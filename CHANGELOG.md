# Cambios

## Sin publicar — Maquetación e idioma

- Las notas cortas consecutivas comparten página; cada una conserva su ancla, su procedencia y la recuperación de subrayados.
- Se retira el pie «Fuente: …» al final de cada artículo, que podía quedar solo en una página.
- Revista 90’s abre cada artículo con una página compuesta de ilustración, sección y título; la leyenda encabeza el texto.
- Las imágenes de las notas se centran como figura sin partirse entre páginas.
- Idioma de la revista: si la selección está en gallego, se puede elegir castellano o galego para la IA, la portada y el índice.
- Un primer encabezado de más de 200 caracteres ya no impide crear la edición; se usa el nombre del archivo.

## 0.8.1 — Errores de generación claros

- Explica los rechazos de validación en lugar de mostrar únicamente el código 422.
- Comprueba el tamaño de la selección antes de enviarla; conserva los límites de 600.000 caracteres por edición y 200.000 por nota.
- Las respuestas de validación no incluyen el contenido de las notas.

## 0.8.0 — Redacción, estudio y actualizaciones

- Modos de redacción, apoyos de estudio e instrucciones extra con bloqueo del orden.
- Carátula de juego retro por nota en Revista 90’s.
- Eliminación manual del EPUB conservando subrayados y procedencia.
- Avisos de versiones publicadas, comprobación manual y detección de diferencias entre plugin y servidor.
- Preparación de versiones coherentes con `scripts/set_version.py`.


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
