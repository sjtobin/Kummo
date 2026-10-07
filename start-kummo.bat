@echo off
REM ============================================================
REM  Start Kummo locally (Windows).
REM  Usage: start-kummo.bat [env]
REM    env = local (default) ^| prod ^| any .env.^<name^> file
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
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
  if "%%a"=="SUPABASE_URL" set "SUPABASE_URL=%%b"
  if "%%a"=="SUPABASE_API_KEY" set "SUPABASE_API_KEY=%%b"
  if "%%a"=="DATABASE_URL" set "DATABASE_URL=%%b"
  if "%%a"=="SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID" set "SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=%%b"
  if "%%a"=="SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET" set "SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=%%b"
  if "%%a"=="RESEND_API_KEY" set "RESEND_API_KEY=%%b"
)

for %%v in (SUPABASE_URL SUPABASE_API_KEY DATABASE_URL) do (
  if not defined %%v (
    echo.
    echo %%v is missing in '%ENV_FILE%'.
    echo See backend\.env.example for the expected keys.
    echo.
    pause
    exit /b 1
  )
)

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
