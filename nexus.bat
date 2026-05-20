@echo off
REM 本文件保存为 GBK 编码
title NexusAI 控制台
cd /d "%~dp0"

:menu
cls
echo.
echo  ============================================
echo            NexusAI 项目控制台
echo  ============================================
echo.
echo   --- 开发模式 [HMR 热更新, 改代码即生效] ---
echo   [1] 启动开发模式 [Docker 数据服务 + 本地 backend/celery/frontend]
echo   [2] 停止开发模式
echo   [3] 仅重启后端+Worker [改 .env 或 Celery 代码用]
echo.
echo   --- Docker 模式 [全部容器化] ---
echo   [4] 启动 Docker 模式 [docker compose up -d]
echo   [5] 停止 Docker 模式 [docker compose down]
echo   [6] 查看 Docker 服务日志 [实时]
echo.
echo   --- 工具 ---
echo   [7] 查看所有服务状态
echo   [8] 打开浏览器
echo   [0] 退出
echo.
echo  ============================================
echo.
set /p choice="请输入选项: "

if "%choice%"=="1" goto dev_start
if "%choice%"=="2" goto dev_stop
if "%choice%"=="3" goto dev_restart_backend
if "%choice%"=="4" goto docker_up
if "%choice%"=="5" goto docker_down
if "%choice%"=="6" goto docker_logs
if "%choice%"=="7" goto status
if "%choice%"=="8" goto open_browser
if "%choice%"=="0" exit /b 0
goto menu

REM ==============================================
REM   开发模式：启动
REM ==============================================
:dev_start

echo.
echo  [1/4] 启动 Docker 数据服务 [PostgreSQL + Redis + ChromaDB] ...
docker compose up -d postgres redis chroma

if errorlevel 1 (
    echo  [X] Docker 数据服务启动失败！请确认 Docker Desktop 已运行。
    pause
    goto menu
)

echo  [OK] 数据服务已启动

REM 等待 PostgreSQL 就绪
echo  [2/4] 等待 PostgreSQL 就绪...
:wait_pg
powershell -NoProfile -Command "Start-Sleep -Seconds 2"
docker compose exec postgres pg_isready -U nexus >nul 2>&1
if errorlevel 1 goto wait_pg
echo  [OK] PostgreSQL 就绪

echo  [3/4] 启动后端服务...

REM 检查虚拟环境
if not exist "backend\.venv\Scripts\activate.bat" (
    echo  [!] 未找到虚拟环境，请先执行: cd backend ^& python -m venv .venv ^& pip install -r requirements.txt
    pause
    goto menu
)

REM 启动 Backend
start "NexusAI-Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8002 --reload"

REM 启动 Celery Worker
start "NexusAI-Celery" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate.bat && celery -A app.tasks.celery_app worker --loglevel=info --pool=solo"

echo  [OK] 后端 + Celery Worker 已在新窗口启动

echo  [4/4] 启动前端开发服务器...

REM 检查 node_modules
if not exist "frontend\node_modules" (
    echo  [!] 未找到 node_modules，请先执行: cd frontend ^& npm install
    pause
    goto menu
)

start "NexusAI-Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo  [OK] 前端开发服务器已在新窗口启动
echo.
echo  ============================================
echo   全部启动完成！
echo     前端 UI:    http://localhost:5173
echo     后端文档:   http://localhost:8002/docs
echo     ChromaDB:   http://localhost:8001
echo  ============================================
echo.
pause
goto menu

REM ==============================================
REM   开发模式：停止
REM ==============================================
:dev_stop

echo.
echo  正在停止所有服务...

taskkill /FI "WINDOWTITLE eq NexusAI-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq NexusAI-Celery*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq NexusAI-Frontend*" /F >nul 2>&1

docker compose stop postgres redis chroma >nul 2>&1

echo  [OK] 所有服务已停止
echo.
pause
goto menu

REM ==============================================
REM   开发模式：仅重启后端
REM ==============================================
:dev_restart_backend

echo.
echo  正在重启后端 + Celery Worker...

taskkill /FI "WINDOWTITLE eq NexusAI-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq NexusAI-Celery*" /F >nul 2>&1

powershell -NoProfile -Command "Start-Sleep -Seconds 1"

start "NexusAI-Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8002 --reload"
start "NexusAI-Celery" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate.bat && celery -A app.tasks.celery_app worker --loglevel=info --pool=solo"

echo  [OK] 后端 + Celery Worker 已重启
echo.
pause
goto menu

REM ==============================================
REM   Docker 模式：启动
REM ==============================================
:docker_up

echo.

REM 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo  [X] Docker Desktop 未运行！请先启动 Docker Desktop。
    pause
    goto menu
)

REM 检查 .env 是否存在
if not exist ".env" (
    echo  [!] 未找到 .env 文件！Docker 模式必须配置 LLM API key。
    echo     1. 复制模板: copy .env.example .env
    echo     2. 编辑 .env，填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY
    echo.
    pause
    goto menu
)

REM 检查端口冲突
powershell -NoProfile -Command "$ports=@(80,8002,5173); $busy=$ports | Where-Object { Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue | Where-Object {$_.State -eq 'Listen'} }; if ($busy) { Write-Host ('  [!] 以下端口被占用: ' + ($busy -join ', ')) -ForegroundColor Yellow; Write-Host '     建议先选 [2] 停止开发模式后再启动 Docker' -ForegroundColor Yellow }"

echo.
echo  清理可能残留的同名容器...
docker compose down --remove-orphans >nul 2>&1
echo  构建并启动所有容器 [首次需 3-5 分钟] ...
docker compose up -d --build

if errorlevel 1 (
    echo  [X] Docker 启动失败，请检查上方错误信息。
    pause
    goto menu
)

echo.
echo  ============================================
echo   Docker 模式已启动！等约30秒等容器就绪：
echo     前端 UI:    http://localhost
echo     后端文档:   http://localhost:8002/docs
echo     ChromaDB:   http://localhost:8001
echo.
echo   查看日志: 选 [6]
echo  ============================================
echo.
pause
goto menu

REM ==============================================
REM   Docker 模式：停止
REM ==============================================
:docker_down

echo.
echo  正在停止并移除所有 Docker 容器...
docker compose down

echo  [OK] Docker 模式已停止
echo.
pause
goto menu

REM ==============================================
REM   Docker 日志
REM ==============================================
:docker_logs

echo.
echo  按 Ctrl+C 退出日志查看
echo.
docker compose logs -f --tail=100
pause
goto menu

REM ==============================================
REM   查看状态
REM ==============================================
:status

echo.
echo  --- Docker 容器状态 ---
docker compose ps 2>nul

echo.
echo  --- 开发模式进程 ---
powershell -NoProfile -Command "$procs = @('uvicorn','celery','node'); foreach ($p in $procs) { $found = Get-Process -Name $p -ErrorAction SilentlyContinue; if ($found) { Write-Host ('  [运行中] ' + $p) -ForegroundColor Green } else { Write-Host ('  [未运行] ' + $p) -ForegroundColor Gray } }"

echo.
pause
goto menu

REM ==============================================
REM   打开浏览器
REM ==============================================
:open_browser

echo.
echo  正在打开浏览器...

powershell -NoProfile -Command "$dev = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Where-Object {$_.State -eq 'Listen'}; if ($dev) { Start-Process 'http://localhost:5173' } else { Start-Process 'http://localhost' }"

echo  [OK] 已打开
echo.
pause
goto menu