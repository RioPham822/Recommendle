@echo off
echo Starting Recommendle...
echo.

echo [1/2] Starting Backend (port 8015)...
start "Recommendle Backend" cmd /k "cd backend && python -m uvicorn app.main:app --host localhost --port 8015 --reload"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend (port 5173)...
start "Recommendle Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 3 /nobreak >nul

echo.
echo ===================================
echo   Backend:  http://localhost:8015
echo   Frontend: http://localhost:5173
echo ===================================
echo.
echo Both servers are running in separate windows.
echo Close those windows to stop the servers.
