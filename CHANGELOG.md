# Cambios

## 0.7.0 — Primera beta pública

- Distribución pública en `samuhlo/prelo-ob`, con licencia MIT, manifiesto de Obsidian y paquetes compilados.
- Instalador guiado para un Mac con Docker y uv: servicio privado, credencial propia, vault explícito y conector USB.
- Plugin instalable con BRAT o ZIP en Obsidian de escritorio para macOS, Windows y Linux.
- SQLite incorporado a `main.js`; el plugin funciona con los tres archivos que instala Obsidian.
- Instalación y actualización conservan configuración, selección y otros complementos, con copia previa.
- USB como flujo principal; acceso al Kobo por wifi fuera de esta versión.
- Logo PrelO en la cabecera y revista en el lateral.
- Pruebas automatizadas, empaquetado reproducible, comprobación de archivos públicos y sumas SHA-256.

La automatización USB mantiene pendiente su validación física específica. Consulta [el estado de la beta](docs/validacion-publica.md).

## Antes de la publicación pública

El prototipo incorporó generación de EPUB, procedencia, importación idempotente de anotaciones, biblioteca compartida, cola persistente, estilos de estudio y revista, e interfaz de selección en Obsidian. El circuito manual de lectura e importación se probó con un Kobo Libra Colour. Los informes de las instalaciones personales se conservan fuera de este repositorio.
