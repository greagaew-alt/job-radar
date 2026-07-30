@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Nastroyka radara vakansiy

set PY=
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%PROGRAMFILES%\Python312\python.exe" "C:\Python313\python.exe" "C:\Python312\python.exe" "C:\Python311\python.exe") do (
  if exist %%P set PY=%%P
)

if "!PY!"=="" (
  echo.
  echo   Python ne nayden na kompyutere.
  echo   Skachay: https://www.python.org/downloads/
  echo   Pri ustanovke postav galochku "Add Python to PATH"
  echo.
  pause
  exit /b 1
)

!PY! -c "import requests" 2>nul
if errorlevel 1 (
  echo.
  echo   Stavlyu biblioteku, podozhdi polminuty...
  !PY! -m pip install -r requirements.txt --quiet --disable-pip-version-check
)

!PY! setup.py

pause
