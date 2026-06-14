@echo off
title YouTube Music Manager
cd /d "%~dp0"
echo.
echo  Starting YouTube Music Manager...
echo  Keep this window open while you listen.
echo  Close it or press Ctrl+C to stop.
echo.
python manager.py
echo.
pause
