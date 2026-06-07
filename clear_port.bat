@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PROJECT_DIR=%cd%"
set "FRONTEND_PORT=3000"
call "%PROJECT_DIR%\tools\load_windows_env.bat"

echo ========================================
echo     LFBot 端口清理和启动工具
echo ========================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠️  建议以管理员身份运行此脚本
    echo.
)

echo [1/4] 检查后端端口 %BACKEND_PORT% 占用情况...
netstat -ano | findstr :%BACKEND_PORT%

echo.
echo [2/4] 清理后端端口占用进程...

REM 查找并停止占用后端端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%BACKEND_PORT% ^| findstr LISTENING') do (
    echo    停止进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo [3/4] 检查前端端口 %FRONTEND_PORT% 占用情况...
netstat -ano | findstr :%FRONTEND_PORT%

echo.
echo [4/4] 清理前端端口占用进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%FRONTEND_PORT% ^| findstr LISTENING') do (
    echo    停止进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo 等待端口释放...
timeout /t 2 /nobreak >nul

REM 最终检查
echo.
echo 清理后的后端端口状态:
netstat -ano | findstr :%BACKEND_PORT%
echo.
echo 清理后的前端端口状态:
netstat -ano | findstr :%FRONTEND_PORT%

echo.
echo ========================================
echo ✅ 端口清理完成！
echo.
echo 现在可以运行以下命令启动后端:
echo    python run.py
echo.
echo 或者运行启动脚本:
echo    oncestart.bat  ^(中文版^)
echo    start.bat      ^(英文版^)
echo    start_frontend.bat ^(仅前端^)
echo ========================================
echo.
pause
