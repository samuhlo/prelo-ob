# Datos y permisos

Prelo es una instalación personal: cada persona ejecuta su servicio y genera su credencial. El repositorio y los ZIP públicos no incluyen credenciales, publicaciones ni datos de ningún vault.

## Qué lee y escribe

- El plugin lee las notas seleccionadas y sus adjuntos locales para generar una publicación. Puede añadir `margen_id` a las propiedades para mantener la identidad de una nota entre equipos y renombrados.
- El servicio guarda fuentes de las ediciones, EPUB, portadas, catálogo, borradores, cola y anotaciones en su volumen Docker.
- El conector USB lee una copia comprobada de `KoboReader.sqlite`, importa las anotaciones, copia las publicaciones pendientes y expulsa el dispositivo. No escribe directamente en la base de datos del lector.
- Los subrayados se añaden al vault. Una actualización conserva el texto previo y los comentarios; no se borran notas como consecuencia de eliminar una cita en el Kobo.
- La limpieza de almacenamiento del servicio no elimina libros del Kobo ni exportaciones manuales del vault. Las retiradas solicitadas explícitamente se vinculan al lector y a la huella del archivo; la importación de citas ocurre antes de ejecutarlas.

## Red e IA

Sin IA, las notas seleccionadas se procesan en tu propio servicio. Al activar IA se envían al proveedor configurado. La generación con Codex utiliza la sesión del usuario del Mac; las credenciales de ChatGPT no se copian al contenedor ni al plugin. La cuota y la disponibilidad dependen de esa cuenta. Las imágenes nuevas se leen únicamente del directorio de su sesión de generación; la copia temporal del host se retira tras preparar el resultado. La caché del servicio conserva la ilustración para reintentos.

El plugin consulta las releases públicas de GitHub al iniciar y cada seis horas para avisar de nuevas versiones, incluidas las betas. No envía notas, rutas del vault ni credenciales; GitHub recibe la conexión HTTP habitual. Puedes desactivar esta consulta en Ajustes de Prelo.

Prelo no incorpora analítica ni telemetría. La instalación descarga dependencias de sus proveedores y puede descargar Python mediante uv. BRAT o GitHub se utilizan para distribuir actualizaciones. Esos servicios tienen sus propias condiciones.

El servicio requiere una credencial compartida y está pensado para una biblioteca personal, no para alojar usuarios independientes. Quien tiene la credencial puede acceder a las publicaciones y anotaciones y gestionar esa biblioteca. El instalador escucha en loopback; los accesos desde otros ordenadores requieren una red privada y HTTPS configurados por el propietario.

## Archivos privados

`service.env`, `.env`, `usb.json`, `conexion-prelo.json` y `.obsidian/plugins/margen/data.json` contienen configuración privada o credenciales. Las copias anteriores de configuración también son privadas. No se incluyen en las releases ni deben enviarse en incidencias.

No adjuntes una base de datos del Kobo, tu vault, una publicación personal ni la salida completa de una herramienta de depuración para comunicar un error. Basta con versiones, sistema operativo, pasos para reproducirlo y un ejemplo sintético.
