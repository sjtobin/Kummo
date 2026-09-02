from functools import lru_cache
from pathlib import Path

from pydantic import DirectoryPath, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase Auth (GoTrue). Application data no longer goes through PostgREST,
    # but identity still does.
    supabase_url: str
    supabase_api_key: str

    # Runtime connection, as the DML-only `kummo_app` role. The backend never does
    # DDL -- schema changes are Supabase CLI migrations, applied out of band.
    database_url: str

    # Where this app is served. Used to build the OAuth callback URL and to decide
    # where to send the browser after a provider redirect.
    app_base_url: str = "http://localhost:8000"
    # Session cookies are HttpOnly always; Secure only where there is TLS to require.
    cookie_secure: bool = False

    # Absolute path to the site served at /. Defaults to the repo's static/, which is
    # where a source checkout keeps it; override with STATIC_DIR wherever a deployment
    # lays it out elsewhere (the container puts it at /app/static). DirectoryPath
    # validates it exists, so a wrong path fails at startup instead of serving 404s.
    static_dir: DirectoryPath = Path(__file__).resolve().parents[3] / "static"

    # Root log level. DEBUG is loud — SQLAlchemy and httpx both talk at that level.
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _require_secure_cookies_over_tls(self) -> "Settings":
        """Refuse to serve session cookies unprotected over a TLS deployment.

        The default is False so that plain-HTTP local development works, which means a
        deployment that forgets COOKIE_SECURE would otherwise ship access and refresh
        tokens in cleartext and say nothing. Failing at startup is the loud version.
        """
        if self.app_base_url.startswith("https://") and not self.cookie_secure:
            raise ValueError(
                "APP_BASE_URL is https, so COOKIE_SECURE must be true — "
                "otherwise the session cookies are sent without the Secure flag."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
