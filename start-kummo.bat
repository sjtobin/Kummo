@echo off
REM ============================================================
REM  Start Kummo locally (Windows).
REM  Usage: start-kummo.bat [local|prod]
REM    env = local (default) ^| prod ^| no other .env.^<name^> yet
REM  For "local": starts Supabase (Docker) if not already running,
REM  then starts a web server and opens the browser.
REM  Stop it with Ctrl+C (or by closing this window).
REM  (User-facing messages below are in English.)
REM ============================================================
setlocal
cd /d "%~dp0"

set "ENV=%~1"
if "%ENV%"=="" set "ENV=local"
set "ENV_FILE=.env.%ENV%"

if not exist "%ENV_FILE%" (
  echo.
  echo Environment file '%ENV_FILE%' not found.
  echo Available environments:
  for %%f in (.env.*) do echo   - %%f
  echo.
  pause
  exit /b 1
)

REM Read credentials for the FastAPI backend
set "SUPABASE_URL="
set "SUPABASE_API_KEY="
set "DATABASE_URL="
set "SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID="
set "SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET="
set "RESEND_API_KEY="
set "APP_BASE_URL="
set "COOKIE_SECURE="
set "LOG_LEVEL="
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
  if "%%a"=="SUPABASE_URL" set "SUPABASE_URL=%%b"
  if "%%a"=="SUPABASE_API_KEY" set "SUPABASE_API_KEY=%%b"
  if "%%a"=="DATABASE_URL" set "DATABASE_URL=%%b"
  if "%%a"=="SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID" set "SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=%%b"
  if "%%a"=="SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET" set "SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=%%b"
  if "%%a"=="RESEND_API_KEY" set "RESEND_API_KEY=%%b"
  if "%%a"=="APP_BASE_URL" set "APP_BASE_URL=%%b"
  if "%%a"=="COOKIE_SECURE" set "COOKIE_SECURE=%%b"
  if "%%a"=="LOG_LEVEL" set "LOG_LEVEL=%%b"
)

for %%v in (SUPABASE_URL SUPABASE_API_KEY DATABASE_URL APP_BASE_URL COOKIE_SECURE LOG_LEVEL) do (
  if not defined %%v (
    echo.
    echo %%v is missing in '%ENV_FILE%'.
    echo See backend\.env.example for the expected keys.
    echo.
    pause
    exit /b 1
  )
)

REM --- Environment safety checks ---
REM Only local and prod are supported.
if /I "%ENV%"=="local" goto :check_local
if /I "%ENV%"=="prod" goto :check_prod

echo ERROR: Environment must be local or prod.
pause
exit /b 1

:check_local
if not "%SUPABASE_URL%"=="http://127.0.0.1:54321" goto :invalid_local
if not "%APP_BASE_URL%"=="http://localhost:8000" goto :invalid_local
if /I not "%COOKIE_SECURE%"=="false" goto :invalid_local
goto :check_database

:check_prod
if not "%SUPABASE_URL%"=="https://xusuvidhmuyzpfrtxutd.supabase.co" goto :invalid_prod
if not "%APP_BASE_URL%"=="https://kummo.fun" goto :invalid_prod
if /I not "%COOKIE_SECURE%"=="true" goto :invalid_prod
goto :check_database

:check_database
REM Use PowerShell to inspect DATABASE_URL without expanding its
REM potentially sensitive or CMD-special characters into batch commands.
powershell -NoProfile -NonInteractive -Command "$d=$env:DATABASE_URL; if ($env:ENV -eq 'local') { if ($d -notmatch '127\.0\.0\.1:54322') { exit 1 } } else { if ($d -notlike 'postgresql+asyncpg://*' -or $d -match '(?i)(127\.0\.0\.1|localhost|REPLACE_WITH|YOUR_PASSWORD|HOSTED_DB_PASSWORD)') { exit 1 } }; exit 0"

if errorlevel 1 goto :invalid_database
goto :environment_valid

:invalid_local
echo ERROR: Local environment configuration is incorrect.
echo Check SUPABASE_URL, APP_BASE_URL and COOKIE_SECURE.
pause
exit /b 1

:invalid_prod
echo ERROR: Production environment configuration is incorrect.
echo Check SUPABASE_URL, APP_BASE_URL and COOKIE_SECURE.
pause
exit /b 1

:invalid_database
echo ERROR: DATABASE_URL is inconsistent with the selected environment.
echo Check the database host and unresolved placeholders.
pause
exit /b 1

:environment_valid
echo Environment: %ENV%


REM --- Supabase (local only) ---
set "STARTED_SUPABASE=false"
if "%ENV%"=="local" (
  REM Stop any existing (possibly unhealthy) Supabase containers first
  pnpm exec supabase stop >nul 2>&1
  echo Starting local Supabase instance ...
  pnpm exec supabase start
  if errorlevel 1 goto :supabase_failed
  set "STARTED_SUPABASE=true"
)

goto :backend

:supabase_failed
echo.
echo Failed to start the local Supabase instance.
echo.
pause
exit /b 1

:backend
REM --- FastAPI backend ---
set "PORT=8000"
set "URL=http://localhost:%PORT%"

where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/
  echo.
  pause
  exit /b 1
)

REM `supabase start` above already applies pending migrations on a fresh stack; this
REM also covers a stack whose volume survived from an earlier checkout.
if "%ENV%"=="local" (
  echo Applying database migrations ...
  pnpm exec supabase migration up
  if errorlevel 1 (
    echo ERROR: Local database migrations failed.
    pnpm exec supabase stop >nul 2>&1
    pause
    exit /b 1
  )
)

REM Wait briefly in the background, then open the browser.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start %URL%"

echo.
echo Kummo is running at %URL%
echo Press Ctrl+C to stop.
echo.

echo Starting Kummo ...
if "%ENV%"=="local" (
  uv --directory backend run fastapi dev src\kummo\main.py --port %PORT%
) else (
  uv --directory backend run fastapi run src\kummo\main.py --port %PORT%
)

REM Stop Supabase on exit only if we started it.
if "%STARTED_SUPABASE%"=="true" (
  echo.
  echo Stopping Supabase ...
  pnpm exec supabase stop >nul 2>&1
)

endlocal
