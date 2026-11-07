@echo off
setlocal
cd /d "%~dp0"

set "MODE=%~1"
if /I "%MODE%"=="console" (
  set "WINDOWFLAG=--console"
) else (
  set "WINDOWFLAG=--windowed"
)
if not defined FFGUI_DISTPATH set "FFGUI_DISTPATH=dist"

echo Compilando FFmpeg Studio (%WINDOWFLAG%)...
python -m PyInstaller --noconfirm --clean --name FFmpegStudio %WINDOWFLAG% ^
  --distpath "%FFGUI_DISTPATH%" ^
  --noupx ^
  --contents-directory "." ^
  --icon "assets\icon.ico" ^
  --runtime-hook "tools\pyi_rth_pythonnet.py" ^
  --add-data "web;web" ^
  --add-data "presets.json;." ^
  --collect-all webview ^
  --collect-all clr_loader ^
  --collect-all pythonnet ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  --exclude-module PySide2 ^
  --exclude-module PySide6 ^
  --exclude-module tkinter ^
  --exclude-module _tkinter ^
  --exclude-module gevent ^
  --exclude-module greenlet ^
  --exclude-module tornado ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  app.py
if errorlevel 1 goto :error

if not exist "%FFGUI_DISTPATH%\FFmpegStudio\FFmpegStudio.exe" goto :error

copy /Y "assets\FFmpegStudio.exe.config" "%FFGUI_DISTPATH%\FFmpegStudio\FFmpegStudio.exe.config" >nul

if not defined FFMPEG_DIR set "FFMPEG_DIR=..\ffmpeg-master-latest-win64-gpl\bin"

if exist "%FFMPEG_DIR%\ffmpeg.exe" (
  if not exist "%FFGUI_DISTPATH%\FFmpegStudio\ffmpeg\bin" mkdir "%FFGUI_DISTPATH%\FFmpegStudio\ffmpeg\bin"
  copy /Y "%FFMPEG_DIR%\ffmpeg.exe" "%FFGUI_DISTPATH%\FFmpegStudio\ffmpeg\bin\" >nul
  copy /Y "%FFMPEG_DIR%\ffprobe.exe" "%FFGUI_DISTPATH%\FFmpegStudio\ffmpeg\bin\" >nul
  if exist "%FFMPEG_DIR%\..\LICENSE.txt" copy /Y "%FFMPEG_DIR%\..\LICENSE.txt" "%FFGUI_DISTPATH%\FFmpegStudio\ffmpeg\LICENSE.txt" >nul
  echo FFmpeg copiado junto a la aplicacion.
)

echo.
echo Listo: %FFGUI_DISTPATH%\FFmpegStudio\FFmpegStudio.exe

rem PyInstaller deja un .exe intermedio en build\ sin sus DLL; se elimina para evitar confusiones.
if exist "build" rmdir /s /q "build" >nul 2>&1
pause
exit /b 0

:error
echo.
echo ERROR: la compilacion fallo.
exit /b 1
