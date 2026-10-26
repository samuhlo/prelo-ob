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
