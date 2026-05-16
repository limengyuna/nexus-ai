$content = @"
@echo off
title NexusAI 控制台
cd /d "%~dp0"

:menu
cls
echo.
echo  ============================================
echo            NexusAI 项目控制台
echo  ============================================
echo.
echo   --- 开发模式(HMR 热更新,改代码即生效) ---
echo   [1] 启动开发模式(Docker 数据服务 + 本地 backend/celery/frontend)
echo   [2] 停止开发模式
echo   [3] 仅重启后端+Worker(改 .env 或 Celery 代码用)
echo.
echo   --- Docker 模式(全部容器化,适合演示/面试) ---
echo   [4] 启动 Docker 模式(docker compose up -d)
echo   [5] 停止 Docker 模式(docker compose down)
echo   [6] 查看 Docker 服务日志(实时)
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
REM   开发模式: 启动全部
REM ==============================================
:dev_start
echo.
REM 检查 Docker 模式是否在跑
powershell -NoProfile -Command "`$c80 = Get-NetTCPConnection -LocalPort 80 -ErrorAction SilentlyContinue | Where-Object {`$_.State -eq 'Listen'}; if (`$c80) { Write-Host '  [!] 端口 80 被占用,可能 Docker 模式正在运行' -ForegroundColor Yellow; Write-Host '     建议先选 [5] 停止 Docker 模式' -ForegroundColor Yellow }"

echo [1/4] 启动 Docker 数据容器(PostgreSQL / Redis / Chroma)...
docker start nexus-postgres nexus-redis nexus-chroma 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] 启动 FastAPI 后端(独立窗口)...
start "NexusAI Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe main.py"
timeout /t 2 /nobreak >nul

echo [3/4] 启动 Celery Worker(独立窗口)...
start "NexusAI Celery" cmd /k "cd /d %~dp0backend && .venv\Scripts\celery.exe -A app.tasks.celery_app worker --loglevel=info --pool=solo"
timeout /t 2 /nobreak >nul

echo [4/4] 启动 Vue 前端(独立窗口)...
start "NexusAI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo  ============================================
echo   开发模式已启动。等 ~10 秒后访问:
echo     前端 (Vite HMR): http://localhost:5173
echo     后端文档:        http://localhost:8002/docs
echo  ============================================
echo.
pause
goto menu

REM ==============================================
REM   开发模式: 停止
REM ==============================================
:dev_stop
echo.
echo 停止后端(端口 8002)...
powershell -NoProfile -Command "`$c = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue; if (`$c) { `$c.OwningProcess | Sort-Object -Unique | ForEach-Object { taskkill /F /PID `$_ /T 2>`$null | Out-Null } }"

echo 停止前端(端口 5173)...
powershell -NoProfile -Command "`$c = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue; if (`$c) { `$c.OwningProcess | Sort-Object -Unique | ForEach-Object { taskkill /F /PID `$_ /T 2>`$null | Out-Null } }"

echo 停止 Celery Worker...
powershell -NoProfile -Command "Get-Process -Name celery -ErrorAction SilentlyContinue | Stop-Process -Force"

echo.
echo  已停止开发模式的 backend / frontend / celery。
echo  Docker 数据容器(postgres/redis/chroma)保持运行。
echo.
pause
goto menu

REM ==============================================
REM   开发模式: 仅重启后端 + Worker
REM ==============================================
:dev_restart_backend
echo.
echo 停止后端 + Celery...
powershell -NoProfile -Command "`$c = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue; if (`$c) { `$c.OwningProcess | Sort-Object -Unique | ForEach-Object { taskkill /F /PID `$_ /T 2>`$null | Out-Null } }; Get-Process -Name celery -ErrorAction SilentlyContinue | Stop-Process -Force"
timeout /t 2 /nobreak >nul

echo 启动 FastAPI 后端...
start "NexusAI Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe main.py"
timeout /t 2 /nobreak >nul

echo 启动 Celery Worker...
start "NexusAI Celery" cmd /k "cd /d %~dp0backend && .venv\Scripts\celery.exe -A app.tasks.celery_app worker --loglevel=info --pool=solo"

echo.
echo  后端 + Worker 已重启(前端保持 HMR)。
echo.
pause
goto menu

REM ==============================================
REM   Docker 模式: 启动
REM ==============================================
:docker_up
echo.
REM 检查 .env 是否存在
if not exist ".env" (
    echo  [!] 未找到 .env 文件! Docker 模式必须配置 LLM API key。
    echo     1. 复制模板: copy .env.example .env
    echo     2. 编辑 .env,填入 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY
    echo.
    pause
    goto menu
)

REM 检查开发模式端口冲突
powershell -NoProfile -Command "`$ports=@(80,8002,5173); `$busy=`$ports | Where-Object { Get-NetTCPConnection -LocalPort `$_ -ErrorAction SilentlyContinue | Where-Object {`$_.State -eq 'Listen'} }; if (`$busy) { Write-Host ('  [!] 以下端口被占用: ' + (`$busy -join ', ')) -ForegroundColor Yellow; Write-Host '     建议先选 [2] 停止开发模式后再启动 Docker' -ForegroundColor Yellow }"

echo.
echo 构建并启动所有容器(首次需 3-5 分钟)...
docker compose up -d --build

if errorlevel 1 (
    echo  [X] Docker 启动失败,请检查上方错误信息。
    pause
    goto menu
)

echo.
echo  ============================================
echo   Docker 模式已启动! 等 ~30 秒等容器就绪:
echo     前端 UI:    http://localhost
echo     后端文档:   http://localhost:8002/docs
echo     ChromaDB:   http://localhost:8001
echo.
echo   查看日志: docker compose logs -f
echo   实时状态: 选菜单 [7]
echo  ============================================
echo.
pause
goto menu

REM ==============================================
REM   Docker 模式: 停止
REM ==============================================
:docker_down
echo.
echo 停止并移除所有 Docker compose 容器...
docker compose down

echo.
echo  已停止 Docker 模式。
echo  数据卷(postgres/redis/chroma)已保留,下次启动数据不丢。
echo  如要彻底清理数据卷: docker compose down -v
echo.
pause
goto menu

REM ==============================================
REM   Docker 模式: 实时日志
REM ==============================================
:docker_logs
echo.
echo 显示所有 Docker compose 服务的实时日志(Ctrl+C 退出)...
echo.
docker compose logs -f --tail=50
echo.
pause
goto menu

REM ==============================================
REM   状态查看(开发模式 + Docker 模式)
REM ==============================================
:status
echo.
echo === Docker 容器 ===
docker ps --filter "name=nexus" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo.
echo === 端口监听(区分模式) ===
powershell -NoProfile -Command "@(@{Port=80;Name='Docker Frontend'},@{Port=5173;Name='Dev Frontend'},@{Port=8002;Name='Backend'},@{Port=8001;Name='Chroma'},@{Port=5432;Name='PostgreSQL'},@{Port=6379;Name='Redis'}) | ForEach-Object { `$line = (netstat -ano | findstr (':'+`$_.Port+' ') | findstr 'LISTENING' | Select-Object -First 1); if (`$line) { Write-Host ('  [OK]   Port ' + `$_.Port.ToString().PadRight(5) + ' ' + `$_.Name) -ForegroundColor Green } else { Write-Host ('  [DOWN] Port ' + `$_.Port.ToString().PadRight(5) + ' ' + `$_.Name) -ForegroundColor DarkGray } }"
echo.
echo === Celery Worker 进程(仅开发模式) ===
powershell -NoProfile -Command "`$p = Get-Process -Name celery -ErrorAction SilentlyContinue; if (`$p) { Write-Host ('  [OK]   Celery Worker (PID=' + `$p.Id + ')') -ForegroundColor Green } else { Write-Host '  [DOWN] Celery Worker' -ForegroundColor DarkGray }"
echo.
pause
goto menu

REM ==============================================
REM   打开浏览器(智能识别当前是哪种模式)
REM ==============================================
:open_browser
echo.
REM 优先打开 Docker 模式的 80 端口; 否则打开开发模式的 5173
powershell -NoProfile -Command "`$c80 = Get-NetTCPConnection -LocalPort 80 -ErrorAction SilentlyContinue | Where-Object {`$_.State -eq 'Listen'}; if (`$c80) { Start-Process 'http://localhost' } else { Start-Process 'http://localhost:5173' }"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8002/docs"
goto menu
"@

$path = 'c:\Users\86191\Desktop\tt\zj\ag1\nexus.bat'
$gbk = [System.Text.Encoding]::GetEncoding('gb2312')
# 确保 CRLF 行尾
$content = $content.Replace("`r`n", "`n").Replace("`n", "`r`n")
[System.IO.File]::WriteAllText($path, $content, $gbk)
Write-Host "nexus.bat 已重新生成 (GBK + CRLF)"
