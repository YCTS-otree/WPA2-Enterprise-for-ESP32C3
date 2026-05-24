@echo off
setlocal EnableExtensions
chcp 65001 >nul
if "%~1"=="" (
  echo 用法：flash_firmware.bat COM端口
  echo 示例：flash_firmware.bat COM73
  pause
  exit /b 1
)
set PORT=%~1
set FW=%~dp0output\firmware.bin
if not exist "%FW%" (
  echo [ERROR] 找不到 %FW%
  echo 请先运行 local_wsl_build.bat 或从 GitHub Actions 下载 firmware.bin 放到 output\firmware.bin
  pause
  exit /b 1
)
python -m esptool --port %PORT% erase_flash
if errorlevel 1 goto fail
python -m esptool --port %PORT% --baud 460800 write_flash 0x0 "%FW%"
if errorlevel 1 goto fail
echo [OK] 烧录完成。
pause
exit /b 0
:fail
echo [ERROR] 烧录失败。若 460800 不稳，可手动改成 115200；C3 SuperMini 必要时按住 BOOT 再插 USB。
pause
exit /b 1
