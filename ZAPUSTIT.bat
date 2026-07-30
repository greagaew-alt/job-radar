@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Radar vakansiy

set PY=
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%PROGRAMFILES%\Python312\python.exe" "C:\Python313\python.exe" "C:\Python312\python.exe" "C:\Python311\python.exe") do (
  if exist %%P set PY=%%P
)

if "!PY!"=="" (
  echo   Python ne nayden. Zapusti snachala NASTROIT.bat
  pause
  exit /b 1
)

if not exist .env (
  echo   Radar ne nastroen. Zapusti snachala NASTROIT.bat
  pause
  exit /b 1
)

!PY! main.py

pause
