# Corrección de conexión de TV

La dirección IP fija usada para solicitar la autorización de TV dejó de responder. El mismo dominio del proveedor siguió respondiendo por el DNS normal del sistema.

La versión 0.1.4 resuelve el dominio previamente validado mediante el sistema operativo. Conserva el nombre HTTPS, SNI, la verificación del certificado y la validación del origen del video. No cambia de cuenta, no añade DNS externos ni modifica VPN. Las respuestas privadas o vacías se rechazan; no se vuelve a la IP fija si falla DNS.

Se verificaron cuatro pruebas de DNS, nueve de renovación de TV y tres de HTTP del autorizador. En la instalación local, AMC HD entregó lista y segmento válidos; una muestra de tres segundos decodificó 86 fotogramas y el usuario confirmó que volvió a funcionar la TV.

Pruebas de DNS y renovación, con las dependencias de desarrollo instaladas:

```powershell
python work/test_tv_dns_resolution.py
python work/test_tv_renewal.py
```

El acceso sigue dependiendo de la disponibilidad del proveedor y de la red utilizada.
