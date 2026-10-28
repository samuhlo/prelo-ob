# Desarrollo y publicación

El plugin se compila con Node 22 o posterior; el servicio usa Python 3.11 o posterior. Los comandos siguientes se ejecutan desde el checkout, con las dependencias de desarrollo instaladas.

```sh
cd plugin
npm ci
npm test
npm run build
cd ../server
uv sync --group dev --locked
uv run pytest -q
uv run pytest ../tests -q
cd ..
python3 scripts/audit_public.py
python3 scripts/build_release.py
```

El empaquetador deja los archivos en `dist/releases/<versión>/`. Produce los tres assets de Obsidian, un ZIP del plugin, un ZIP completo para Mac y `SHA256SUMS`. El archivo SQLite WASM está incorporado en `main.js`; las pruebas de distribución abren una base sintética sin archivos externos.

`manifest.json` en la raíz y `plugin/manifest.json` deben coincidir. La versión del tag coincide exactamente con la del manifiesto, sin prefijo `v`. Los empaquetadores usan una lista explícita de archivos públicos; `data/`, configuraciones privadas, informes locales y el historial anterior a la publicación no forman parte de los paquetes.

## Publicar una versión

1. Ejecuta `python3 scripts/set_version.py 0.8.0` (o la siguiente versión). Sincroniza manifiestos, paquetes, lockfiles, versión del servicio y `versions.json`. Actualiza CHANGELOG y, al publicar, los enlaces de descarga.
2. Ejecuta las pruebas y revisa el resultado del empaquetado.
3. Guarda los cambios y sube un tag como `0.7.0`.
4. El workflow de release ejecuta las comprobaciones y adjunta los artefactos a una prerelease de GitHub.
5. Comprueba las descargas y las sumas SHA-256 antes de anunciar la versión.

BRAT instala directamente desde las releases. La publicación en el catálogo oficial es un trámite separado y no se realiza automáticamente por subir el repositorio. [Requisitos de Obsidian](https://docs.obsidian.md/Plugins/Releasing/Submit%20your%20plugin).

## Probar sin afectar una instalación personal

Las pruebas usan directorios temporales, credenciales sintéticas y bases SQLite creadas para cada caso. No ejecutes `scripts/install.py` contra tu vault y servicio de uso diario como sustituto de esas pruebas. `--check` comprueba requisitos y detecta conflictos sin instalar.

Para EPUBCheck usa `scripts/validate_epub.py --checker /ruta/a/epubcheck publicación.epub`. El validador crea un contenedor aislado y copia archivos con `docker cp`; no utiliza montajes del equipo. Las pruebas de USB físico y de arranque de los agentes deben registrarse por separado.

El formato de datos y el identificador de plugin mantienen `margen` por compatibilidad. Un cambio visual o de nombre no debe convertirse en una migración de datos ni de identificadores.

## Avisos de actualización

Cada instalación del plugin consulta las releases públicas de GitHub al arrancar y cada seis horas. Incluye las prereleases porque Prelo se distribuye como beta; descarta borradores, tags no numéricos y versiones sin los tres assets del plugin. Compara major/minor/patch numéricamente. No basta con subir código o un tag: tiene que publicarse la release con sus archivos.

El aviso aparece en Prelo y en Ajustes, con «Actualizar ahora» y un enlace a las novedades. Hay un comando «Comprobar actualizaciones» y un ajuste para desactivar las consultas automáticas. La consulta no usa la credencial del servidor ni transmite contenido del vault. Los errores de conexión no bloquean el plugin.

«Actualizar ahora» descarga los tres assets del plugin y `SHA256SUMS` desde las URL de descarga de este repositorio. Solo escribe si las sumas coinciden, el manifiesto es de `margen` con la versión anunciada y Obsidian cumple `minAppVersion`; el manifiesto se escribe el último. Después recarga los manifiestos y reinicia el plugin con el registro interno de Obsidian, y si no está disponible pide reiniciar Obsidian. No se actualiza mientras otra operación de Prelo está en curso. Una release sin `SHA256SUMS` abre la página de la release. El paquete macOS actualiza el servicio y sus conectores en el Mac. El plugin compara su versión con la que anuncia el servidor y avisa si difieren; no instala ni reinicia servicios. Las instalaciones anteriores a 0.8.0 necesitan una primera actualización por el mecanismo anterior para recibir estos avisos.


## Órdenes USB identificadas

El protocolo de gestión del lector requiere un inventario reciente con identificador del dispositivo y SHA-256 del archivo. Cada orden se asocia al lector en la tabla adicional `kobo_command_targets`, conservando los identificadores y filas anteriores. Al adoptar un catálogo anterior, las órdenes pendientes sin destino pasan a fallidas con un aviso; deben solicitarse de nuevo tras conectar el lector. No se ejecutan automáticamente.

El conector reclama una orden antes de modificar archivos. Una cancelación solo se confirma antes de la reclamación; una orden en ejecución se recupera para el mismo lector con el mismo identificador de reclamación. Los resultados se pueden confirmar de nuevo. Un archivo que cambió se conserva. Los conectores antiguos que consultan órdenes sin identificar el dispositivo no reciben órdenes. Actualiza servicio, conector y plugin conjuntamente; no rebajes solo el servidor después de activar este protocolo.

## Comprobación editorial de la beta

Los prompts llevan una versión explícita y la caché distingue proveedor y destino. Antes de redactar se comprueba que el plan incluya una ficha por nota y conexiones conocidas. Los modos de adaptación fiel requieren conservar los literales detectados (cifras, comandos e imágenes); si siguen faltando tras un reintento se rechaza la edición antes de publicarla o ponerla en cola. Repaso rápido permite condensar datos, pero conserva las referencias a imágenes. El modo original mantiene su cuerpo.

Estas comprobaciones no demuestran equivalencia semántica: negaciones, condiciones, relaciones y explicaciones añadidas necesitan revisión. El corpus sintético de pruebas cubre números de un dígito, cifras incrustadas en otras, valores negativos, comandos, imágenes con identificadores largos, planificación incompleta y caché por proveedor. Antes de una candidata, ejecutar también una muestra real con notas ficticias en castellano y gallego y revisar datos, negaciones, idioma y contenido añadido. Nunca usar notas privadas en CI.

La maquetación se verifica con EPUBCheck y con `check_caption_layout.py` a varios tamaños. Un render en MuPDF no equivale a un Kobo físico; la comprobación del lector sigue siendo independiente.

## Recuperación del instalador público

El instalador registra una transacción privada antes de cambiar archivos. La copia incluye el entorno Python nativo y los agentes, además de aplicación/plugin/configuración; si hay servicio disponible, exporta una biblioteca comprobada antes de empezar. Un fallo restaura esos archivos y arranca la imagen Docker anterior por su identificador, sin reconstruirla ni borrar volúmenes. Un proceso interrumpido requiere `--recover` explícito. Se exige cerrar Obsidian en todos los equipos y no tener trabajos ni USB en curso; no se promete una actualización concurrente con ediciones o cambios de configuración de otros clientes.

Las pruebas de instalación usan vaults/directorios temporales y sustitutos de Docker/launchd: inyectan fallos en entorno nativo, arranque de contenedor, paquete, USB y plugin, además de cubrir éxito, interrupción y rechazo de bind mounts antiguos. No equivalen a una instalación limpia real en otro Mac, que sigue siendo parte de la aceptación manual.


## Preparar la aceptación de una versión

`python scripts/smoke_service.py --build --image prelo-ci --output data/validation` comprueba el servicio en volúmenes temporales y deja EPUB sintéticos. `python scripts/check_beta.py --digest` muestra la huella de las fuentes de producto. Tras completar las comprobaciones requeridas, registra su fecha y un resumen sanitizado en `docs/beta-acceptance.json`, junto a esa huella. `python scripts/check_beta.py` debe pasar antes de crear el tag. Los estados pendientes son deliberados: no cambiarlos para saltarse una prueba manual. El CI normal puede pasar aunque todavía no se haya autorizado publicar la candidata.
