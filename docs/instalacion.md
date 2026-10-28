# Instalar Prelo

La primera beta usa un **Mac como servidor y punto de conexión USB del Kobo**. El plugin puede usarse también desde Obsidian en Windows y Linux. No incluye un servidor público: cada persona mantiene su biblioteca y sus credenciales.

## Requisitos del Mac

- Obsidian de escritorio 1.8 o posterior y un vault ya creado.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). Si usas Homebrew: `brew install uv`. El lanzador utiliza uv para obtener Python 3.13 cuando hace falta.
- [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) abierto, o una instalación de Colima ya configurada e iniciada. El instalador utiliza el contexto Docker seleccionado y lo recuerda para las actualizaciones.
- Internet durante la instalación para las dependencias y la imagen del servicio.
- Espacio para la imagen Docker y la biblioteca; la cuota inicial de publicaciones es 10 GB, no una reserva de espacio.

El instalador no instala ni reinicia Docker/Colima, no cambia permisos del sistema y no monta tu vault dentro del contenedor.

## Instalación guiada

1. Descarga `prelo-macos-<versión>.zip` desde [Releases](https://github.com/samuhlo/prelo-ob/releases). Usa el plugin, servicio y conectores de la misma versión.
2. Descomprime el ZIP y cierra Obsidian.
3. Abre `Instalar Prelo.command` e indica la ruta del vault: debe contener la carpeta `.obsidian`.
4. Elige si quieres usar Codex para IA. Para empezar, responde **N**: Revista de estudio funciona sin IA.
5. Espera al mensaje de instalación terminada. Abre Obsidian y activa Prelo en Complementos de la comunidad si fuera necesario.

También puedes iniciar el mismo asistente desde Terminal, dentro de la carpeta descomprimida:

```sh
sh "Instalar Prelo.command"
```

Para dar la ruta y elegir el modo sin preguntas:

```sh
sh "Instalar Prelo.command" --vault "/ruta/a/Mi vault" --ai none
```

Para comprobar los requisitos sin instalar:

```sh
sh "Instalar Prelo.command" --vault "/ruta/a/Mi vault" --check
```

El asistente guarda la aplicación y la configuración en `~/Library/Application Support/Prelo/`, registra el conector como agente de tu usuario y usa un volumen Docker gestionado. Puedes borrar el ZIP y la carpeta de descarga después de instalar. La credencial se genera para esa instalación y se guarda en archivos privados; no aparece en la salida del instalador.

Si ya hay otro servicio en el puerto 8765 o un proyecto Docker `prelo` que no reconoce, se detiene antes de sustituirlo. Las instalaciones anteriores hechas a mano o integradas en un homelab se mantienen mediante su propio despliegue; usa la opción de instalar solo el plugin para conectarte a ellas.

## Primera sincronización USB

1. En Obsidian, abre Prelo con el icono de revista, selecciona dos notas de prueba y crea una Revista de estudio.
2. Conecta el Kobo al Mac y acepta **Conectar** en su pantalla.
3. El conector recoge anotaciones, copia las publicaciones pendientes, comprueba los archivos y expulsa el lector.
4. Abre la revista en el Kobo, subraya una frase y vuelve a conectarlo al Mac.
5. Comprueba la cita y su enlace en `Prelo/Subrayados/`. Repetir la conexión no debe duplicarla.

Usa primero notas y una publicación de prueba. Este recorrido debe verificarse con tu lector real: las pruebas automáticas utilizan SQLite y dispositivos simulados. Los subrayados manuscritos con lápiz no se importan.

## Conectar otro ordenador

Instala BRAT desde Complementos de la comunidad, añade `samuhlo/prelo-ob` y selecciona la misma versión que el servicio. BRAT instala los archivos compilados de la release. [Guía de BRAT](https://github.com/TfTHacker/obsidian42-brat/blob/main/BRAT-DEVELOPER-GUIDE.md).

Si prefieres instalación manual, descarga `prelo-plugin-<versión>.zip` y copia su carpeta `margen` a `.obsidian/plugins/` de tu vault. Activa Prelo. El nombre técnico de esa carpeta se conserva por compatibilidad.

El plugin necesita llegar al servicio de tu Mac. Para acceso desde otros ordenadores, prepara una dirección HTTPS en tu red privada, por ejemplo mediante tu VPN o proxy privado. La instalación inicial escucha solo en `127.0.0.1:8765`: no es accesible desde otro equipo sin esa configuración de red. No abras el puerto al internet público.

Copia de forma privada `~/Library/Application Support/Prelo/conexion-prelo.json` y sustituye **solo** `serverUrl` por la dirección HTTPS de tu servidor. En el segundo equipo, ejecuta **Prelo: Conectar con el servidor** e importa ese archivo. No incluyas la credencial en Git, un issue ni un enlace público.

El paquete completo también permite instalar solo el plugin, usando Python 3.11 o posterior:

```sh
python3 scripts/install.py --plugin-only --vault "/ruta/al/vault" --connection "/ruta/privada/conexion-prelo.json"
```

En Windows puedes usar `py -3` en lugar de `python3`. El archivo de conexión es opcional al instalar: también puedes importarlo después desde Obsidian.

Los equipos necesitan sus propias copias del vault para resolver las notas seleccionadas. Prelo no instala ni configura tu sistema de sincronización de notas. El Kobo se conecta por USB al Mac que ejecuta el conector.

## Activar IA

Instala el Codex CLI oficial, inicia sesión con tu propia cuenta y comprueba el acceso:

```sh
codex login
codex login status
```

Después ejecuta el instalador con `--ai codex`. Prelo mantiene la autenticación de Codex en el Mac y usa su modo no interactivo para la edición y las imágenes. Requiere acceso a Codex, compatibilidad del CLI y cuota disponible; los errores de autenticación o límites se muestran como errores, sin cambiar a una clave API por su cuenta. [Autenticación](https://learn.chatgpt.com/docs/auth), [modo no interactivo](https://learn.chatgpt.com/docs/non-interactive-mode).

### Cómo trabaja la IA

Una edición con IA se prepara por etapas. Primero, una llamada propone el plan del número a partir de un resumen de cada nota: título, ruta, encabezados y comienzo. Si la selección es pequeña, recibe las notas completas. Después, si la redacción o los apoyos lo requieren, cada nota se divide en partes de unos 20.000 caracteres, sin cortar bloques de código, y se redacta en llamadas paralelas. Cada parte se comprueba: si faltan cifras, comandos o imágenes de la fuente, se pide una vez más con esa lista. Las partes terminadas se guardan durante 30 días en la biblioteca, así que reintentar una edición fallida solo repite lo que faltaba.

Ajustes opcionales de `service.env` en Application Support/Prelo para el instalador público, o del `.env` de tu despliegue avanzado (aplica después la actualización por el mismo mecanismo con que instalaste):

| Ajuste | Uso |
|---|---|
| `AI_MODEL_PLAN`, `AI_EFFORT_PLAN` | Modelo y esfuerzo de razonamiento del plan editorial. |
| `AI_MODEL_WRITE`, `AI_EFFORT_WRITE` | Modelo y esfuerzo de la redacción por partes. |
| `AI_MODEL`, `AI_EFFORT` | Valores por defecto de ambas etapas. Vacíos, Codex usa su modelo predeterminado. |
| `AI_CONCURRENCY` | Llamadas simultáneas (4 por defecto; con 4, una edición de 13 notas tardó la mitad que con 2). |
| `AI_IMAGE_CONCURRENCY` | Ilustraciones de Revista 90's a la vez (3 por defecto). El puente no supera `AI_CONCURRENCY` procesos de Codex. |
| `AI_CHUNK_CHARS`, `AI_TIMEOUT` | Tamaño de cada parte y segundos por llamada. |

Con Codex, la configuración recomendada es `AI_MODEL=gpt-6.1-sol`, con `AI_EFFORT_PLAN=high` para el plan y `AI_EFFORT_WRITE=medium` para la redacción.

El puente ignora la configuración personal de Codex (`~/.codex/config.toml`) para no depender de ella: indica aquí el modelo si quieres uno concreto.

Para proveedores compatibles, el servicio conserva `AI_BASE_URL`, `AI_MODEL` y `AI_API_KEY`; es una configuración avanzada del despliegue. Ese modo organiza y adapta texto, añade apoyos de estudio y no ofrece la generación de imágenes de Revista 90's de esta versión.

## Actualizar

Descarga el paquete de la nueva release, cierra Obsidian y ejecuta su instalador indicando el mismo vault. Mantiene la credencial del servicio y respalda la configuración anterior. Selecciona el mismo contexto Docker usado en la instalación inicial.

Desde 0.9.1, el plugin se actualiza en el propio Obsidian: pulsa «Actualizar ahora» en el aviso de Prelo o en Ajustes → Prelo. Descarga `main.js`, `manifest.json` y `styles.css` de la release, comprueba sus sumas SHA-256 y reinicia el plugin sin tocar `data.json`. Cada equipo se actualiza por separado; el servicio del Mac sigue necesitando el paquete para macOS.

También puedes actualizar desde BRAT. En instalación manual sustituye `main.js`, `manifest.json` y `styles.css`, conservando `data.json`. La versión 0.7 ya no necesita descargar un archivo WASM aparte; un archivo antiguo sobrante no impide usar el plugin.

Las instalaciones existentes conservan las claves `margen_id`, `margen_lectura`, los nombres de EPUB y los marcadores de citas. No renombres esos datos para cambiar la marca visual.

## Diagnóstico

| Síntoma | Comprobación |
| --- | --- |
| Falta uv | Instálalo y vuelve a abrir Terminal. |
| Docker no responde | Abre Docker Desktop o inicia tu Colima habitual y comprueba el contexto seleccionado. |
| Puerto 8765 ocupado | Usa la conexión del servicio existente; no arranques una segunda biblioteca encima. |
| El plugin está vacío o desconectado | Revisa el servicio, la dirección y la credencial en Ajustes → Prelo. |
| El Kobo no aparece | Acepta Conectar en su pantalla y usa un cable que transmita datos. |
| El conector se detiene por WAL | Expulsa el lector y vuelve a conectarlo; no borres archivos de su base de datos. |
| La IA falla | Comprueba `codex login status`, la versión del CLI y los límites de tu cuenta. |

La configuración nativa está en `usb.json` y la del servicio en `service.env`, dentro de Application Support/Prelo. Los registros del conector contienen tipos de error y estados; no adjuntes esos archivos de configuración a incidencias.

## Desinstalar conservando los datos

Desactiva Prelo en Obsidian. Para detener los agentes creados por el instalador público:

```sh
launchctl bootout "gui/$(id -u)/local.prelo.kobo"
launchctl bootout "gui/$(id -u)/local.prelo.codex-bridge"
```

El segundo puede no existir si no activaste IA. Retira sus archivos `local.prelo.*.plist` de `~/Library/LaunchAgents/` para que no se inicien en el siguiente acceso. Detén el servicio desde Docker Desktop o Compose; consulta `installation.json` para el contexto usado. Conserva Application Support/Prelo, sus copias y el volumen Docker mientras quieras recuperar la biblioteca. Eliminar el plugin o detener el servicio no necesita borrar notas, EPUB ni volúmenes.


## Recuperar una actualización interrumpida

Cierra Obsidian en todos los equipos y espera a que terminen las ediciones y la copia USB antes de actualizar. El instalador público rechaza un servicio ocupado. Guarda una copia privada de la aplicación, entorno nativo, ajustes, agentes y plugin, además de exportar la biblioteca cuando el servicio está disponible. Conserva también la identidad exacta de la imagen Docker anterior.

Si una etapa falla, intenta restaurar esos archivos y la imagen anterior sin borrar el volumen. Si se interrumpe el proceso por completo, la siguiente instalación se detiene al detectar el registro pendiente. Desde el paquete de la versión nueva puedes ejecutar:

```sh
sh "Instalar Prelo.command" --recover
```

No borres `update-in-progress.json` ni el backup para saltarte el aviso. Una recuperación rechaza configuraciones antiguas con bind mounts. Las copias contienen datos privados y nunca deben adjuntarse a incidencias. La exportación de biblioteca es una copia lógica de procedencia, anotaciones y archivos protegidos/pendientes; no garantiza conservar todos los EPUB no protegidos.

Este procedimiento corresponde al instalador público (`prelo`). Las instalaciones gestionadas por un homelab (`margen`) conservan su despliegue propio; no ejecutes el instalador público encima de ellas.


Desde una versión anterior a 0.11, instala esta candidata con el paquete completo/BRAT o con copia manual del plugin y Obsidian cerrado: la versión antigua todavía no incorpora la nueva recuperación del autoactualizador. Actualiza también el conector USB antes de solicitar retiradas; las órdenes anteriores sin un lector identificado quedan pendientes de revisión, no se ejecutan por su cuenta.

Los adjuntos admiten hasta 20 megapíxeles y 20.000 píxeles por lado, con 80 megapíxeles por edición, además del límite de bytes. La cuota de biblioteca controla EPUB e imágenes; catálogo/procedencia, copias privadas del instalador y archivos nativos del Mac tienen un alcance distinto. Conserva espacio libre para las copias y la recuperación.

### Identidad del lector al actualizar a 1.0 beta

El conector identifica el Kobo con un hash de su número de serie (primer campo de
`.kobo/version`), sin incluir el firmware ni guardar el número de serie en claro.
Un lector sin ese dato requiere revisar sus metadatos; la ruta de montaje no lo sustituye.
Las órdenes pendientes o en ejecución con el hash antiguo de 20 caracteres pasan a
fallidas, conservando su destino y contenido. Ese hash no permite demostrar qué serie
lo originó. Conecta de nuevo el Kobo, revisa su inventario y solicita otra vez los cambios;
puedes descartar el aviso antiguo en «Próxima conexión». Ninguna retirada se reasigna
por coincidencia de ruta o de archivos. Actualiza servicio y conector juntos, sin una
copia USB activa. Los nombres de ediciones y las claves de citas no cambian.

### Recuperación de una actualización del plugin

`.prelo-update/pending.json` se conserva hasta confirmar la activación. Que los tres
archivos coincidan con la descarga solo confirma su escritura. Una reversión registra
su fase antes de restaurar y restaura `main.js` al final para conservar el código de
recuperación durante una interrupción. Si Obsidian no permite activar desde el plugin,
reinícialo; el registro puede permanecer hasta la siguiente actualización explícita.

El instalador manual comparte ese registro: recupera primero una sustitución parcial,
registra su propio conjunto de archivos y retira la señal anterior solo al completar la
instalación. Cierra Obsidian antes de usarlo. Una reversión incompleta conserva su señal
para el siguiente arranque o reintento; no borres `.prelo-update` para forzar el proceso.
