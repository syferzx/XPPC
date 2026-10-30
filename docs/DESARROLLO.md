# Desarrollo

## Estructura

- `outputs/windows-hls-player/`: interfaz HTML/CSS/JS, servidor y lanzador Python.
- `work/`: módulos de transporte y pruebas.
- `outputs/ranger-windows/`: adaptador del protocolo.
- `outputs/app-bootstrap.json` y `outputs/rutas-portal.json`: configuración compartida del cliente; no son sesiones personales.

## Ejecutar desde las fuentes

Usa Windows de 64 bits y Python 3.12. Desde la raíz:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

La reproducción necesita el componente binario externo del motor. Si ya tienes una copia local del portable, el archivo está en `Engine/outputs/xuper-apk/lib/arm64-v8a/libranger-jni.so`. Para trabajar localmente, sitúalo en la misma ruta relativa `outputs/xuper-apk/lib/arm64-v8a/libranger-jni.so` de las fuentes. No lo añadas al repositorio: está excluido de Git y no se publica su código fuente aquí.

```powershell
.venv\Scripts\python outputs/windows-hls-player/portable.py
```

Para probar cambios con el motor ya incluido en el portable, sin configurar dependencias de reproducción en Python, usa el procedimiento siguiente y abre el EXE de la copia generada.

## Preparar una copia del portable con tus cambios

El script toma únicamente `Engine`, `_internal` y el EXE de un portable existente, sustituye el código del cliente por las fuentes actuales y crea una carpeta nueva. Nunca copia `Datos`. No recompila Python, FFmpeg ni el componente binario externo.

```powershell
python tools/prepare_portable.py --base "C:\ruta\XuperPC" --output "C:\ruta\XPPC-prueba"
```

Abre `XuperPC.exe` en la nueva carpeta. Los cambios en HTML/CSS/JS y módulos de aplicación quedan incluidos. Para recompilar el pequeño lanzador `bootstrap.py` añade `--rebuild-launcher`, después de instalar `pyinstaller==6.22.0` con el mismo Python.

## Pruebas sin conexión al proveedor

```powershell
python -m unittest discover -s work -p "test_*.py"
```

## Contribuir

Crea una rama y envía un pull request describiendo el cambio y cómo lo comprobaste. No adjuntes `Datos`, sesiones, tokens, capturas de tráfico ni archivos de tu instalación personal. Para distribuir binarios revisa también las condiciones de sus componentes externos.

## Pruebas de categorías y TV en vivo

Con Node.js compatible con jsdom 29.1.1, desde la raíz del repositorio:

```powershell
npm install
npm test
```

Estas dependencias son solo para desarrollo. El portable no necesita Node.js. El generador también copia `Iniciar.bat` junto al motor de la nueva carpeta.
