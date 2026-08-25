@echo off
title Nigel — Assistant Launcher
cd /d "%~dp0"

echo ===================================================
echo               Iniciando Nigel Assistant
echo ===================================================
echo.

:: Verifica se existe ambiente virtual e ativa se presente
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Ativando ambiente virtual 'venv'...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Ativando ambiente virtual '.venv'...
    call .venv\Scripts\activate.bat
)

:: Executa a aplicacao
echo [INFO] Executando main.py...
python main.py

:: Se encerrar com erro, pausa para visualizacao
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] O Nigel encerrou com codigo de erro %ERRORLEVEL%.
    echo Pressione qualquer tecla para fechar...
    pause >nul
)
