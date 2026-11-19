@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
python -m allampapir_ertesito quick --config "%~dp0..\config.toml"
if errorlevel 1 (
  echo.
  echo Hiba tortent. Nezd meg a fenti uzenetet, es ellenorizd a config.toml / .env beallitasokat.
)
pause
