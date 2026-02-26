@echo off
set "ROOT=%~dp0"
echo Starting Recommendle...
echo.

echo [1/3] Starting Backend in Docker (postgres + backend)...
cd /d "%ROOT%"
docker compose up --build -d postgres backend
if errorlevel 1 (
  echo Failed to start backend services in Docker.
  exit /b 1
)

echo [2/3] Seeding fountain pens dataset...
docker compose exec backend python -m scripts.load_db
if errorlevel 1 (
  echo Failed to load dataset. Check: docker compose logs backend
  exit /b 1
)

echo [3/3] Starting Frontend in Docker (local-frontend profile)...
docker compose --profile local-frontend up --build -d frontend
if errorlevel 1 (
  echo Failed to start frontend container.
  exit /b 1
)

timeout /t 3 /nobreak >nul

echo.
echo ===================================
echo   Backend (Docker):  http://localhost:8015
echo   Frontend (Docker): http://localhost:5173
echo ===================================
echo.
echo To stop backend containers: docker compose down
echo To stop all containers: docker compose down
