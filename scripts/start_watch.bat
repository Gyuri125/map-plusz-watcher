@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
python -m allampapir_ertesito watch --config "%~dp0..\config.toml" --interval-minutes 60
pause
