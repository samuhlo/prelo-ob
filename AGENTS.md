# Prelo

Prelo publica notas de Obsidian para leer en Kobo y recuperar subrayados mediante USB.

- Mantener USB como flujo principal. Wifi queda fuera del alcance actual.
- El logo PrelO pertenece a la cabecera; conservar el icono de revista en el lateral y los demás controles. Preguntar antes de extender cambios visuales a otras superficies.
- Conservar los identificadores persistidos `margen`, los nombres de ediciones y las claves de anotaciones sin una migración explícita.
- No registrar credenciales ni contenido de notas. Los ejemplos reales y las evidencias privadas viven en `data/`, excluido de Git.
- No publicar historial local, archivos de conexión ni informes privados. Usar `scripts/public_files.py`, `scripts/audit_public.py` y el generador de releases.
- Los datos del servicio viven en un volumen Docker gestionado. No usar bind mounts de Documents ni iniciar contenedores antiguos que los tengan.
- Validar EPUB con contenedores sin montajes y `docker cp`; aplicar tiempos máximos a las operaciones Docker. No reiniciar Colima ni modificar permisos de macOS para una validación.
- Los conectores nativos se ejecutan desde Application Support, fuera del checkout y de Documents.
- Una base SQLite sintética no valida hardware. La prueba USB requiere un Kobo físico y debe registrarse por separado.
- Comprobar el plugin con `npm test` y `npm run build`, y el servicio con `uv run pytest`. Probar instaladores con fixtures temporales; no ejecutar instalaciones nuevas contra los servicios personales para hacer pruebas.
