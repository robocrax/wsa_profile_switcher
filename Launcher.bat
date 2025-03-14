@echo off
setlocal enabledelayedexpansion

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH
    echo Please install Python 3.6 or later
    pause
    exit /b 1
)

:: Get the script directory
set "SCRIPT_DIR=%~dp0"

:: Check if the Python script exists
if not exist "%SCRIPT_DIR%wsa_profile_switcher.py" (
    echo wsa_profile_switcher.py not found in %SCRIPT_DIR%
    pause
    exit /b 1
)

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    :: Already running as administrator
    python "%SCRIPT_DIR%wsa_profile_switcher.py"
    exit /b %errorLevel%
) else (
    :: Not running as administrator, restart with elevation
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b %errorLevel%
) 