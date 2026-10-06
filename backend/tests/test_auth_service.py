"""Unit tests for the provider boundary itself.

`tests/test_auth.py` replaces this module wholesale to exercise everything above it,
which leaves its own logic — the error translation and the PKCE derivation — with
nothing testing it. Both are pure functions, so they are tested directly here; the
network-facing coroutines stay the route tests' problem.
"""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from supabase_auth.errors import AuthApiError, AuthWeakPasswordError

from kummo.auth import service
from kummo.auth.errors import (
    AuthError,
    EmailAlreadyRegistered,
    EmailConfirmationRequired,
    EmailNotConfirmed,
    InvalidCredentials,
    RateLimited,
    WeakPassword,
)


def api_error(message: str, code: str | None) -> AuthApiError:
    return AuthApiError(message, 400, code)


# --- Error translation ------------------------------------------------------------


@pytest.mark.parametrize("code", ["user_already_exists", "email_exists"])
def test_an_existing_address_becomes_email_already_registered(code):
    translated = service._translate(api_error("already registered", code))

    assert isinstance(translated, EmailAlreadyRegistered)


@pytest.mark.parametrize("code", ["invalid_credentials", "invalid_grant"])
def test_a_rejected_credential_becomes_invalid_credentials(code):
    translated = service._translate(api_error("nope", code))

    assert isinstance(translated, InvalidCredentials)


def test_invalid_credentials_is_recognised_by_message_when_the_code_is_absent():
    translated = service._translate(api_error("Invalid login credentials", None))

    assert isinstance(translated, InvalidCredentials)


def test_a_weak_password_does_not_carry_the_providers_wording():
    """The message reaches a 400 body, so it must be ours rather than GoTrue's."""
    provider_copy = "Password should contain at least one character of each: abc123"
    translated = service._translate(AuthWeakPasswordError(provider_copy, 400, ["length"]))

    assert isinstance(translated, WeakPassword)
    assert provider_copy not in str(translated)


def test_an_unmapped_error_stays_a_bare_auth_error():
    """Which the route layer turns into a 400 with a fixed detail."""
    translated = service._translate(api_error("something new", "some_new_code"))

    assert type(translated) is AuthError


def test_an_unconfirmed_address_becomes_email_not_confirmed():
    """The failure that made cloud sign-in look like an outage.

    Unmapped, it arrived at the route layer as a bare `AuthError` and was reported as
    "the identity provider is unavailable" — for a live 400 from the token endpoint.
    """
    translated = service._translate(api_error("Email not confirmed", "email_not_confirmed"))

    assert isinstance(translated, EmailNotConfirmed)


def test_email_not_confirmed_is_recognised_by_message_when_the_code_is_absent():
    translated = service._translate(api_error("Email not confirmed", None))

    assert isinstance(translated, EmailNotConfirmed)


@pytest.mark.parametrize("code", ["over_email_send_rate_limit", "over_request_rate_limit"])
def test_a_throttle_becomes_rate_limited(code):
    translated = service._translate(api_error("too many requests", code))

    assert isinstance(translated, RateLimited)


# --- Sign-up outcomes -------------------------------------------------------------


class _User:
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email
        self.user_metadata = {}


class _Response:
    def __init__(self, user=None, session=None):
        self.user = user
        self.session = session


def test_a_signup_without_a_session_is_a_pending_identity():
    """What a provider that requires email confirmation answers."""
    user_id = uuid4()
    pending = service._to_pending(_Response(user=_User(user_id, "anna@example.de")))

    assert pending == service.PendingIdentity(
        auth_user_id=user_id, email="anna@example.de"
    )


def test_a_signup_with_neither_session_nor_user_is_refused():
    with pytest.raises(EmailConfirmationRequired):
        service._to_pending(_Response())


# --- PKCE and state ---------------------------------------------------------------


def _authorize_params(redirect: service.OAuthRedirect) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(redirect.url).query).items()}


def test_the_challenge_is_the_s256_digest_of_the_verifier():
    """A silent bug here breaks every OAuth sign-in, and only the provider would notice."""
    redirect = service.build_oauth_redirect("google", "https://kummo.test/api/auth/callback")

    params = _authorize_params(redirect)
    digest = hashlib.sha256(redirect.code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    assert params["code_challenge"] == expected
    assert "=" not in params["code_challenge"]
    # RFC 7636 spells the method in uppercase.
    assert params["code_challenge_method"] == "S256"


def test_the_authorize_url_carries_the_provider_and_the_redirect():
    redirect = service.build_oauth_redirect("google", "https://kummo.test/api/auth/callback")

    params = _authorize_params(redirect)

    assert params["provider"] == "google"
    assert params["redirect_to"] == "https://kummo.test/api/auth/callback"


def test_the_authorize_url_does_not_override_supabase_state():
    redirect = service.build_oauth_redirect(
        "google", "https://kummo.test/api/auth/callback"
    )

    assert "state" not in _authorize_params(redirect)


def test_every_flow_gets_a_fresh_verifier():
    first = service.build_oauth_redirect(
        "google", "https://kummo.test/api/auth/callback"
    )
    second = service.build_oauth_redirect(
        "google", "https://kummo.test/api/auth/callback"
    )

    assert first.code_verifier != second.code_verifier


def test_the_verifier_stays_within_the_length_the_rfc_allows():
    redirect = service.build_oauth_redirect("google", "https://kummo.test/api/auth/callback")

    assert 43 <= len(redirect.code_verifier) <= 128


# --- Session extraction -----------------------------------------------------------


class FakeUser:
    def __init__(self, user_id, email, metadata):
        self.id = user_id
        self.email = email
        self.user_metadata = metadata


class FakeSession:
    def __init__(self, user, access_token="access", expires_in=3600):
        self.access_token = access_token
        self.refresh_token = "refresh"
        self.expires_in = expires_in
        self.user = user


class FakeResponse:
    def __init__(self, session):
        self.session = session


def make_response(metadata=None, **session_overrides) -> FakeResponse:
    user = FakeUser(
        "11111111-1111-1111-1111-111111111111", "anna@example.de", metadata or {}
    )
    return FakeResponse(FakeSession(user, **session_overrides))


def test_a_signup_without_a_session_means_the_address_needs_confirming():
    with pytest.raises(EmailConfirmationRequired):
        service._to_session(FakeResponse(None))


def test_a_session_without_an_access_token_is_treated_the_same():
    with pytest.raises(EmailConfirmationRequired):
        service._to_session(make_response(access_token=None))


def test_the_full_name_claim_is_read_from_either_metadata_key():
    assert service._to_session(make_response({"full_name": "Anna Schmidt"})).full_name == (
        "Anna Schmidt"
    )
    assert service._to_session(make_response({"name": "Anna Schmidt"})).full_name == (
        "Anna Schmidt"
    )


def test_a_missing_full_name_is_none_rather_than_a_guess():
    assert service._to_session(make_response()).full_name is None


def test_a_missing_expiry_falls_back_to_an_hour():
    assert service._to_session(make_response(expires_in=None)).expires_in == 3600
