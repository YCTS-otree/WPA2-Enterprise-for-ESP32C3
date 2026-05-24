@echo off
setlocal EnableExtensions
chcp 65001 >nul
set ROOT=%~dp0
where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 WSL。
  echo 请先以管理员 PowerShell 运行： wsl --install -d Ubuntu
  echo 安装后重启电脑，再双击本脚本。
  pause
  exit /b 1
)
for /f "delims=" %%i in ('wsl.exe wslpath "%ROOT%"') do set WSL_ROOT=%%i
echo [INFO] 将在 WSL 中构建 MicroPython ESP32-C3 Enterprise 固件。
echo [INFO] 工作目录：%ROOT%
wsl.exe bash -lc "cd '%WSL_ROOT%' && bash scripts/build_wsl.sh"
if errorlevel 1 (
  echo.
  echo [ERROR] 构建失败。请把 work/build.log 的最后 80 行发给我。
  pause
  exit /b 1
)
echo.
echo [OK] 构建完成。固件在：output\firmware.bin
pause
