"""The auth flow against the real local GoTrue.

Everything in `tests/test_auth.py` stubs the provider, which is what makes those tests
fast — but it also means the token this backend actually receives is never verified by
the code that verifies tokens. In particular `tokens.verify_access_token` checks the
issuer and the audience against values only a real token can confirm: get either
expectation wrong and every authenticated request 401s, with nothing in the unit suite
to notice.

These tests create real users in the local `auth.users`, which `db_session`'s rollback
does not cover — GoTrue writes them over HTTP, outside our transaction. Emails are
therefore unique per run. The profile rows do go through the rolled-back session.
"""

from uuid import uuid4

import pytest

from kummo.auth import cookies, service, tokens
from kummo.auth.errors import (
    EmailNotConfirmed,
    InvalidCredentials,
    InvalidToken,
    SessionExpired,
)

from .mail import confirmation_token_hash

pytestmark = pytest.mark.integration


def unique_email() -> str:
    return f"anna-{uuid4().hex[:12]}@example.de"


PASSWORD = "ein-geheimes-passwort"


async def sign_up_and_confirm(email: str) -> service.Session:
    """Sign-up leaves the account unconfirmed, so the session comes from the link."""
    pending = await service.sign_up(email, PASSWORD)
    assert isinstance(pending, service.PendingIdentity)
    return await service.confirm_email(await confirmation_token_hash(email))


@pytest.fixture
async def real_session() -> service.Session:
    """A genuine signed-in session, tokens included."""
    return await sign_up_and_confirm(unique_email())


# --- Token verification -----------------------------------------------------------


async def test_a_real_access_token_verifies(real_session):
    """The end-to-end check the stubbed suite cannot make."""
    identity = await tokens.verify_access_token(real_session.access_token)

    assert identity.auth_user_id == real_session.auth_user_id
    assert identity.email == real_session.email


async def test_the_expected_issuer_matches_what_the_provider_actually_issues(
    real_session,
):
    """A wrong expectation here rejects every request, so pin it against a real token."""
    claims = (await tokens._get_verifier_client()).auth
    response = await claims.get_claims(real_session.access_token)
    actual = response.claims if hasattr(response, "claims") else response["claims"]

    assert actual["iss"] == tokens.expected_issuer()
    assert actual["aud"] == tokens.EXPECTED_AUDIENCE


async def test_a_tampered_token_is_rejected(real_session):
    """Flip the last character of the signature."""
    head, _, signature = real_session.access_token.rpartition(".")
    tampered = f"{head}.{'A' if signature[-1] != 'A' else 'B'}{signature[1:]}"

    with pytest.raises(InvalidToken):
        await tokens.verify_access_token(tampered)


async def test_a_garbage_token_is_rejected():
    with pytest.raises(InvalidToken):
        await tokens.verify_access_token("not-even-a-jwt")


# --- Credentials ------------------------------------------------------------------


async def test_signing_up_yields_a_pending_identity_until_the_link_is_clicked():
    """The hosted project's behaviour, now the local one too."""
    email = unique_email()

    pending = await service.sign_up(email, PASSWORD)

    assert isinstance(pending, service.PendingIdentity)
    assert pending.email == email
    with pytest.raises(EmailNotConfirmed):
        await service.sign_in(email, PASSWORD)


async def test_confirming_the_link_produces_a_verifiable_session():
    email = unique_email()

    session = await sign_up_and_confirm(email)

    identity = await tokens.verify_access_token(session.access_token)
    assert identity.email == email


async def test_confirmation_route_sets_session_cookies_and_authenticates(db_client):
    email = unique_email()

    registered = await db_client.post(
        "/api/auth/register/client",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert registered.status_code == 202

    token_hash = await confirmation_token_hash(email)

    confirmed = await db_client.get(
        "/api/auth/confirm",
        params={"token_hash": token_hash, "type": "email"},
        follow_redirects=False,
    )

    assert confirmed.status_code == 303

    issued = {
        header.split("=", 1)[0]
        for header in confirmed.headers.get_list("set-cookie")
    }
    assert cookies.SESSION_COOKIE in issued
    assert cookies.REFRESH_COOKIE in issued

    me = await db_client.get("/api/auth/me")

    assert me.status_code == 200


async def test_signing_in_returns_a_usable_session():
    email = unique_email()
    await sign_up_and_confirm(email)

    signed_in = await service.sign_in(email, PASSWORD)

    identity = await tokens.verify_access_token(signed_in.access_token)
    assert identity.email == email


async def test_a_wrong_password_is_translated_to_invalid_credentials():
    email = unique_email()
    await sign_up_and_confirm(email)

    with pytest.raises(InvalidCredentials):
        await service.sign_in(email, "das-falsche-passwort")


# --- Session lifecycle ------------------------------------------------------------


async def test_refreshing_yields_a_working_token(real_session):
    refreshed = await service.refresh(real_session.refresh_token)

    identity = await tokens.verify_access_token(refreshed.access_token)
    assert identity.auth_user_id == real_session.auth_user_id


async def test_signing_out_revokes_the_refresh_token(real_session):
    """Regression: logout used to leave the refresh token live whenever the access
    token had already expired, so the session outlived the sign-out by thirty days."""
    await service.sign_out(real_session.refresh_token, real_session.access_token)

    with pytest.raises(SessionExpired):
        await service.refresh(real_session.refresh_token)


async def test_signing_out_with_only_a_refresh_token_still_revokes(real_session):
    """The access cookie expires long before the refresh cookie, so this is the
    ordinary case rather than an edge one."""
    await service.sign_out(real_session.refresh_token)

    with pytest.raises(SessionExpired):
        await service.refresh(real_session.refresh_token)
