Prelo 0.9.0 permite crear revistas con carpetas completas de apuntes y mejora la lectura en el Kobo.

- La IA trabaja por etapas: un plan editorial del número y la redacción de cada nota por partes, cuatro a la vez. Cada parte se comprueba contra su fuente y se repite si faltan cifras, comandos o imágenes.
- Idioma de la revista: si las notas están en gallego, puedes elegir castellano o galego.
- Los títulos de los artículos salen en el idioma de la revista; la procedencia conserva el de la nota.
- Las notas cortas consecutivas comparten página y se retiran los pies que quedaban solos.
- Las imágenes de las notas se mantienen tal cual. Revista 90’s las enmarca con un bisel retro y su número de figura, y abre cada artículo con una página de ilustración y título.
- Las imágenes WebP se convierten a PNG para que el Kobo las muestre.
- La lectura USB ya no falla con columnas binarias de la base del Kobo.

Actualiza a la vez el servicio del Mac y el puente de Codex con el paquete macOS, y el plugin en cada equipo. Ajustes recomendados en `.env`: `AI_MODEL=gpt-6.1-sol`, `AI_EFFORT_PLAN=high`, `AI_EFFORT_WRITE=medium`, `AI_CONCURRENCY=4`. Consulta «Cómo trabaja la IA» en `docs/instalacion.md`.

Assets: `prelo-plugin-0.9.0.zip`, `prelo-macos-0.9.0.zip`, `main.js`, `manifest.json`, `styles.css` y `SHA256SUMS`.
