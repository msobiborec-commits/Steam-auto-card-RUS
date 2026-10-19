@echo off
title Установка зависимостей Steam Card Farmer
cd /d "%~dp0"

echo ========================================================
echo Проверка и установка библиотек: requests, beautifulsoup4, pillow...
echo ========================================================
echo.

:: 1. Check local pythoncore
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements.txt
    goto finish
)

:: 2. Check standard Windows AppData Python
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -m pip install -r requirements.txt
        goto finish
    )
)

:: 3. Check Program Files Python
for /d %%D in ("C:\Program Files\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -m pip install -r requirements.txt
        goto finish
    )
)

:: 4. Try py launcher
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -m pip install -r requirements.txt
    goto finish
)

:: 5. Try PATH python
where python >nul 2>&1
if %errorlevel% equ 0 (
    python -m pip install -r requirements.txt
    goto finish
)

echo.
echo [ОШИБКА] Python не найден на этом компьютере!
echo Скачайте и установите Python с https://python.org
echo При установке ОБЯЗАТЕЛЬНО поставьте галочку "Add python.exe to PATH"!
echo.
pause
exit /b 1

:finish
echo.
echo ========================================================
echo Все зависимости успешно установлены!
echo Теперь вы можете запускать бота через Start_Farmer.bat
echo ========================================================
echo.
pause
