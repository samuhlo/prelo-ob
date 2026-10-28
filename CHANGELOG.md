# Cambios

## Sin publicar

- Nuevo logotipo: PREL en palo grueso y la O dentro de una piedra amarilla, de la misma familia que Anaco. El icono lateral conserva la revista.
- README con capturas del recorrido y un ejemplo de portada y carátula de Revista 90's, generados con un vault de demostración.
- Portadas con «1 sección» en singular.
- Ajustes: «Actualizar ahora» solo se destaca cuando hay una versión nueva; el servicio se describe como «tu Mac».
- Biblioteca en MB por debajo de 1 GB, «Sin subrayados» en libros sin citas, avisos de selección sin la pista redundante cuando Prelo ya está abierto y separación entre la cabecera y el aviso de revista lista.

## 1.0.0 — Beta candidata, pendiente de aceptación

- Drenaje de borradores y revisiones guardados durante un envío.
- Identidad Kobo estable ante firmware; órdenes antiguas visibles para repetirlas sin reasignar retiradas.
- Estados por lector, entregas recientes y libros sin ruta local sin falsos avisos de ausencia.
- Recuperación de trabajos inexistentes sin confundirlos con errores de red; liberación de cupos y cancelación al obtener turno.
- Subidas sin doble reserva de disco, manteniendo cuota y margen libre.
- Aislamiento de YAML inválido, cabeceras largas y anclas nulas; citas sin duplicados al recuperar una ficha, tanto en el conector como en la importación manual.
- Literales conservados sin falsos rechazos, signos numéricos e imágenes comprobadas con el contrato del renderizador. Los dos últimos eran limitaciones previas.
- Registro de recuperación hasta confirmar activación; reversión con el archivo de entrada al final y coordinación con instalación manual.
- Consultas API independientes de la carpeta de exportación; reintento seguro de primera instalación, ajustes con BOM y bloqueo real de copia USB.
- Paquetes preparados localmente. Publicación bloqueada hasta repetir aceptación de instalación limpia, Obsidian, Kobo físico y recuperación para esta huella.

## 0.11.0 — Candidata de estabilización

- Conservación de varias revistas sin conexión y sincronización de borradores confirmada.
- Órdenes USB vinculadas al dispositivo y al archivo, reclamación antes de ejecutar y cancelación veraz.
- Cancelación recuperable, límites de trabajos y bloqueo de opciones de IA incompatibles.
- Subidas por streaming, backup/restauración de pendientes y retención planificada antes de borrar.
- Importación tolerante a notas defectuosas, identidades delimitadas y anclas para recuperar procedencia.
- Rechazo de adaptaciones incompletas, planes editoriales comprobados y caché por proveedor.
- Pillow 13, validación de imágenes y lista explícita de archivos públicos.
- Recuperación de actualizaciones del plugin y del instalador; publicación condicionada al CI y aceptación de la candidata.
- Las comprobaciones manuales pendientes se registran en docs/beta-acceptance.json; este cambio no publica por sí solo la versión.

## 0.10.1 — Revista 90's más ligera en el Kobo

- Revista 90's lleva la portada y las carátulas como imágenes JPEG compuestas en el servicio, en lugar de SVG, y ajusta las imágenes de las notas a la pantalla del Kobo. La revista se ve mejor en el lector y pesa alrededor de un 40 % menos.
- El servicio instala la fuente Liberation Sans para componer esos títulos.

## 0.10.0 — Tu Kobo desde cualquier equipo

- Pestaña Kobo renovada: libros del lector con progreso y fecha de lectura, revistas de Prelo y otros EPUB, búsqueda y filtros.
- Desde cualquier equipo: quitar libros del Kobo, enviar cualquier EPUB y cancelar cambios pendientes; el Mac los aplica en la próxima conexión.
- Subrayados de cada libro, incluidos los EPUB que no son de Prelo, con acceso a su nota en el vault.
- Al eliminar una revista de la biblioteca se puede quitar también del Kobo.
- Las ilustraciones de Revista 90's se generan de tres en tres (`AI_IMAGE_CONCURRENCY`).
- Repaso visual: botones alineados, selección más compacta, vistas estrechas legibles y títulos de nota sin encabezados corruptos.
- Una revista en preparación se mantiene al actualizar o recargar el plugin.
- El instalador recompila el servicio aunque un archivo cambie sin variar de tamaño.

## 0.9.2 — Estado real del Kobo y revistas a medias

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
