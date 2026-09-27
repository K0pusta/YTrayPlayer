@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo  YTrayPlayer - сборка exe через PyInstaller
echo ============================================
echo.

REM
if not exist main.py (
    echo [ОШИБКА] main.py не найден. Переименуй main_core_test.py в main.py
    pause
    exit /b 1
)

REM
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller не установлен. Устанавливаю...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить PyInstaller.
        pause
        exit /b 1
    )
)

REM
echo [INFO] Устанавливаю зависимости...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

REM
echo [INFO] Чищу build\ и dist\...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM
echo [INFO] Собираю exe...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo [ОШИБКА] Сборка провалилась.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Готово! exe лежит в dist\YTrayPlayer.exe
echo  Дальше запусти make_dist.bat — соберёт zip
echo ============================================
pause