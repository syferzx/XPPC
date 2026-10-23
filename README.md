# XPPC

Reproductor multimedia portable para Windows.

[![Descargar para Windows](docs/download-windows.svg)](https://github.com/syferzx/XPPC/releases/latest/download/XuperPC-Windows-x64.zip)

## Abrir la aplicaciÃ³n

1. Descarga el ZIP de [Releases](https://github.com/syferzx/XPPC/releases/latest).
2. Haz clic derecho y elige **Extraer todo**.
3. Abre la carpeta y ejecuta **XuperPC.exe**.

## CÃ³digo fuente y colaboraciÃ³n

AquÃ­ estÃ¡ el cÃ³digo del cliente: interfaz, catÃ¡logo, reproductor, favoritos, progreso y conexiÃ³n al servicio. Puedes analizarlo, modificarlo y proponer mejoras mediante pull requests.

Consulta [Desarrollo](docs/DESARROLLO.md) para ejecutar las fuentes, probar cambios y preparar un portable. El motor utiliza un componente binario externo; esta publicaciÃ³n no incluye su cÃ³digo fuente ni permite reconstruirlo. Las fuentes del cliente por sÃ­ solas no son una distribuciÃ³n autÃ³noma del motor.

El catÃ¡logo y la reproducciÃ³n dependen de servicios externos. Cada instalaciÃ³n conserva sus datos localmente en `Datos`.

## Licencia

[MIT](LICENSE) para el cÃ³digo original del cliente. Los componentes externos conservan sus [licencias](THIRD_PARTY_NOTICES.md).
