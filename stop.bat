@echo off
title NexusAI Stop
cd /d "%~dp0"

echo.
echo  ============================================
echo   一键停止 NexusAI 全部服务
echo   （含开发模式 + Docker compose 服务）
echo  ============================================
echo.

echo [1/4] 停止开发模式 - 后端（端口 8002）...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue; if ($c) { $c.OwningProcess | Sort-Object -Unique | ForEach-Object { Write-Host ('    Killing PID=' + $_); taskkill /F /PID $_ /T 2>$null | Out-Null } } else { Write-Host '    (端口已空闲)' }"

echo [2/4] 停止开发模式 - 前端（端口 5173）...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue; if ($c) { $c.OwningProcess | Sort-Object -Unique | ForEach-Object { Write-Host ('    Killing PID=' + $_); taskkill /F /PID $_ /T 2>$null | Out-Null } } else { Write-Host '    (端口已空闲)' }"

echo [3/4] 停止开发模式 - Celery Worker...
powershell -NoProfile -Command "$ps = Get-Process -Name celery -ErrorAction SilentlyContinue; if ($ps) { $ps | ForEach-Object { Write-Host ('    Killing celery PID=' + $_.Id); Stop-Process -Id $_.Id -Force } } else { Write-Host '    (Worker 未运行)' }"

echo [4/4] 停止 Docker 模式 - compose 服务...
REM 只有 nexus-backend / nexus-celery / nexus-frontend 这几个 compose 创建的容器存在时才停
docker ps --filter "name=nexus-backend" --filter "name=nexus-celery" --filter "name=nexus-frontend" --format "{{.Names}}" | findstr /R "nexus-" >nul
if errorlevel 1 (
    echo     (Docker compose 模式未运行)
) else (
    docker compose down
)

echo.
echo  ============================================
echo   完成。Docker 数据容器（postgres/redis/chroma）保留运行。
echo.
echo   如需彻底停 Docker 数据容器：
echo     docker stop nexus-postgres nexus-redis nexus-chroma
echo   如需清理 Docker 数据卷（会丢数据！）：
echo     docker compose down -v
echo  ============================================
echo.
pause
