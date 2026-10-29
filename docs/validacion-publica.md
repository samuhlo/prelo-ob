# Aceptación de la candidata beta

La versión preparada es **1.0.2**. No se considera lista para anunciar únicamente porque sus pruebas automáticas pasen. El estado preciso está en [beta-acceptance.json](beta-acceptance.json).

## Comprobaciones automáticas

El CI ejecuta el plugin en macOS, Windows y Linux, pruebas de servicio e instaladores, análisis de dependencias y auditoría de archivos públicos. Construye la imagen del servicio y la arranca con red deshabilitada y un volumen Docker temporal gestionado. Comprueba autenticación, publicaciones, trabajos, órdenes, anotaciones y una restauración en otro contenedor con volumen nuevo; no utiliza bind mounts.

EPUBCheck se descarga de una versión y checksum fijados y se ejecuta en contenedores temporales sin montajes. Se validan muestras de estudio y retro con JPEG. MuPDF verifica pies completos y sin solapamientos en varios tamaños; no es un emulador de Kobo.

Los tests de instalación inyectan fallos por etapa en fixtures. Los controles de IA de esta candidata usan proveedores simulados y comprueban contratos y literales. Las muestras reales de texto sintético en castellano y gallego de la candidata anterior no equivalen a una nueva aceptación de 1.0.0. Esto no demuestra equivalencia semántica universal ni sustituye una revisión de contenido.

## Comprobaciones manuales requeridas

1. Instalar desde el paquete en un Mac limpio, con el runtime y los agentes fuera de Documents. Confirmar reinicio de sesión y Docker disponible. No probar una instalación nueva encima de servicios personales.
2. En Obsidian real, comprobar selección, varios borradores sin conexión, recarga, actualización y conservación de ajustes. Cerrar todos los clientes al actualizar el servicio.
3. Con Kobo físico: copiar publicaciones sintéticas, verificar importación y lectura, crear una cita, recuperar su nota y comprobar que una segunda importación no duplica ni borra comentarios. Retirar únicamente los libros sintéticos. Registrar el modelo/firmware de forma privada y publicar solo un resumen sin identificadores del dispositivo.
4. Recuperar una biblioteca aislada con publicaciones, citas y un EPUB pendiente y servirla de nuevo. Diferenciar esta recuperación lógica de la recuperación completa de un Mac y de sus secretos.

El workflow de publicación exige los resultados de esta versión y de la huella de sus archivos de producto. Las dispensas del propietario se registran como `waived`, no como pruebas superadas, y el workflow solo las admite para las versiones y comprobaciones que enumera: en 1.0.0, la instalación en otro Mac limpio. Ninguna dispensa acepta otra versión o huella. Cambiar el producto invalida una aceptación anterior; `set_version.py` reinicia los estados al preparar otra versión. El archivo es un registro humano revisable, no una prueba de que las acciones físicas se hayan ejecutado.

## Resultados de 1.0.2 (29 de octubre de 2026)

1.0.2 añade la actualización del servidor desde Obsidian a través del conector USB y cambia el estilo del icono lateral. No cambia datos persistidos, identificadores, la copia USB, la importación de subrayados ni el formato de la biblioteca. El propietario confirma que realizó las cuatro comprobaciones manuales con 1.0.2 y que se superaron. Pasan las pruebas automáticas en macOS, Windows y Linux; la entrega del trabajo de launchd, la descarga verificada de una release real y el desempaquetado se han comprobado en un entorno aislado.

## Resultados de 1.0.1 (28 de octubre de 2026)

1.0.1 cambia el logotipo, textos y detalles de la interfaz del plugin y la etiqueta de secciones de la portada. No cambia datos persistidos, identificadores, el conector USB, la importación de subrayados ni el formato de la biblioteca. El propietario confirma que realizó las cuatro comprobaciones manuales con 1.0.1 y que se superaron. Pasan las pruebas automáticas en macOS, Windows y Linux.

## Resultados de 1.0.0 (28 de octubre de 2026)

La cadena completa y sus correcciones están integradas en `main`. El CI remoto pasa en macOS, Windows y Linux y comprueba el servicio y su recuperación aislada. La actualización del plugin desde 0.10.1 se ha probado en Obsidian real con un vault sintético: conserva ajustes y selección, recupera dos borradores tras cerrar sin conexión y los comparte al volver a conectar.

El propietario confirmó la lectura de dos publicaciones sintéticas en un Kobo físico, incluida tabla e imagen JPEG plana. Se recuperaron cuatro subrayados en dos notas; repetir la importación no añadió duplicados ni alteró comentarios. Se retiraron solo los libros de prueba y la base del lector permaneció intacta durante las operaciones del conector. No se actualizó el servicio ni el vault habitual del propietario para esta aceptación.

No se ha instalado este paquete 1.0.0 en otro Mac limpio ni comprobado allí el arranque tras iniciar sesión. El propietario ha descartado esa condición para publicar esta beta, destinada principalmente a su uso personal. Una prueba de una versión anterior o un runtime aislado en un Mac ya configurado no acredita esa condición. `check_beta.py` mantiene el diagnóstico estricto; el workflow aplica únicamente las dispensas documentadas.

## Límites de la beta

- Servicio y automatismo USB en macOS; plugin de escritorio. USB sigue siendo el flujo principal.
- Una biblioteca personal y copias sincronizadas del mismo vault; no alojamiento público multiusuario.
- No se certifican todos los modelos/firmwares Kobo ni trazos manuscritos del lápiz.
- Canvas, Dataview, fórmulas, PDF incrustado y Mermaid renderizado requieren adaptadores; los límites de conversión se mantienen explícitos.
- La IA puede fallar por cuenta, modelo o cuota. Un control literal no garantiza que todas las relaciones o matices sean fieles.
- La sincronización simultánea de un mismo borrador entre equipos requiere prudencia; las pruebas de conservación local no equivalen a un sistema de edición colaborativa.
- La beta externa conserva su actualizador. Una futura distribución en el catálogo oficial de Obsidian requiere adaptar ese mecanismo a sus políticas.

Los informes completos y las evidencias privadas no se incluyen en el repositorio ni en las releases.
