# Prelo

<img src="assets/prelo-logo.svg" alt="PrelO, con un cristal amarillo como O" height="56" />

**Elige qué leer. Conecta el cable. Vuelve con subrayados.**

Prelo convierte una selección de notas de Obsidian en una publicación EPUB para Kobo. Preparas la lectura, la dejas en la cola y, cuando conectas el lector por USB al Mac, el conector recoge las anotaciones y entrega las publicaciones pendientes. Los subrayados vuelven al vault con enlaces a sus notas de origen.

**Beta actual: 0.8.1.** [Descargar para Mac](https://github.com/samuhlo/prelo-ob/releases/download/0.8.1/prelo-macos-0.8.1.zip) · [Descargar solo el plugin](https://github.com/samuhlo/prelo-ob/releases/download/0.8.1/prelo-plugin-0.8.1.zip) · [Releases](https://github.com/samuhlo/prelo-ob/releases)

## Instalar

Prelo tiene dos piezas: un servicio en el Mac que genera las publicaciones y gestiona el Kobo, y un plugin de Obsidian que puede usarse desde Mac, Windows o Linux.

### En el Mac al que conectarás el Kobo

1. Ten Obsidian y un vault abierto al menos una vez. Instala [uv](https://docs.astral.sh/uv/getting-started/installation/) y [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/), o usa tu Colima ya configurado e iniciado.
2. Descarga y descomprime **prelo-macos-0.8.1.zip** desde la release. Cierra Obsidian antes de instalar.
3. Abre **Instalar Prelo.command**. Indica la carpeta del vault y elige si quieres usar tu Codex CLI para IA; puedes empezar sin IA.
4. Abre Obsidian. En **Ajustes → Complementos de la comunidad**, activa Prelo si es necesario.

El paquete incluye el plugin compilado: no necesitas Node ni compilar el proyecto. El instalador genera una credencial privada, prepara el servicio, configura el conector USB para tu vault y guarda una copia de la configuración anterior al actualizar.

[Guía de instalación, requisitos, actualizaciones y desinstalación](docs/instalacion.md).

### Plugin en otros ordenadores

Puedes instalarlo con [BRAT](https://github.com/TfTHacker/obsidian42-brat): añade `samuhlo/prelo-ob` como plugin beta y selecciona la versión `0.8.1`. También puedes descomprimir el ZIP del plugin y copiar `margen` a `.obsidian/plugins/` de tu vault.

Después importa el archivo privado de conexión de **tu propio servidor** desde **Prelo: Conectar con el servidor**. Para usarlo desde otro equipo, el Mac necesita una dirección accesible por HTTPS en tu red privada; `127.0.0.1` solo sirve en el propio Mac. [Conectar otro ordenador](docs/instalacion.md#conectar-otro-ordenador).

Instalar únicamente el plugin requiere que ya exista un servicio Prelo. La publicación en GitHub permite instalarlo con BRAT o manualmente; aún no está en el catálogo oficial de complementos de Obsidian.

## El recorrido

1. Pulsa el icono de **revista** de Prelo en Obsidian.
2. Selecciona notas por título o carpeta y ordénalas.
3. Elige **Revista de estudio** o **Revista 90's**, la redacción y los apoyos para estudiar, y crea la publicación.
4. Conecta el Kobo por USB al Mac y acepta **Conectar** en su pantalla.
5. El conector importa los subrayados, copia la cola, verifica los archivos y expulsa el lector.
6. Lee sin conexión. En la siguiente conexión USB, las nuevas citas regresan al vault.

La sincronización con el Kobo es por USB. El cable forma parte del ritmo del producto: preparar una selección y reservar un momento para llevarla y recoger lo leído.

## Qué incluye

- Una vista propia en Obsidian con selección, biblioteca, borradores y cola.
- Avisos de nuevas versiones en el plugin, comprobación manual y versión del servidor visible. Cada equipo actualiza su plugin por separado mediante BRAT o el ZIP.
- EPUB 3 con portada, índice, imágenes locales, tablas y código.
- **Revista de estudio** sin IA por defecto. **Revista 90's** con portada general y una carátula de juego retro por nota mediante Codex.
- **Redacción independiente del diseño**: notas originales (por defecto), revista narrativa, explicación sencilla, paso a paso o repaso rápido.
- **Apoyos opcionales con IA**: esquemas y tablas, preguntas con respuestas o un kit completo; compatibles con ambos tipos de revista. Son contenido Markdown legible sin conexión, no imágenes generadas adicionales.
- El modo original conserva el cuerpo de las notas. Los demás adaptan solo el EPUB, identifican el texto como adaptación con IA y conservan la procedencia; el vault no se modifica. Repaso rápido condensa y omite detalles.
- **Instrucciones extra**: pide, por ejemplo, que cada tema vaya seguido de su examen resuelto. Activan IA aunque el texto se conserve original. Puedes bloquear el orden exacto de la selección; ese bloqueo prevalece sobre cualquier reorganización.
- Los borradores guardan también la redacción, los apoyos y las preferencias de IA y envío.
- Ediciones independientes e identidades estables para conservar la procedencia.
- Importaciones repetibles sin duplicar citas; actualizaciones que conservan comentarios anteriores.
- Biblioteca con límite configurable de almacenamiento y ediciones protegidas. En el menú de cada publicación puedes **Eliminar EPUB**: retira el archivo y cancela su envío, conservando subrayados e historial. Las copias del Kobo o del vault se mantienen.
- Servicio personal, con acceso autenticado y datos propios. No requiere un servicio alojado por el autor.

## Compatibilidad y estado

| Componente | Compatibilidad de esta beta |
| --- | --- |
| Servicio y automatización USB | macOS, con Docker y uv; sesión del usuario iniciada |
| Plugin de Obsidian | Obsidian de escritorio 1.8 o posterior, en macOS, Windows y Linux |
| Kobo | Circuito manual comprobado con Kobo Libra Colour; otros modelos y firmwares requieren prueba |
| Móvil | No incluido |

El conector USB automático tiene pruebas con dispositivos simulados; su validación física específica sigue pendiente. Publicamos esta versión como **beta**, con [límites y comprobaciones documentados](docs/validacion-publica.md).

El Mac debe permanecer encendido, con su sesión iniciada y Docker disponible. Obsidian puede estar cerrado durante la sincronización USB. Prelo escribe los subrayados en el vault del Mac; si utilizas otros equipos, la sincronización de esos Markdown depende de la herramienta que ya uses para tu vault.

## IA y datos

Puedes preparar revistas de estudio sin IA. Para la organización y las ilustraciones con Codex, cada persona utiliza su propia instalación oficial de Codex CLI y su propia cuenta con acceso a Codex. Prelo no distribuye ni comparte una cuenta de ChatGPT. [Autenticación de Codex](https://learn.chatgpt.com/docs/auth).

Al activar IA, las notas seleccionadas se envían al proveedor elegido y consumen sus límites o cuota. Sin IA, el contenido se procesa en tu servicio. No hay telemetría añadida por Prelo. [Datos, permisos y credenciales](docs/privacidad.md).

## Desarrollo

Código del plugin en `plugin/`, servicio Python en `server/` e instaladores en `scripts/`. El identificador técnico `margen` se conserva para actualizar las instalaciones anteriores sin duplicar el plugin ni romper anotaciones.

[Guía de desarrollo y releases](docs/desarrollo.md) · [Dirección de producto](docs/producto.md) · [Estilo Revista 90's](docs/revista-90s.md) · [Historial](CHANGELOG.md)

Licencia [MIT](LICENSE). El cristal del logo procede de [Anaco](https://github.com/samuhlo/anaco-ob); el icono lateral conserva la revista. [Avisos de terceros](THIRD_PARTY_NOTICES.md).
