@echo off
cd /d "%~dp0"
python pipeline.py %*
pause
