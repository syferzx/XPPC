# Reproducción y búfer

Películas y series utilizan hasta tres descargas simultáneas. El navegador intenta acumular 180 segundos, con máximo temporal de 240 segundos y presupuesto de tamaño de 192 MiB. El servicio conserva una caché de 96 MiB y una ventana adicional de hasta 60 segundos, limitada también por bytes y cantidad de segmentos. El consumo total incluye otras estructuras y los datos en tránsito.

La reserva contigua se muestra junto a la resolución. Los límites son objetivos, no una garantía de disponibilidad o de ausencia de cortes. La velocidad del proveedor puede limitar la reserva.

La continuación carga desde 20 segundos antes del marcador y espera a tener disponible el punto guardado. Los rangos consecutivos del índice se agrupan con objetivo de cuatro segundos y máximo de ocho MiB por combinación, conservando bytes y tiempos. Esto evita fragmentos diminutos que podían bloquear la reproducción. No se recodifica el contenido para agruparlo.

## Validación

Las pruebas comprueban concurrencia, deduplicación, límites, saltos de posición, cancelación, reintentos, renovación concurrente, validación de rangos, continuación y conservación de bytes al agrupar. Se verificó una muestra de 18 segundos en la zona del bloqueo de La Brea T3 y el usuario confirmó que el episodio volvió a funcionar.

Con Python y las dependencias de desarrollo instaladas:

```powershell
python work/test_vod_parallel_buffer.py
python work/test_vod_renewal.py
python work/test_vod_segment_grouping.py
npm install
npm test
```

Los registros y las muestras privadas no se incluyen en el repositorio.
