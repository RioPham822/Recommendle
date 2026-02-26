@echo off
set "ROOT=%~dp0"

echo Stopping Recommendle services...
echo.

cd /d "%ROOT%"

echo [1/2] Stopping backend + postgres + frontend containers...
docker compose --profile local-frontend down
if errorlevel 1 (
  echo Failed to stop one or more services.
  exit /b 1
)

echo [2/2] Verifying services are down...
docker compose ps

echo.
echo Done. Backend, postgres, and frontend are stopped.
