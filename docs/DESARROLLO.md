# Desarrollo

## Estructura

- `outputs/windows-hls-player/`: interfaz HTML/CSS/JS, servidor y lanzador Python.
- `work/`: mÃ³dulos de transporte y pruebas.
- `outputs/ranger-windows/`: adaptador del protocolo.
- `outputs/app-bootstrap.json` y `outputs/rutas-portal.json`: configuraciÃ³n compartida del cliente; no son sesiones personales.

## Ejecutar desde las fuentes

Usa Windows de 64 bits y Python 3.12. Desde la raÃ­z:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

La reproducciÃ³n necesita el componente binario externo del motor. Si ya tienes una copia local del portable, el archivo estÃ¡ en `Engine/outputs/xuper-apk/lib/arm64-v8a/libranger-jni.so`. Para trabajar localmente, sitÃºalo en la misma ruta relativa `outputs/xuper-apk/lib/arm64-v8a/libranger-jni.so` de las fuentes. No lo aÃ±adas al repositorio: estÃ¡ excluido de Git y no se publica su cÃ³digo fuente aquÃ­.

```powershell
.venv\Scripts\python outputs/windows-hls-player/portable.py
```

Para probar cambios con el motor ya incluido en el portable, sin configurar dependencias de reproducciÃ³n en Python, usa el procedimiento siguiente y abre el EXE de la copia generada.

## Preparar una copia del portable con tus cambios

El script toma Ãºnicamente `Engine`, `_internal` y el EXE de un portable existente, sustituye el cÃ³digo del cliente por las fuentes actuales y crea una carpeta nueva. Nunca copia `Datos`. No recompila Python, FFmpeg ni el componente binario externo.

```powershell
python tools/prepare_portable.py --base "C:\ruta\XuperPC" --output "C:\ruta\XPPC-prueba"
```

Abre `XuperPC.exe` en la nueva carpeta. Los cambios en HTML/CSS/JS y mÃ³dulos de aplicaciÃ³n quedan incluidos. Para recompilar el pequeÃ±o lanzador `bootstrap.py` aÃ±ade `--rebuild-launcher`, despuÃ©s de instalar `pyinstaller==6.22.0` con el mismo Python.

## Pruebas sin conexiÃ³n al proveedor

```powershell
python -m unittest discover -s work -p "test_*.py"
```

## Contribuir

Crea una rama y envÃ­a un pull request describiendo el cambio y cÃ³mo lo comprobaste. No adjuntes `Datos`, sesiones, tokens, capturas de trÃ¡fico ni archivos de tu instalaciÃ³n personal. Para distribuir binarios revisa tambiÃ©n las condiciones de sus componentes externos.
