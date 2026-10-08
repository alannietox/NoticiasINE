@echo off
setlocal
title Instalador - NoticiasINE
echo =======================================================
echo   Instalador de NoticiasINE
echo =======================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 no esta instalado o no esta en PATH.
    echo Intentando instalar Python 3.12 mediante winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar Python automaticamente.
        pause
        exit /b 1
    )
    echo.
    echo Cierra esta ventana y vuelve a ejecutar win_instalador.bat.
    pause
    exit /b 0
)

echo [OK] Python encontrado:
python --version
echo.

echo [1/4] Creando entorno virtual...
python -m venv venv
if errorlevel 1 goto :error

echo [2/4] Instalando dependencias...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [3/4] Creando lanzador...
(
echo @echo off
echo call venv\Scripts\activate.bat
echo python app.py
) > iniciar.bat

echo [4/4] Verificando instalacion...
python -m compileall -q app.py
if errorlevel 1 goto :error

echo.
echo =======================================================
echo   Instalacion completada correctamente.
echo   Ejecuta iniciar.bat para abrir NoticiasINE.
echo =======================================================
pause
exit /b 0

:error
echo.
echo [ERROR] La instalacion no se pudo completar.
pause
exit /b 1
