@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

if not exist "%~dp0Engine\python.exe" (
    echo Falta Engine\python.exe. Extrae la carpeta completa antes de iniciar.
    pause
    exit /b 1
)
if not exist "%~dp0Engine\app\portable.py" (
    echo Falta Engine\app\portable.py. Extrae la carpeta completa antes de iniciar.
    pause
    exit /b 1
)

set "XUPERPC_PORTABLE_ROOT=%~dp0"
set "XUPERPC_ENGINE_ROOT=%~dp0Engine"
set "PYTHONPATH="
set "PYTHONHOME="
echo XuperPC - inicio directo con el motor incluido.
echo La aplicacion se abrira en tu navegador.
echo Conserva esta ventana abierta. Para detener el servidor, pulsa Ctrl+C.
echo.
"%~dp0Engine\python.exe" -I "%~dp0Engine\app\portable.py" %*
set "resultado=%errorlevel%"
if not "%resultado%"=="0" (
    echo.
    echo No se pudo completar el inicio. Revisa el mensaje anterior y Datos\work\XuperPC-error.log.
    pause
)
exit /b %resultado%
