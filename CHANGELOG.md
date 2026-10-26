# Cambios

## Sin publicar

- El estado de cada revista enviada refleja lo que hay en el Kobo: «Copiada · aparecerá al desconectar el Kobo», «En tu Kobo» con el porcentaje leído, «el Kobo no la importó» o «Ya no está en el Kobo», con la opción de volver a enviarla. El conector del Mac lee la base del lector en cada conexión.
- Preparar revista empieza con «Empezar una revista» y la lista «Para retomar». Al cerrar Prelo, la revista a medias se guarda como borrador compartido y desaparecen los marcadores de selección; si el Mac no responde, se guarda en el equipo hasta poder compartirla.
- «Guardar y salir» y «Descartar» durante la preparación; al crear la revista se retira su borrador.
- Una edición en marcha se puede cancelar desde Prelo; se detiene al terminar la parte en curso.

## 0.9.1 — Actualizar desde Obsidian

- «Actualizar ahora» instala la nueva versión del plugin en el propio Obsidian: descarga la release, comprueba sus sumas SHA-256 y reinicia Prelo. «Novedades» abre la release en GitHub.

## 0.9.0 — Ediciones grandes, idioma y maquetación

- Revista 90’s enmarca cada imagen de las notas en un bisel de consola de 16 bits, con su número de figura en el mismo bloque. La imagen original no cambia; las pequeñas se amplían con píxeles nítidos.
- Las imágenes WebP se incluyen como PNG sin pérdida, porque los lectores no siempre las muestran.
- Las notas cortas consecutivas comparten página; cada una conserva su ancla, su procedencia y la recuperación de subrayados.
- Se retira el pie «Fuente: …» al final de cada artículo, que podía quedar solo en una página.
- Revista 90’s abre cada artículo con una página compuesta de ilustración, sección y título; la leyenda encabeza el texto.
- Las imágenes de las notas se centran como figura sin partirse entre páginas.
- Idioma de la revista: si la selección está en gallego, se puede elegir castellano o galego para la IA, la portada y el índice.
- Los artículos redactados de nuevo muestran su título en el idioma de la revista; la procedencia conserva el título de la nota.
- Un primer encabezado de más de 200 caracteres ya no impide crear la edición; se usa el nombre del archivo.
- Edición con IA por etapas: un plan editorial con un resumen de cada nota y la redacción por partes, cuatro a la vez por defecto. Las selecciones grandes ya no dependen de una única respuesta.
- Prompts nuevos por etapa, modo de redacción y apoyos, con reglas de lectura para el Kobo.
- Cada parte se comprueba contra su fuente: si faltan cifras, comandos o imágenes, se vuelve a pedir una vez.
- Las partes terminadas se reutilizan al reintentar una edición fallida durante 30 días.
- Modelo y esfuerzo de razonamiento configurables por etapa (`AI_MODEL_PLAN`, `AI_EFFORT_WRITE`…), además de concurrencia, tamaño de parte y tiempo máximo.
- El puente de Codex expone `/v1/complete` en lugar de `/v1/plan`: actualiza servidor y puente juntos.
- La lectura USB solo pide al Kobo las columnas necesarias, para que los datos binarios del firmware no impidan importar subrayados.

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
