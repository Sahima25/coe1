@echo off
title GCE Salem COE Portal Server
color 0A

echo ===================================================
echo     GCE SALEM COE PORTAL SERVER IS RUNNING
echo ===================================================
echo.
echo Please DO NOT close this black window while using the portal.
echo To turn off the portal, simply close this window.
echo.

:: Get current folder
cd /d "%~dp0"

:: Open the default web browser to the dashboard
start http://localhost:5000

:: Start the Python application
python app.py

pause