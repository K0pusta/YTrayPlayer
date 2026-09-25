@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo  Скачивание yt-dlp в bin\
echo ============================================

if not exist bin mkdir bin
if not exist bin\mpv mkdir bin\mpv

REM --- yt-dlp ---
if exist bin\yt-dlp.exe (
    echo [INFO] bin\yt-dlp.exe уже есть
) else (
    echo [INFO] Скачиваю yt-dlp.exe...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile 'bin\yt-dlp.exe'"
)

REM --- mpv ---
if exist bin\mpv\mpv.exe (
    echo [INFO] bin\mpv\mpv.exe уже есть
) else (
    echo.
    echo [ВАЖНО] mpv надо скачать вручную:
    echo   1. Открой https://sourceforge.net/projects/mpv-player-windows/files/release/
    echo   2. Скачай mpv-x86_64-*.7z
    echo   3. Распакуй mpv.exe и d3dcompiler_43.dll в bin\mpv\
    echo.
)

pause