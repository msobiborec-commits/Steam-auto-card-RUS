@echo off
cd /d "%~dp0"

:: 1. Check specific local pythoncore
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe" main.py
    exit
)

:: 2. Check standard Windows AppData Python versions
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\pythonw.exe" (
        start "" "%%D\pythonw.exe" main.py
        exit
    )
)

:: 3. Check Program Files Python
for /d %%D in ("C:\Program Files\Python3*") do (
    if exist "%%D\pythonw.exe" (
        start "" "%%D\pythonw.exe" main.py
        exit
    )
)

:: 4. Try pyw launcher
where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw main.py
    exit
)

:: 5. Try PATH pythonw
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw main.py
    exit
)

:: 6. Fallback to python.exe
where python >nul 2>&1
if %errorlevel% equ 0 (
    start "" python main.py
    exit
)

:: 7. If Python not found on target PC
echo [ОШИБКА] Python не обнаружен на этом компьютере!
echo Пожалуйста, установите Python с сайта https://python.org
echo При установке обязательно включите галочку "Add python.exe to PATH".
echo.
pause
