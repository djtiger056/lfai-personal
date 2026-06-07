@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PROJECT_DIR=%cd%"
set "FRONTEND_PORT=3000"
call "%PROJECT_DIR%\tools\load_windows_env.bat"

echo 正在检查并清理后端端口 %BACKEND_PORT% 和前端端口 %FRONTEND_PORT% 占用...

REM 查找占用后端端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%BACKEND_PORT% ^| findstr LISTENING') do (
    echo 找到占用后端端口 %BACKEND_PORT% 的进程 PID: %%a
    echo 正在停止进程...
    taskkill /PID %%a /F
)

REM 查找占用前端端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%FRONTEND_PORT% ^| findstr LISTENING') do (
    echo 找到占用前端端口 %FRONTEND_PORT% 的进程 PID: %%a
    echo 正在停止进程...
    taskkill /PID %%a /F
)

echo 等待端口释放...
timeout /t 2 /nobreak >nul

REM 再次检查端口状态
echo 后端端口状态:
netstat -ano | findstr :%BACKEND_PORT%
echo 前端端口状态:
netstat -ano | findstr :%FRONTEND_PORT%

echo 端口清理完成，现在可以启动整套服务了。
pause
