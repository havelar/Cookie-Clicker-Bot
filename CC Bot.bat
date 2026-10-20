@echo off
setlocal

rem Este arquivo pode ser copiado para qualquer pasta deste computador.
set "PROJECT_DIR=D:\Github\Cookie-Clicker-Bot"
set "PYTHONW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Ambiente virtual nao encontrado em:
    echo %PYTHONW%
    echo.
    echo Execute a instalacao das dependencias antes de iniciar o bot.
    pause
    exit /b 1
)

start "Cookie Clicker Bot" /D "%PROJECT_DIR%" "%PYTHONW%" "%PROJECT_DIR%\main.py"
endlocal
