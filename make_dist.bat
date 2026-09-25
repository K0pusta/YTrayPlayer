@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set DIST=dist\YTrayPlayer

echo ============================================
echo  Сборка финального дистрибутива в dist\YTrayPlayer\
echo ============================================
echo.

REM Проверяем, что exe собран
if not exist dist\YTrayPlayer.exe (
    echo [ОШИБКА] dist\YTrayPlayer.exe не найден. Сначала запусти build.bat
    pause
    exit /b 1
)

REM Создаём структуру
if exist "%DIST%" rmdir /s /q "%DIST%"
mkdir "%DIST%"
mkdir "%DIST%\bin"
mkdir "%DIST%\bin\mpv"
mkdir "%DIST%\assets"
mkdir "%DIST%\locales"

REM Копируем exe
copy dist\YTrayPlayer.exe "%DIST%\YTrayPlayer.exe" >nul

REM portable.flag
type nul > "%DIST%\portable.flag"

REM bin
copy bin\mpv\mpv.exe "%DIST%\bin\mpv\mpv.exe" >nul
copy bin\mpv\d3dcompiler_43.dll "%DIST%\bin\mpv\d3dcompiler_43.dll" >nul
copy bin\yt-dlp.exe "%DIST%\bin\yt-dlp.exe" >nul

REM assets
copy assets\icon.ico "%DIST%\assets\icon.ico" >nul

REM locales
copy locales\ru.json "%DIST%\locales\ru.json" >nul
copy locales\en.json "%DIST%\locales\en.json" >nul

REM README
if exist README_друзьям.txt (
    copy README_друзьям.txt "%DIST%\README_друзьям.txt" >nul
)

REM ZIP
echo [INFO] Упаковываю в zip...
powershell -NoProfile -Command "Compress-Archive -Path '%DIST%\*' -DestinationPath 'dist\YTrayPlayer.zip' -Force"

echo.
echo ============================================
echo  Готово!
echo ============================================
pause