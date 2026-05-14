@echo off
chcp 65001 >nul
title SmartSelect 启动中...

cd /d "%~dp0"

:: 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先执行：
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements-server.txt
    pause
    exit /b 1
)

:: 检查端口 8000 是否已在运行
netstat -an | find "0.0.0.0:8000" >nul 2>&1
if %errorlevel%==0 (
    echo [提示] SmartSelect 服务已在运行，直接打开浏览器...
    goto OPEN_BROWSER
)

:: 启动 FastAPI 后台服务
echo [1/2] 启动 SmartSelect 服务...
set PYTHONPATH=%~dp0
start "" /b "venv\Scripts\python.exe" "server\app.py"

:: 等待服务就绪（最多 15 秒）
echo [2/2] 等待服务就绪...
set /a tries=0
:WAIT_LOOP
timeout /t 1 /noisy >nul
set /a tries+=1
netstat -an | find "0.0.0.0:8000" >nul 2>&1
if %errorlevel%==0 goto OPEN_BROWSER
if %tries% lss 15 goto WAIT_LOOP
echo [警告] 服务启动超时，尝试直接打开浏览器...

:OPEN_BROWSER
echo 打开浏览器 http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
exit /b 0
