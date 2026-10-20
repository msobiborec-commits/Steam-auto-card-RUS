@echo off
cd /d "%~dp0"

echo ========================================================
echo   Steam Card Auto-Farmer: SecretBall Cyber Edition
echo ========================================================
echo Searching for Python...

set "RUN_PY="
set "RUN_PYW="

REM 1. Check Python Launcher (py)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set RUN_PY=py -3
        where pyw >nul 2>&1
        if not errorlevel 1 (
            set RUN_PYW=pyw -3
        ) else (
            set RUN_PYW=py -3
        )
        goto python_ready
    )
)

REM 2. Check system PATH
for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined RUN_PY (
        echo %%I | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            "%%I" -c "import sys" >nul 2>&1
            if not errorlevel 1 (
                set RUN_PY="%%I"
                if exist "%%~dpIpythonw.exe" (
                    set RUN_PYW="%%~dpIpythonw.exe"
                ) else (
                    set RUN_PYW="%%I"
                )
                goto python_ready
            )
        )
    )
)

REM 3. Check AppData Programs
for %%V in (314 313 312 311 310 39 38) do (
    if not defined RUN_PY (
        if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
            set RUN_PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            set RUN_PYW="%LOCALAPPDATA%\Programs\Python\Python%%V\pythonw.exe"
            goto python_ready
        )
    )
)

REM 4. Check Program Files
for %%V in (314 313 312 311 310 39 38) do (
    if not defined RUN_PY (
        if exist "%ProgramFiles%\Python%%V\python.exe" (
            set RUN_PY="%ProgramFiles%\Python%%V\python.exe"
            set RUN_PYW="%ProgramFiles%\Python%%V\pythonw.exe"
            goto python_ready
        )
    )
)

REM 5. Check pythoncore
for /d %%C in ("%LOCALAPPDATA%\Python\pythoncore-*") do (
    if not defined RUN_PY (
        if exist "%%C\python.exe" (
            set RUN_PY="%%C\python.exe"
            set RUN_PYW="%%C\pythonw.exe"
            goto python_ready
        )
    )
)

echo [ERROR] Python was not found on this computer!
echo Please install Python 3.8+ from https://www.python.org/downloads/
echo Make sure to check 'Add python.exe to PATH' during installation.
pause
exit /b 1

:python_ready
echo Found Python: %RUN_PY%

REM Check dependencies
%RUN_PY% -c "import requests, bs4, PIL" >nul 2>&1
if errorlevel 1 (
    echo Installing required libraries: requests, beautifulsoup4, pillow...
    %RUN_PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        %RUN_PY% -m pip install --user -r requirements.txt
    )
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements automatically.
        echo Please run Install_Requirements.bat manually.
        pause
        exit /b 1
    )
    echo Libraries installed successfully!
)

echo Starting Steam Card Farmer...
start "" %RUN_PYW% main.py
exit /b 0
