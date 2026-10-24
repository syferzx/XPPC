# Componentes externos

La licencia MIT del cliente no sustituye las licencias de sus dependencias ni concede derechos sobre servicios, marcas o contenidos externos.

Los textos de las dependencias identificadas se conservan en `LICENSES/` y el aviso de hls.js también en `outputs/windows-hls-player/vendor/`.

Dependencias: hls.js (Apache-2.0), cryptography (Apache-2.0 o BSD), cffi, pycparser, mmh3, certifi (MPL-2.0), pyelftools, imageio-ffmpeg (BSD para el wrapper), Python (PSF) y Unicorn (GPL-2.0 para su núcleo). FFmpeg tiene su propia licencia según la compilación utilizada.

El componente de protocolo `libranger-jni.so` es externo, no tiene código fuente en este repositorio y no se incluye en esta exportación. Su licencia de redistribución no está verificada. Tampoco se incluyen Python, FFmpeg ni otros ejecutables. La reutilización del motor de una instalación local no resuelve por sí sola las condiciones de redistribución de esos binarios.
