@echo off
title NexusAI Start
cd /d "%~dp0"

echo.
echo  ============================================
echo   NexusAI 启动
echo  ============================================
echo.
echo   [1] 开发模式（推荐，HMR 热更新，改代码即生效）
echo       - Docker 只跑数据服务（PG/Redis/Chroma）
echo       - backend / celery / frontend 本地启动到独立窗口
echo       - 前端: http://localhost:5173
echo.
echo   [2] Docker 模式（全部容器化，适合演示）
echo       - docker compose up -d，6 个服务统一编排
echo       - 前端: http://localhost
echo       - 需要 .env 配置好 LLM API key
echo.
set /p mode="请选择启动模式（默认 1）: "
if "%mode%"=="" set mode=1
if "%mode%"=="1" goto dev_start
if "%mode%"=="2" goto docker_start
echo 无效选项，使用默认开发模式
goto dev_start

REM ==============================================
REM   开发模式
REM ==============================================
:dev_start
echo.
echo === 启动开发模式 ===
echo.

echo [1/4] 启动 Docker 数据容器（PostgreSQL / Redis / Chroma）...
docker start nexus-postgres nexus-redis nexus-chroma 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] 启动 FastAPI 后端...
start "NexusAI Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe main.py"
timeout /t 2 /nobreak >nul

echo [3/4] 启动 Celery Worker...
start "NexusAI Celery" cmd /k "cd /d %~dp0backend && .venv\Scripts\celery.exe -A app.tasks.celery_app worker --loglevel=info --pool=solo"
timeout /t 2 /nobreak >nul

echo [4/4] 启动 Vue 前端...
start "NexusAI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo  ============================================
echo   开发模式已启动！等 ~10 秒后访问：
echo     前端: http://localhost:5173
echo     后端: http://localhost:8002/docs
echo  ============================================
echo.
echo  3 秒后自动打开浏览器...
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo  本窗口可以关闭。要停止服务请双击 stop.bat
pause
exit /b 0

REM ==============================================
REM   Docker 模式
REM ==============================================
:docker_start
echo.
echo === 启动 Docker 模式 ===
echo.

if not exist ".env" (
    echo  ? 未找到 .env 文件！
    echo     请先执行：copy .env.example .env
    echo     然后编辑 .env 填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY
    echo.
    pause
    exit /b 1
)

REM 检查开发模式端口冲突
powershell -NoProfile -Command "$ports=@(80,8002,5173); $busy=$ports | Where-Object { Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue | Where-Object {$_.State -eq 'Listen'} }; if ($busy) { Write-Host ('  ??  以下端口被占用: ' + ($busy -join ', ')) -ForegroundColor Yellow; Write-Host '     可能开发模式或上次的容器还在跑。可以先 stop.bat 清理一下' -ForegroundColor Yellow; Write-Host '' }"

echo 构建并启动所有容器（首次需 3-5 分钟）...
docker compose up -d --build

if errorlevel 1 (
    echo.
    echo  ? Docker 启动失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Docker 模式已启动！等 ~30 秒等容器健康检查通过：
echo     前端 UI:    http://localhost
echo     后端文档:   http://localhost:8002/docs
echo     ChromaDB:   http://localhost:8001
echo.
echo   查看实时日志: docker compose logs -f
echo   停止服务:     stop.bat
echo  ============================================
echo.
echo  10 秒后自动打开浏览器...
timeout /t 10 /nobreak >nul
start "" "http://localhost"

echo.
pause
