"""Route tests for /api/auth.

The identity provider is stubbed at the `service` boundary — that module is the only
one that talks to Supabase, so replacing it exercises everything above it (cookies,
profile linking, status codes) without a network call.
"""

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request

from kummo.auth import cookies, routes, service
from kummo.auth.dependencies import (
    get_current_client,
    get_current_identity,
    get_current_vendor,
    get_optional_identity,
)
from kummo.auth.errors import (
    AuthError,
    ConfirmationLinkInvalid,
    EmailAlreadyRegistered,
    EmailConfirmationRequired,
    EmailNotConfirmed,
    InvalidCredentials,
    OAuthExchangeFailed,
    ProviderUnavailable,
    RateLimited,
    SessionExpired,
    WeakPassword,
)
from kummo.auth.profiles import Profile, split_full_name
from kummo.auth.tokens import Identity

# Value stored in the PKCE verifier cookie during OAuth tests.
OAUTH_VERIFIER_COOKIE_VALUE = "verifier-value"
from kummo.clients import data_model as clients
from kummo.main import app
from kummo.vendors import data_model as vendors


def make_session(**overrides) -> service.Session:
    defaults = dict(
        access_token="access-token-value",
        refresh_token="refresh-token-value",
        expires_in=3600,
        auth_user_id=uuid4(),
        email="anna@example.de",
        full_name=None,
    )
    return service.Session(**{**defaults, **overrides})


@pytest.fixture
def provider(monkeypatch):
    """Replaces the identity provider with recorded, controllable behaviour."""

    class Provider:
        def __init__(self):
            self.session = make_session()
            self.signed_out: list[tuple[str, str]] = []
            self.raises: Exception | None = None
            # Set to mimic a provider that requires email confirmation: the identity
            # exists, the session does not.
            self.pending: service.PendingIdentity | None = None
            self.resent: list[str] = []

        async def sign_up(self, email, password):
            if self.raises:
                raise self.raises
            return self.pending or self.session

        async def confirm_email(self, token_hash):
            if self.raises:
                raise self.raises
            return self.session

        async def resend_confirmation(self, email):
            if self.raises:
                raise self.raises
            self.resent.append(email)

        async def sign_in(self, email, password):
            if self.raises:
                raise self.raises
            return self.session

        async def refresh(self, refresh_token):
            if self.raises:
                raise self.raises
            return self.session

        async def sign_out(self, refresh_token, access_token=""):
            self.signed_out.append((refresh_token, access_token))

        async def exchange_code(self, code, verifier):
            if self.raises:
                raise self.raises
            return self.session

        def build_oauth_redirect(self, provider_name, redirect_to):
            return service.OAuthRedirect(
                url=f"https://idp.test/authorize?provider={provider_name}",
                code_verifier="verifier-value",
            )

    fake = Provider()
    for name in (
        "sign_up",
        "confirm_email",
        "resend_confirmation",
        "sign_in",
        "refresh",
        "sign_out",
        "exchange_code",
        "build_oauth_redirect",
    ):
        monkeypatch.setattr(routes.service, name, getattr(fake, name))
    return fake


# --- Registration ---------------------------------------------------------------


async def test_register_client_creates_profile_and_sets_cookies(
    client, stub_session, provider
):
    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "ein-gutes-passwort",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["user"]["role"] == "client"
    assert body["user"]["display_name"] == "Anna Schmidt"

    added = stub_session.added[0]
    assert isinstance(added, clients.Client)
    assert added.auth_user_id == provider.session.auth_user_id


async def test_register_client_response_carries_no_tokens(client, stub_session, provider):
    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "ein-gutes-passwort",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    serialized = response.text
    assert provider.session.access_token not in serialized
    assert provider.session.refresh_token not in serialized
    assert set(response.json()["user"]) == {"id", "email", "role", "display_name"}


async def test_session_cookies_are_httponly(client, stub_session, provider):
    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "ein-gutes-passwort",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    set_cookie_headers = response.headers.get_list("set-cookie")
    session_header = next(
        h for h in set_cookie_headers if h.startswith(f"{cookies.SESSION_COOKIE}=")
    )
    refresh_header = next(
        h for h in set_cookie_headers if h.startswith(f"{cookies.REFRESH_COOKIE}=")
    )
    assert "HttpOnly" in session_header
    assert "HttpOnly" in refresh_header


async def test_register_vendor_creates_vendor_profile(client, stub_session, provider):
    response = await client.post(
        "/api/auth/register/vendor",
        json={
            "email": "info@werkstatt.de",
            "password": "ein-gutes-passwort",
            "name": "Kreativwerkstatt",
            "address": "Oranienstraße 1, 10999 Berlin",
            "activity_type": ["kunst"],
        },
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "vendor"
    assert response.json()["user"]["display_name"] == "Kreativwerkstatt"
    assert isinstance(stub_session.added[0], vendors.Vendor)


async def test_register_vendor_requires_activity_type(client, stub_session, provider):
    response = await client.post(
        "/api/auth/register/vendor",
        json={
            "email": "info@werkstatt.de",
            "password": "ein-gutes-passwort",
            "name": "Kreativwerkstatt",
            "address": "Oranienstraße 1",
            "activity_type": [],
        },
    )

    assert response.status_code == 422


async def test_register_rejects_short_password(client, stub_session, provider):
    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "kurz",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert response.status_code == 422


async def test_register_duplicate_email_is_409(client, stub_session, provider):
    provider.raises = EmailAlreadyRegistered("already exists")

    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "ein-gutes-passwort",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert response.status_code == 409


# --- Email confirmation ----------------------------------------------------------


def make_pending(auth_user_id=None) -> service.PendingIdentity:
    return service.PendingIdentity(
        auth_user_id=auth_user_id or uuid4(), email="anna@example.de"
    )


async def test_register_client_awaiting_confirmation_creates_the_profile_without_cookies(
    client, stub_session, provider
):
    """The identity exists but has no session yet.

    The profile is still written — the auth user id is already final and the details
    typed into the form only exist in this request — but nothing is handed out that
    would let the browser act as if it were signed in.
    """
    provider.pending = make_pending()

    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "ein-gutes-passwort",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending_confirmation"
    assert response.json()["user"]["display_name"] == "Anna Schmidt"
    assert response.headers.get_list("set-cookie") == []

    added = stub_session.added[0]
    assert isinstance(added, clients.Client)
    assert added.auth_user_id == provider.pending.auth_user_id


async def test_register_vendor_awaiting_confirmation_keeps_the_business_details(
    client, stub_session, provider
):
    provider.pending = make_pending()

    response = await client.post(
        "/api/auth/register/vendor",
        json={
            "email": "info@werkstatt.de",
            "password": "ein-gutes-passwort",
            "name": "Kreativwerkstatt",
            "address": "Oranienstraße 1, 10999 Berlin",
            "activity_type": ["kunst"],
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending_confirmation"
    added = stub_session.added[0]
    assert isinstance(added, vendors.Vendor)
    assert added.activity_type == ["kunst"]
    assert response.headers.get_list("set-cookie") == []


async def test_login_before_confirming_is_403(client, stub_session, provider):
    provider.raises = EmailNotConfirmed("not confirmed yet")

    response = await client.post(
        "/api/auth/login", json={"email": "anna@example.de", "password": "geheim1234"}
    )

    # Not 401: the password was right, and repeating it will not help.
    assert response.status_code == 403


async def test_confirming_signs_the_client_in(client, stub_session, provider):
    stub_session.scalar_results = [
        clients.Client(
            id=uuid4(),
            auth_user_id=provider.session.auth_user_id,
            first_name="Anna",
            last_name="Schmidt",
            email="anna@example.de",
        )
    ]

    response = await client.get(
        "/api/auth/confirm",
        params={"token_hash": "hash-from-the-email", "type": "email"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/client.html")
    issued = {
        header.split("=", 1)[0] for header in response.headers.get_list("set-cookie")
    }
    assert issued == {cookies.SESSION_COOKIE, cookies.REFRESH_COOKIE}


async def test_confirming_sends_a_vendor_to_the_dashboard(
    client, stub_session, provider
):
    stub_session.scalar_results = [
        None,
        vendors.Vendor(
            id=uuid4(),
            auth_user_id=provider.session.auth_user_id,
            name="Kreativwerkstatt",
            address="Oranienstraße 1",
            email="info@werkstatt.de",
            activity_type=["kunst"],
        ),
    ]

    response = await client.get(
        "/api/auth/confirm",
        params={"token_hash": "hash-from-the-email"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/vendor.html")


async def test_a_spent_confirmation_link_goes_back_to_login(
    client, stub_session, provider
):
    provider.raises = ConfirmationLinkInvalid("already used")

    response = await client.get(
        "/api/auth/confirm",
        params={"token_hash": "hash-from-the-email"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login.html?error=confirm")
    assert response.headers.get_list("set-cookie") == []


async def test_a_confirmation_link_without_a_token_goes_back_to_login(
    client, stub_session, provider
):
    response = await client.get("/api/auth/confirm", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login.html?error=confirm")


async def test_resending_the_confirmation_is_204(client, stub_session, provider):
    response = await client.post(
        "/api/auth/resend-confirmation", json={"email": "anna@example.de"}
    )

    assert response.status_code == 204
    assert provider.resent == ["anna@example.de"]


async def test_a_throttled_resend_is_429(client, stub_session, provider):
    provider.raises = RateLimited("wait a minute")

    response = await client.post(
        "/api/auth/resend-confirmation", json={"email": "anna@example.de"}
    )

    assert response.status_code == 429


# --- Login / logout -------------------------------------------------------------


async def test_login_returns_existing_profile(client, stub_session, provider):
    existing = clients.Client(
        id=uuid4(),
        auth_user_id=provider.session.auth_user_id,
        first_name="Anna",
        last_name="Schmidt",
        email="anna@example.de",
    )
    stub_session.scalar_results = [existing]

    response = await client.post(
        "/api/auth/login",
        json={"email": "anna@example.de", "password": "ein-gutes-passwort"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Anna Schmidt"
    # An existing profile must not be duplicated.
    assert stub_session.added == []


async def test_login_completes_an_interrupted_registration(
    client, stub_session, provider
):
    """No profile row: registration died between the identity and the insert."""
    provider.session = make_session(full_name="Anna Schmidt")
    stub_session.scalar_results = [None, None]

    response = await client.post(
        "/api/auth/login",
        json={"email": "anna@example.de", "password": "ein-gutes-passwort"},
    )

    assert response.status_code == 200
    assert isinstance(stub_session.added[0], clients.Client)
    assert response.json()["display_name"] == "Anna Schmidt"


async def test_login_with_bad_credentials_is_401(client, stub_session, provider):
    provider.raises = InvalidCredentials("nope")

    response = await client.post(
        "/api/auth/login", json={"email": "anna@example.de", "password": "falsch"}
    )

    assert response.status_code == 401


async def test_logout_clears_cookies_and_revokes(client, stub_session, provider):
    client.cookies.set(cookies.SESSION_COOKIE, "access-token-value")
    client.cookies.set(cookies.REFRESH_COOKIE, "refresh-token-value")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert provider.signed_out == [("refresh-token-value", "access-token-value")]
    cleared = response.headers.get_list("set-cookie")
    assert any(cookies.SESSION_COOKIE in header for header in cleared)
    assert any(cookies.REFRESH_COOKIE in header for header in cleared)


async def test_logout_revokes_with_only_the_refresh_cookie(
    client, stub_session, provider
):
    """The access cookie expires after an hour, the refresh cookie after thirty days.

    Requiring both meant that logging out of a tab left open overnight cleared the
    cookies while the session stayed alive at the provider.
    """
    client.cookies.set(cookies.REFRESH_COOKIE, "refresh-token-value")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert provider.signed_out == [("refresh-token-value", "")]


async def test_logout_without_a_session_still_succeeds(client, stub_session, provider):
    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    assert provider.signed_out == []


# --- Refresh --------------------------------------------------------------------


async def test_refresh_without_cookie_is_401(client, stub_session, provider):
    response = await client.post("/api/auth/refresh")

    assert response.status_code == 401


async def test_refresh_with_expired_token_is_401(client, stub_session, provider):
    client.cookies.set(cookies.REFRESH_COOKIE, "stale")
    provider.raises = SessionExpired("expired")

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 401


def _expired_cookies(response) -> set[str]:
    """The cookie names this response tells the browser to drop."""
    return {
        header.split("=", 1)[0]
        for header in response.headers.get_list("set-cookie")
        if "Max-Age=0" in header or "01 Jan 1970" in header
    }


async def test_refresh_returns_the_profile_and_rotates_the_cookies(
    client, stub_session, provider
):
    client.cookies.set(cookies.REFRESH_COOKIE, "refresh-token-value")
    stub_session.scalar_results = [
        clients.Client(
            id=uuid4(),
            auth_user_id=provider.session.auth_user_id,
            first_name="Anna",
            last_name="Schmidt",
            email="anna@example.de",
        )
    ]

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 200
    assert response.json()["role"] == "client"
    issued = response.headers.get_list("set-cookie")
    assert any(h.startswith(f"{cookies.SESSION_COOKIE}=") for h in issued)
    assert any(h.startswith(f"{cookies.REFRESH_COOKIE}=") for h in issued)


async def test_refresh_failure_actually_clears_the_cookies(
    client, stub_session, provider
):
    """Regression: the clear used to be written to the injected `Response` and then
    discarded, because raising discards it. The browser kept re-sending a token the
    provider had already rejected."""
    client.cookies.set(cookies.SESSION_COOKIE, "stale-access")
    client.cookies.set(cookies.REFRESH_COOKIE, "stale-refresh")
    provider.raises = SessionExpired("expired")

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert _expired_cookies(response) == {
        cookies.SESSION_COOKIE,
        cookies.REFRESH_COOKIE,
    }


async def test_refresh_without_a_linked_profile_is_404_and_clears_cookies(
    client, stub_session, provider
):
    """Rotation has already revoked the token the browser holds, so keeping it would
    strand the session on a dead cookie."""
    client.cookies.set(cookies.REFRESH_COOKIE, "refresh-token-value")
    stub_session.scalar_results = []  # neither a client nor a vendor row

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 404
    assert _expired_cookies(response) == {
        cookies.SESSION_COOKIE,
        cookies.REFRESH_COOKIE,
    }


# --- /me ------------------------------------------------------------------------


async def test_me_without_a_session_is_401(client, stub_session):
    response = await client.get("/api/auth/me")

    assert response.status_code == 401


async def test_me_returns_the_linked_profile(client, stub_session):
    auth_user_id = uuid4()
    stub_session.scalar_results = [
        clients.Client(
            id=uuid4(),
            auth_user_id=auth_user_id,
            first_name="Anna",
            last_name="Schmidt",
            email="anna@example.de",
        )
    ]
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        auth_user_id=auth_user_id, email="anna@example.de"
    )
    try:
        response = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_identity, None)

    assert response.status_code == 200
    assert response.json()["role"] == "client"


# --- OAuth ----------------------------------------------------------------------


async def test_oauth_start_redirects_and_stores_the_verifier(
    client, stub_session, provider
):
    response = await client.get("/api/auth/oauth/google", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://idp.test/authorize")
    verifier_cookie = next(
        h
        for h in response.headers.get_list("set-cookie")
        if h.startswith(f"{cookies.OAUTH_VERIFIER_COOKIE}=")
    )
    assert "HttpOnly" in verifier_cookie
    # The cookie carries only the PKCE verifier; Supabase owns OAuth state.
    assert f"{cookies.OAUTH_VERIFIER_COOKIE}=verifier-value" in verifier_cookie

async def test_oauth_start_rejects_unknown_provider(client, stub_session, provider):
    response = await client.get("/api/auth/oauth/myspace", follow_redirects=False)

    assert response.status_code == 404


async def test_oauth_callback_creates_a_client_profile(client, stub_session, provider):
    provider.session = make_session(full_name="Anna Schmidt")
    stub_session.scalar_results = [None, None]
    client.cookies.set(cookies.OAUTH_VERIFIER_COOKIE, OAUTH_VERIFIER_COOKIE_VALUE)

    response = await client.get(
        "/api/auth/callback",
        params={"code": "abc"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/client.html")
    added = stub_session.added[0]
    assert isinstance(added, clients.Client)
    assert (added.first_name, added.last_name) == ("Anna", "Schmidt")


async def test_oauth_callback_sends_a_vendor_to_the_dashboard(
    client, stub_session, provider
):
    stub_session.scalar_results = [
        None,
        vendors.Vendor(
            id=uuid4(),
            auth_user_id=provider.session.auth_user_id,
            name="Kreativwerkstatt",
            address="Oranienstraße 1",
            email="info@werkstatt.de",
            activity_type=["kunst"],
        ),
    ]
    client.cookies.set(cookies.OAUTH_VERIFIER_COOKIE, OAUTH_VERIFIER_COOKIE_VALUE)

    response = await client.get(
        "/api/auth/callback",
        params={"code": "abc"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/vendor.html")
    assert stub_session.added == []


async def test_oauth_callback_without_a_verifier_goes_back_to_login(
    client, stub_session, provider
):
    response = await client.get(
        "/api/auth/callback",
        params={"code": "abc"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=oauth" in response.headers["location"]


async def test_oauth_callback_when_the_user_declines_goes_back_to_login(
    client, stub_session, provider
):
    """Consent denied: the provider sends `error` instead of a code."""
    client.cookies.set(cookies.OAUTH_VERIFIER_COOKIE, OAUTH_VERIFIER_COOKIE_VALUE)

    response = await client.get(
        "/api/auth/callback",
        params={"error": "access_denied", "error_description": "User declined"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=oauth" in response.headers["location"]


async def test_oauth_callback_clears_the_state_cookie(client, stub_session, provider):
    stub_session.scalar_results = [None, None]
    client.cookies.set(cookies.OAUTH_VERIFIER_COOKIE, OAUTH_VERIFIER_COOKIE_VALUE)

    response = await client.get(
        "/api/auth/callback",
        params={"code": "abc"},
        follow_redirects=False,
    )

    cleared = response.headers.get_list("set-cookie")
    assert any(
        h.startswith(f"{cookies.OAUTH_VERIFIER_COOKIE}=")
        and ("Max-Age=0" in h or "01 Jan 1970" in h)
        for h in cleared
    )


async def test_oauth_callback_with_a_failed_exchange_goes_back_to_login(
    client, stub_session, provider
):
    provider.raises = OAuthExchangeFailed("bad code")
    client.cookies.set(cookies.OAUTH_VERIFIER_COOKIE, OAUTH_VERIFIER_COOKIE_VALUE)

    response = await client.get(
        "/api/auth/callback",
        params={"code": "abc"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=oauth" in response.headers["location"]


def test_uuid_round_trip_of_identity():
    identity = Identity(auth_user_id=UUID(int=1), email="a@b.de")

    assert identity.auth_user_id == UUID(int=1)


# --- Profile guards ---------------------------------------------------------------


async def test_me_without_a_linked_profile_is_404(client, stub_session):
    """Authenticated but unlinked: the identity exists, the profile row does not."""
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        auth_user_id=uuid4(), email="anna@example.de"
    )
    try:
        response = await client.get("/api/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_identity, None)

    assert response.status_code == 404


async def test_a_client_is_refused_by_the_vendor_guard(stub_session):
    profile = Profile(
        role="client", id=uuid4(), email="anna@example.de", display_name="Anna"
    )

    with pytest.raises(HTTPException) as raised:
        await get_current_vendor(profile)

    assert raised.value.status_code == 403


async def test_a_vendor_is_refused_by_the_client_guard(stub_session):
    profile = Profile(
        role="vendor", id=uuid4(), email="info@werkstatt.de", display_name="Werkstatt"
    )

    with pytest.raises(HTTPException) as raised:
        await get_current_client(profile)

    assert raised.value.status_code == 403


async def test_each_guard_passes_its_own_role_through(stub_session):
    client_profile = Profile(
        role="client", id=uuid4(), email="anna@example.de", display_name="Anna"
    )
    vendor_profile = Profile(
        role="vendor", id=uuid4(), email="info@werkstatt.de", display_name="Werkstatt"
    )

    assert await get_current_client(client_profile) is client_profile
    assert await get_current_vendor(vendor_profile) is vendor_profile


async def test_optional_identity_is_none_for_an_anonymous_caller():
    """Unused by any route today, so it needs a test of its own to stay honest."""
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})

    assert await get_optional_identity(request) is None


# --- Provider error mapping -------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (WeakPassword("too weak"), 400),
        (EmailConfirmationRequired("confirm first"), 400),
        (RateLimited("too many"), 429),
        (ProviderUnavailable("unreachable"), 502),
        # Regression: an unmapped provider rejection used to be reported as a 502
        # outage, which is how a live "email not confirmed" 400 read as downtime.
        (AuthError("something we do not map"), 400),
    ],
)
async def test_registration_maps_provider_errors(
    client, stub_session, provider, error, expected_status
):
    provider.raises = error

    response = await client.post(
        "/api/auth/register/client",
        json={
            "email": "anna@example.de",
            "password": "geheim1234",
            "first_name": "Anna",
            "last_name": "Schmidt",
        },
    )

    assert response.status_code == expected_status


async def test_an_unavailable_provider_does_not_leak_its_message(
    client, stub_session, provider
):
    provider.raises = ProviderUnavailable("connect timeout to db.supabase.co:5432")

    response = await client.post(
        "/api/auth/login", json={"email": "anna@example.de", "password": "geheim1234"}
    )

    assert response.status_code == 502
    assert "supabase" not in response.text.lower()


async def test_an_unmapped_provider_message_is_not_echoed_back(
    client, stub_session, provider
):
    provider.raises = AuthError("relation auth.users does not exist on db.supabase.co")

    response = await client.post(
        "/api/auth/login", json={"email": "anna@example.de", "password": "geheim1234"}
    )

    assert response.status_code == 400
    assert "supabase" not in response.text.lower()


# --- Cookie attributes ------------------------------------------------------------


async def test_session_cookies_carry_the_hardening_attributes(
    client, stub_session, provider
):
    response = await client.post(
        "/api/auth/login", json={"email": "anna@example.de", "password": "geheim1234"}
    )

    issued = {
        header.split("=", 1)[0]: header
        for header in response.headers.get_list("set-cookie")
    }
    for name in (cookies.SESSION_COOKIE, cookies.REFRESH_COOKIE):
        assert "HttpOnly" in issued[name]
        assert "SameSite=lax" in issued[name]
        assert "Path=/" in issued[name]

    # The access cookie tracks the token's own lifetime; the refresh cookie outlives it.
    assert f"Max-Age={provider.session.expires_in}" in issued[cookies.SESSION_COOKIE]
    assert f"Max-Age={cookies.REFRESH_MAX_AGE}" in issued[cookies.REFRESH_COOKIE]


# --- split_full_name --------------------------------------------------------------


@pytest.mark.parametrize(
    ("full_name", "email", "expected"),
    [
        ("Anna Schmidt", "anna@example.de", ("Anna", "Schmidt")),
        ("Anna Maria Schmidt", "anna@example.de", ("Anna Maria", "Schmidt")),
        ("Anna", "anna@example.de", ("Anna", "")),
        ("  ", "anna@example.de", ("anna", "")),
        (None, "anna@example.de", ("anna", "")),
        (None, "@example.de", ("Unbekannt", "")),
    ],
)
def test_split_full_name(full_name, email, expected):
    assert split_full_name(full_name, email) == expected
