@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0app.py" %*
  exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0app.py" %*
  exit /b %errorlevel%
)
echo No se encuentra Python. Instala Python 3.10 o superior y vuelve a intentarlo.
pause
