Primera beta pública de Prelo: selecciona notas en Obsidian, prepara una publicación y conecta el Kobo por USB para llevarla y recuperar subrayados.

- **prelo-macos-0.7.0.zip**: instalador guiado, servicio y plugin compilado. Requiere macOS, Docker iniciado y uv.
- **prelo-plugin-0.7.0.zip**: plugin para Obsidian de escritorio en Mac, Windows y Linux; necesita un servicio Prelo existente.
- **main.js, manifest.json, styles.css**: assets para BRAT e instalación manual. SQLite está incorporado a main.js.
- **SHA256SUMS**: sumas de los archivos públicos.

La sincronización USB automática se ejecuta en el Mac. La prueba física específica del automatismo y de las nuevas instalaciones sigue pendiente; empieza con una publicación de prueba. Las pruebas sintéticas no validan hardware.

Cada instalación usa sus propios datos y credenciales. Los paquetes públicos no incluyen archivos de conexión a ningún servidor personal.

Consulta README y docs/instalacion.md antes de instalar. Esta release no implica publicación en el catálogo oficial de complementos de Obsidian.
