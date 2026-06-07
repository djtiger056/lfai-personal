@echo off
setlocal

if not defined PROJECT_DIR (
    for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
)

if not defined FRONTEND_PORT (
    set "FRONTEND_PORT=3000"
)

set "DEFAULT_BACKEND_PORT=8003"
set "BACKEND_PORT=%DEFAULT_BACKEND_PORT%"
set "CONFIG_PATH=%PROJECT_DIR%\config.yaml"
set "PORT_READER="

if exist "%PROJECT_DIR%\venv\Scripts\python.exe" (
    set "PORT_READER="%PROJECT_DIR%\venv\Scripts\python.exe""
) else (
    where py >nul 2>&1
    if not errorlevel 1 (
        set "PORT_READER=py -3"
    ) else (
        where python >nul 2>&1
        if not errorlevel 1 (
            set "PORT_READER=python"
        )
    )
)

if defined PORT_READER (
    for /f "usebackq delims=" %%I in (`%PORT_READER% "%PROJECT_DIR%\tools\get_server_port.py" "%CONFIG_PATH%" 2^>nul`) do (
        if not "%%~I"=="" set "BACKEND_PORT=%%~I"
    )
)

if not defined BACKEND_PORT (
    set "BACKEND_PORT=%DEFAULT_BACKEND_PORT%"
)

set "BACKEND_HEALTH_URL=http://127.0.0.1:%BACKEND_PORT%/api/health"
set "VITE_PORT=%FRONTEND_PORT%"
set "VITE_API_TARGET=http://127.0.0.1:%BACKEND_PORT%"
set "VITE_WS_TARGET=ws://127.0.0.1:%BACKEND_PORT%"

endlocal & (
    set "PROJECT_DIR=%PROJECT_DIR%"
    set "FRONTEND_PORT=%FRONTEND_PORT%"
    set "BACKEND_PORT=%BACKEND_PORT%"
    set "BACKEND_HEALTH_URL=%BACKEND_HEALTH_URL%"
    set "VITE_PORT=%VITE_PORT%"
    set "VITE_API_TARGET=%VITE_API_TARGET%"
    set "VITE_WS_TARGET=%VITE_WS_TARGET%"
)
exit /b 0
