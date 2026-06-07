@echo off
chcp 65001 >nul
title LFBot Frontend
cd /d "%~dp0"

set "PROJECT_DIR=%cd%"
set "FRONTEND_DIR=%PROJECT_DIR%\frontend"
set "FRONTEND_PORT=3000"
call "%PROJECT_DIR%\tools\load_windows_env.bat"

echo ========================================
echo        LFBot 前端启动
echo ========================================
echo.

if not exist "%FRONTEND_DIR%\node_modules\" (
    echo [1/3] 安装前端依赖...
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        popd
        echo [X] 前端依赖安装失败
        pause
        exit /b 1
    )
    popd
) else (
    echo [1/3] 前端依赖已存在
)

echo [2/3] 清理前端端口 %FRONTEND_PORT%...
netstat -ano 2>nul | findstr ":%FRONTEND_PORT%.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%.*LISTENING"') do (
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
    echo       已清理端口 %FRONTEND_PORT%
) else (
    echo       端口可用
)

echo [3/3] 启动前端...
start "LFBot-Frontend" /D "%FRONTEND_DIR%" cmd /k "set VITE_PORT=%VITE_PORT% && set VITE_API_TARGET=%VITE_API_TARGET% && set VITE_WS_TARGET=%VITE_WS_TARGET% && node .\scripts\vite-dev.mjs --host 0.0.0.0 --port %FRONTEND_PORT% --clearScreen false"

echo       等待前端就绪...
set /a retries=0
:wait_frontend
timeout /t 1 /nobreak >nul
set /a retries+=1
netstat -ano 2>nul | findstr ":%FRONTEND_PORT%.*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo       前端已就绪
    goto frontend_ok
)
if %retries% lss 15 goto wait_frontend
echo       [!] 前端启动超时，请查看前端窗口
:frontend_ok

echo.
echo 前端地址: http://localhost:%FRONTEND_PORT%
echo 代理后端: %VITE_API_TARGET%
echo.
set /p open_browser="打开浏览器? (Y/n): "
if /i not "%open_browser%"=="n" (
    start "" http://localhost:%FRONTEND_PORT%
)

echo.
echo 按任意键关闭此窗口...
pause >nul
