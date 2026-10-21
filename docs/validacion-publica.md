# Estado de la beta pública

Versión 0.7.0, preparada el 21 de octubre de 2026.

## Comprobaciones automatizadas

La suite del servicio cubre generación EPUB, enlaces y procedencia, autenticación, biblioteca, retención, cola y recibos, y conservación de anotaciones. Las pruebas USB usan dispositivos simulados y SQLite sintético.

La suite del plugin cubre selección, búsqueda, reordenación, fechas, importaciones idempotentes y lectura de SQLite. La prueba de distribución comprueba SQLite incorporado al paquete sin un archivo WASM externo.

Los instaladores se prueban con vaults temporales: actualización sin perder ajustes ni otros plugins, copia previa, rechazo de conexiones inválidas, selección explícita del vault y rechazo de un puerto ocupado por otra instalación. Estas pruebas no equivalen a ejecutar un instalador completo en un Mac nuevo.

CI vuelve a ejecutar estas comprobaciones antes de producir los paquetes. Las releases contienen sumas SHA-256 para verificar los archivos descargados.

## Comprobaciones con lector físico

El circuito manual del prototipo se probó con un Kobo Libra Colour: transferencia de EPUB, lectura y retorno de subrayados con enlaces a sus notas originales. También se verificó la importación repetida sin duplicados.

La validación física específica del conector automático, las nuevas instalaciones completas y otros modelos o versiones de firmware siguen pendientes. Por eso la versión se distribuye como **beta**. La guía de instalación incluye un recorrido corto con una publicación de prueba para comprobar tu equipo.

## Límites

- USB automático solo en macOS; los clientes Windows/Linux usan el servicio del Mac.
- El Mac necesita sesión iniciada y Docker disponible. El arranque tras reiniciar completamente el equipo requiere comprobar el desbloqueo del disco y el inicio de Docker.
- El contenido avanzado de Obsidian —Canvas, Dataview, fórmulas, PDF incrustado y Mermaid renderizado— necesita adaptadores. El código Mermaid se conserva como código.
- No se importan trazos manuscritos del lápiz.
- Las anotaciones sin una procedencia inequívoca quedan pendientes de vincular.
- La IA puede fallar por autenticación, versión del CLI, compatibilidad del proveedor o límites de la cuenta. El cuerpo original de las notas se conserva.
- El servicio no ofrece aislamiento entre usuarios ni está preparado como alojamiento público multiusuario.
