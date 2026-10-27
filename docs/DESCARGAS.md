# Mis descargas

Usa la flecha de una carátula de película para descargar sin abrir el reproductor. También puedes usar **Descargar** en una ficha o la flecha de un episodio. Se guarda el progreso de reproducción y se detienen el reproductor y su búfer al abrir las opciones de descarga.

Elige un audio y un subtítulo opcional, y pulsa **Añadir a Mis descargas**. Un aviso animado confirma la incorporación. En **Mis descargas** puedes consultar progreso, posición en cola, cancelar y abrir la carpeta. Se procesa un título a la vez con tres partes en paralelo, conservando su orden al escribir el archivo. Las solicitudes conservan las verificaciones y renovación del motor existente y tienen reintentos limitados para errores de conexión.

El formato predeterminado es MKV original: conserva el video y el audio seleccionado sin recodificar. Los subtítulos se incluyen como pista SRT y también se entrega un SRT aparte. Como alternativa se puede elegir MP4 compatible: H.264 y AAC, con conversión del video cuando haga falta. MKV requiere reorganizar y escribir el contenedor, pero evita la recodificación de video y audio; no acelera la transferencia de red.

La carpeta predeterminada se cambia con **Elegir carpeta** o introduciendo una ruta absoluta y pulsando **Guardar ruta**. Las descargas ya encoladas conservan la carpeta que tenían al añadirlas. El historial se guarda localmente en Datos. Si un archivo se borra o mueve desde Windows, la lista indica **Archivo no encontrado**. **Quitar del historial** elimina solo el registro, nunca el MP4 ni el SRT.

Mantén XuperPC abierto. Al reiniciar, las descargas pendientes o incompletas se muestran como interrumpidas y requieren volver a intentarlo; no se reanudan desde el byte anterior. Los archivos terminados permanecen en su carpeta. Los archivos finalizados por la versión anterior se reconocen en la carpeta predeterminada por su nombre de exportación.

Validación: creación de MP4 real de muestra con dos audios y subtítulos, selección de idioma, SRT, tres partes simultáneas y ensamblado correcto, cola y cancelación, persistencia, detección de archivo borrado y cambios de carpeta. Pruebas integradas verifican que descargar detiene el reproductor y su búfer. La prueba del portable descargó 44 MB y se canceló: el reproductor registró cero solicitudes de segmentos y los temporales quedaron limpios. No se descargó una película completa para esta comprobación.
