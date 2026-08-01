@echo off
setlocal
cd /d "%~dp0"
title Networked World v1.0.1 Professional Atlas

echo Starting Networked World v1.0.1 Professional Atlas on a free local port...
echo Do not open index.html directly: the local server also provides the read-only API proxy.
echo.

where py >nul 2>nul
if not errorlevel 1 (
  py -3 server.py --port 0
  goto :done
)

where python >nul 2>nul
if not errorlevel 1 (
  python server.py --port 0
  goto :done
)

echo Python 3 was not found.
echo Install Python, or open a terminal in this folder and run: py -3 server.py --port 0

:done
echo.
echo Server stopped.
pause
