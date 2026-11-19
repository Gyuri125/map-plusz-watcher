@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"
python -m allampapir_ertesito check --config "%~dp0..\config.toml" >> "%~dp0..\logs\task.log" 2>&1
exit /b %ERRORLEVEL%
