"""The /api/auth surface.

Every route here hands the caller a session through HttpOnly cookies and a plain
`CurrentUser` body. Nothing leaks that the identity provider is Supabase — not a URL,
not a token, not a provider error code.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics
from ..config import Settings, get_settings
from ..db import get_session
from . import cookies, service
from .api_model import (
    ClientRegistration,
    Credentials,
    CurrentUser,
    EmailRequest,
    RegistrationResult,
    VendorRegistration,
)
from .dependencies import get_current_profile
from .errors import (
    AuthError,
    ConfirmationLinkInvalid,
    EmailAlreadyRegistered,
    EmailConfirmationRequired,
    EmailNotConfirmed,
    InvalidCredentials,
    ProviderUnavailable,
    RateLimited,
    SessionExpired,
    WeakPassword,
)
from .profiles import (
    Profile,
    ensure_client_profile,
    ensure_vendor_profile,
    find_profile,
    split_full_name,
)
from .tokens import Identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SUPPORTED_PROVIDERS = {"google", "apple", "azure", "github", "facebook"}


def _as_current_user(profile: Profile) -> CurrentUser:
    return CurrentUser(
        id=profile.id,
        email=profile.email,
        role=profile.role,
        display_name=profile.display_name,
    )


def _identity_of(session: service.Session | service.PendingIdentity) -> Identity:
    return Identity(auth_user_id=session.auth_user_id, email=session.email)


def _home_of(profile: Profile) -> str:
    """The page that belongs to the role — the same split the frontend guard enforces."""
    return "/vendor.html" if profile.role == "vendor" else "/client.html"


async def _profile_or_completed(db: AsyncSession, auth_session: service.Session) -> Profile:
    """The profile linked to this identity, created now if registration never got there.

    Registration cannot be atomic — the identity is an HTTP call, the profile a local
    transaction — so an interrupted one is completed on the next entry rather than
    compensated.

    A warning rather than an aside: nothing recorded which role was being registered,
    so this always produces a *client*. If the interrupted registration was a vendor's,
    this is the line that says where that went.
    """
    profile = await find_profile(db, auth_session.auth_user_id)
    if profile is not None:
        return profile

    logger.warning(
        "Auth user %s has no profile; completing it as a client",
        auth_session.auth_user_id,
    )
    first_name, last_name = split_full_name(auth_session.full_name, auth_session.email)
    return await ensure_client_profile(
        db, _identity_of(auth_session), first_name, last_name
    )


def _http_error(error: AuthError) -> HTTPException:
    if isinstance(error, InvalidCredentials):
        return HTTPException(status_code=401, detail=str(error))
    if isinstance(error, EmailAlreadyRegistered):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, EmailNotConfirmed):
        # Credentials that are right but an account that is not usable yet: 403, not
        # 401 — repeating them will not help until the link in the email is clicked.
        return HTTPException(status_code=403, detail=str(error))
    if isinstance(error, RateLimited):
        return HTTPException(status_code=429, detail=str(error))
    if isinstance(error, SessionExpired):
        return HTTPException(status_code=401, detail=str(error))
    if isinstance(error, ProviderUnavailable):
        return HTTPException(status_code=502, detail="The identity provider is unavailable")
    if isinstance(error, (WeakPassword, EmailConfirmationRequired, ConfirmationLinkInvalid)):
        # Our own wording, safe to hand back.
        return HTTPException(status_code=400, detail=str(error))
    # A rejection we have no name for is still a rejection: the caller sent something
    # the provider refused, so it is a 400 — reporting it as 502 said "outage" about a
    # live answer. The provider's own text stays in the log, where it cannot leak a
    # hostname or an internal code to the browser.
    logger.warning("Unmapped auth failure returned as 400: %s", error)
    return HTTPException(status_code=400, detail="The sign-in service refused the request")


def _log_safe(value: str | None, limit: int = 80) -> str:
    """Make provider-supplied text safe to put in a log line.

    Anything arriving on the query string is attacker-controlled; a newline in it
    would let a caller forge whole entries in a plaintext log sink.
    """
    if not value:
        return "none"
    collapsed = " ".join(value.split())
    return collapsed[:limit] if len(collapsed) <= limit else f"{collapsed[:limit]}..."


def _failed_response(error: AuthError) -> JSONResponse:
    """The same mapping as `_http_error`, but as a response we can attach cookies to.

    Headers written to the injected `Response` are only merged into the reply when the
    handler *returns*; raising discards them, because the exception handler builds a
    fresh response. So any path that has to both fail and clear cookies must return.
    """
    http_error = _http_error(error)
    return JSONResponse({"detail": http_error.detail}, status_code=http_error.status_code)


def _registered(
    profile: Profile,
    identity: service.Session | service.PendingIdentity,
    response: Response,
    event: str,
) -> RegistrationResult:
    """Finish a registration, with or without a session to hand out.

    When the provider requires email confirmation it creates the identity and stops
    there, so there is nothing to put in a cookie yet. The profile row is written
    either way — the auth user id is already final, and the details typed into the
    form only exist in this request.
    """
    if isinstance(identity, service.PendingIdentity):
        logger.info("Registered %s %s, awaiting email confirmation", profile.role, profile.id)
        metrics.record_auth_event(event, metrics.PENDING)
        response.status_code = 202
        return RegistrationResult(
            status="pending_confirmation", user=_as_current_user(profile)
        )

    logger.info("Registered %s %s", profile.role, profile.id)
    metrics.record_auth_event(event)
    cookies.set_session_cookies(response, identity)
    return RegistrationResult(status="active", user=_as_current_user(profile))


@router.post("/register/client", response_model=RegistrationResult, status_code=201)
async def register_client(
    body: ClientRegistration,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> RegistrationResult:
    try:
        identity = await service.sign_up(body.email, body.password)
    except AuthError as error:
        metrics.record_auth_event(metrics.AUTH_REGISTER_CLIENT, metrics.FAILURE)
        raise _http_error(error) from error

    # Identifiers, never the address: these lines are an audit trail, not a mailing
    # list, and the profile id is what every other line here can be joined on.
    profile = await ensure_client_profile(
        db, _identity_of(identity), body.first_name, body.last_name
    )
    return _registered(profile, identity, response, metrics.AUTH_REGISTER_CLIENT)


@router.post("/register/vendor", response_model=RegistrationResult, status_code=201)
async def register_vendor(
    body: VendorRegistration,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> RegistrationResult:
    try:
        identity = await service.sign_up(body.email, body.password)
    except AuthError as error:
        metrics.record_auth_event(metrics.AUTH_REGISTER_VENDOR, metrics.FAILURE)
        raise _http_error(error) from error

    profile = await ensure_vendor_profile(
        db,
        _identity_of(identity),
        name=body.name,
        address=body.address,
        activity_type=body.activity_type,
        phone=body.phone,
        website=body.website,
    )
    return _registered(profile, identity, response, metrics.AUTH_REGISTER_VENDOR)


@router.post("/login", response_model=CurrentUser)
async def login(
    body: Credentials,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> CurrentUser:
    try:
        auth_session = await service.sign_in(body.email, body.password)
    except AuthError as error:
        # Worth a series of its own: several distinct provider errors arrive at the
        # caller as the same 401, so the status code cannot tell them apart.
        metrics.record_auth_event(metrics.AUTH_LOGIN, metrics.FAILURE)
        raise _http_error(error) from error

    profile = await _profile_or_completed(db, auth_session)

    logger.info("Signed in %s %s", profile.role, profile.id)
    metrics.record_auth_event(metrics.AUTH_LOGIN)
    cookies.set_session_cookies(response, auth_session)
    return _as_current_user(profile)


@router.get("/confirm")
async def confirm_email(
    token_hash: str | None = None,
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """The link in the confirmation email.

    The provider's own confirmation URL would redirect the browser with the tokens
    attached, which is exactly what the HttpOnly cookie transport exists to avoid. So
    the email template points here instead and the token hash is redeemed server-side:
    the browser leaves this route signed in, holding cookies and no tokens.
    """
    base = settings.app_base_url.rstrip("/")

    def back_to_login() -> RedirectResponse:
        metrics.record_auth_event(metrics.AUTH_CONFIRM, metrics.FAILURE)
        return RedirectResponse(f"{base}/login.html?error=confirm", status_code=303)

    if not token_hash:
        logger.info("Confirmation link without a token hash")
        return back_to_login()

    try:
        auth_session = await service.confirm_email(token_hash)
    except AuthError as error:
        # An expired or already-used link and an unreachable provider are the same
        # dead end for the browser; the distinction is in the log, not the redirect.
        logger.info("Email confirmation failed: %s", error)
        return back_to_login()

    profile = await _profile_or_completed(db, auth_session)

    logger.info("Confirmed %s %s", profile.role, profile.id)
    metrics.record_auth_event(metrics.AUTH_CONFIRM)
    response = RedirectResponse(f"{base}{_home_of(profile)}", status_code=303)
    cookies.set_session_cookies(response, auth_session)
    return response


@router.post("/resend-confirmation", status_code=204)
async def resend_confirmation(body: EmailRequest) -> Response:
    """Send the confirmation email again.

    Always 204, whatever the provider says about the address: answering differently
    for an unknown one would turn this into an account-existence oracle. The single
    exception is a throttle, which the caller has to see to know that waiting helps.
    """
    try:
        await service.resend_confirmation(body.email)
    except AuthError as error:
        metrics.record_auth_event(metrics.AUTH_RESEND, metrics.FAILURE)
        raise _http_error(error) from error

    metrics.record_auth_event(metrics.AUTH_RESEND)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    # The refresh token alone is enough to revoke, and it is the half that is still
    # there: the access cookie lasts an hour, the refresh cookie thirty days. Waiting
    # for both meant the common case — logging out of a tab left open overnight —
    # cleared the cookies while the session stayed alive at the provider.
    refresh_token = cookies.read_refresh_token(request)
    if refresh_token:
        await service.sign_out(refresh_token, cookies.read_access_token(request))

    response = Response(status_code=204)
    cookies.clear_session_cookies(response)
    cookies.clear_oauth_verifier(response)
    metrics.record_auth_event(metrics.AUTH_LOGOUT)
    return response


@router.post("/refresh", response_model=CurrentUser)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> CurrentUser | Response:
    refresh_token = cookies.read_refresh_token(request)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        auth_session = await service.refresh(refresh_token)
    except AuthError as error:
        metrics.record_auth_event(metrics.AUTH_REFRESH, metrics.FAILURE)
        # Returned, not raised, so the cookie clearing survives — otherwise the browser
        # keeps a token the provider has already rejected and re-sends it every time.
        failed = _failed_response(error)
        cookies.clear_session_cookies(failed)
        return failed

    profile = await find_profile(db, auth_session.auth_user_id)
    if profile is None:
        # The refresh succeeded, so rotation has already revoked the token the browser
        # holds. Leaving it in place would strand the session on a dead cookie.
        failed = JSONResponse(
            {"detail": "No profile linked to this account"}, status_code=404
        )
        cookies.clear_session_cookies(failed)
        metrics.record_auth_event(metrics.AUTH_REFRESH, metrics.FAILURE)
        return failed

    metrics.record_auth_event(metrics.AUTH_REFRESH)
    cookies.set_session_cookies(response, auth_session)
    return _as_current_user(profile)


@router.get("/me", response_model=CurrentUser)
async def me(profile: Profile = Depends(get_current_profile)) -> CurrentUser:
    return _as_current_user(profile)


@router.get("/oauth/{provider}")
async def start_oauth(
    provider: str, settings: Settings = Depends(get_settings)
) -> RedirectResponse:
    """Send the browser to the provider.

    Sign-up through a provider always produces a *client*: a vendor is also the shop,
    and a Google profile carries no address or activity types. An existing vendor can
    still sign in this way — the callback finds the profile that is already linked.
    """
    if provider not in SUPPORTED_PROVIDERS:
        # Summarised, not interpolated: the path segment is caller-controlled.
        logger.info("OAuth requested for an unknown provider (%s)", _log_safe(provider))
        # The provider is not a label: it is a path segment the caller chose, and this
        # branch is exactly the case where it is not one of the values we support.
        metrics.record_auth_event(metrics.AUTH_OAUTH_START, metrics.FAILURE)
        raise HTTPException(status_code=404, detail="Unknown provider")

    redirect = service.build_oauth_redirect(
        provider, f"{settings.app_base_url.rstrip('/')}/api/auth/callback"
    )
    metrics.record_auth_event(metrics.AUTH_OAUTH_START)
    response = RedirectResponse(redirect.url, status_code=307)
    cookies.set_oauth_verifier(response, redirect.code_verifier)
    return response


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    base = settings.app_base_url.rstrip("/")
    verifier = cookies.read_oauth_verifier(request)

    def back_to_login() -> RedirectResponse:
        # Every way this callback can fail ends here, so one count covers them all —
        # and the redirect is a 303 either way, which is why the status code cannot.
        metrics.record_auth_event(metrics.AUTH_OAUTH_CALLBACK, metrics.FAILURE)
        failed = RedirectResponse(f"{base}/login.html?error=oauth", status_code=303)
        cookies.clear_oauth_verifier(failed)
        return failed

    if code is None or not verifier:
        # The provider's text is attacker-controlled, so it is summarised, never
        # interpolated: a newline in it would forge entries in a plaintext log.
        logger.info(
            "OAuth callback without a usable code (provider error: %s)",
            _log_safe(error or error_description),
        )
        return back_to_login()

    try:
        auth_session = await service.exchange_code(code, verifier)
    except AuthError as exchange_error:
        # OAuthExchangeFailed plus the provider-unavailable case: from the browser's
        # point of view both are the same dead end.
        logger.warning("OAuth code exchange failed: %s", exchange_error)
        return back_to_login()

    profile = await _profile_or_completed(db, auth_session)

    logger.info("Signed in %s %s via OAuth", profile.role, profile.id)
    metrics.record_auth_event(metrics.AUTH_OAUTH_CALLBACK)
    response = RedirectResponse(f"{base}{_home_of(profile)}", status_code=303)
    cookies.clear_oauth_verifier(response)
    cookies.set_session_cookies(response, auth_session)
    return response
