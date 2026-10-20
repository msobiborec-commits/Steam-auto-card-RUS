@echo off
cd /d "%~dp0"

echo ========================================================
echo   Install Requirements for Steam Card Farmer
echo ========================================================
echo Searching for Python...

set "RUN_PY="

REM 1. Check Python Launcher (py)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set RUN_PY=py -3
        goto do_install
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
                goto do_install
            )
        )
    )
)

REM 3. Check AppData Programs
for %%V in (314 313 312 311 310 39 38) do (
    if not defined RUN_PY (
        if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
            set RUN_PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            goto do_install
        )
    )
)

REM 4. Check Program Files
for %%V in (314 313 312 311 310 39 38) do (
    if not defined RUN_PY (
        if exist "%ProgramFiles%\Python%%V\python.exe" (
            set RUN_PY="%ProgramFiles%\Python%%V\python.exe"
            goto do_install
        )
    )
)

REM 5. Check pythoncore
for /d %%C in ("%LOCALAPPDATA%\Python\pythoncore-*") do (
    if not defined RUN_PY (
        if exist "%%C\python.exe" (
            set RUN_PY="%%C\python.exe"
            goto do_install
        )
    )
)

echo [ERROR] Python was not found on this computer!
echo Please install Python 3.8+ from https://www.python.org/downloads/
echo Make sure to check 'Add python.exe to PATH' during installation.
pause
exit /b 1

:do_install
echo Using Python: %RUN_PY%
echo.
echo Installing requests, beautifulsoup4, pillow...
%RUN_PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo Retrying with --user flag...
    %RUN_PY% -m pip install --user -r requirements.txt
)

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install libraries. Please check your internet connection.
) else (
    echo.
    echo ========================================================
    echo [SUCCESS] All requirements installed successfully!
    echo You can now launch Start_Farmer.bat
    echo ========================================================
)
echo.
pause
exit /b 0
