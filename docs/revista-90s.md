# Revista 90's: contenido, dirección visual y generación

La portada y las imágenes interiores se generan para el contenido seleccionado en cada edición. La plantilla aporta tipografía, marcos y jerarquía; las ilustraciones no salen de una biblioteca genérica.

## Referencias revisadas

- **Referencia principal desde 0.3:** [Club Nintendo nº 1 de 1994, páginas 20–22 y portada](https://archive.org/details/club-nintendo-no-1-1994_202101/page/20/mode/2up). Se adopta una cabecera más redondeada, blanco y rojo sobre azul profundo, bandas turquesa, paneles de color e ilustración de manual de consola. La composición sigue adaptándose al ancho del lector.
- [Hobby Consolas, nº 17, febrero de 1993](https://www.retrorevistas.com/revistas/hobby-consolas/numeros/017): cabecera dominante, ilustración protagonista, cintas de color y destacados de tamaños diferentes.
- [Entrevista a Wil Overton sobre Super Play](https://www.forgottenworlds.net/blog/the-wil-overton-super-play-interview): ilustración editorial como identidad de la publicación y relación entre el dibujo y sus contenidos.
- [Super Play, nº 7, mayo de 1993, escaneo](https://datassette.s3.us-west-004.backblazeb2.com/revistas/super_play_n.07_mai93.pdf): se revisaron la página 21, dedicada a tecnología, y la 41, con una guía de juego. Cabeceras grandes, ilustraciones explicativas, pies y recuadros; las columnas del papel se adaptan a una lectura fluida en la pantalla pequeña.

Se usan esas observaciones como dirección de diseño. No se incorporan a las publicaciones personajes, logotipos ni imágenes de las revistas originales.

## Recorrido de una edición

1. La IA recibe las notas seleccionadas y propone el orden de lectura.
2. Elige una idea común para la portada y el concepto central de cada nota para su propia carátula retro.
3. Cada encargo visual incluye el concepto, descripción de la escena, notas de origen, pie de imagen y encabezado de destino.
4. El puente local solicita una imagen original por encargo con la herramienta integrada de generación de Codex.
5. El servicio coloca las imágenes junto al contenido correspondiente. Los títulos, pies y párrafos se maquetan como texto.

El validador rechaza referencias a notas ajenas a la selección y exige exactamente una portada general y al menos una ilustración interior por nota. Una imagen que menciona varias notas solo cuenta para la primera, que es donde se coloca. La generación solicita una carátula por nota: con N notas se generan N + 1 imágenes, incluida la portada.

## Dirección base del prompt

Carátula original vertical (3:4) de juego de consola de los 90 para cada nota e ilustración de revista de club de consolas de 1994 para la portada general: contornos dibujados, sombreado de animación, aerógrafo suave y formas expresivas. Turquesa, azul profundo, rojo, verde, amarillo y toques morados. Se prefieren escenas o comparaciones vivas a un esquema isométrico genérico. Escenas originales sin texto incrustado, marcas, personajes de franquicias ni adornos ajenos al tema.

Sobre esa dirección se añade el encargo específico y el material de origen. El prompt efectivo se construye en `server/margen/artwork.py`; las descripciones y leyendas de cada edición se guardan en su manifiesto.

En la prueba de Docker se generaron:

- Portada: de una imagen a varios servicios conectados y con almacenamiento persistente.
- Interior del primer artículo: una misma imagen y varios contenedores con capas de escritura independientes.
- Interior del segundo: sustitución del contenedor conservando datos en almacenamiento separado.

Las primeras exploraciones con un personaje genérico se descartaron para el producto; quedan únicamente como material de trabajo en `data/style-exploration/`.

## Revista de estudio

Tipografía sobria, espaciado amplio, jerarquía formal y portada determinista. No solicita imágenes. La organización con IA comienza desactivada: sin activarla, la edición se genera localmente sin llamadas al modelo.

## Consumo y espera

Revista 90's usa la sesión de ChatGPT del Codex CLI oficial. No cambia a una API de pago si falla. La [documentación oficial de generación de imágenes](https://learn.chatgpt.com/docs/image-generation) explica que las imágenes consumen los límites de uso de Codex.

Los trabajos muestran su fase y se pueden recuperar desde Obsidian. Repetir una solicitud con el mismo identificador no crea otra edición. Las imágenes se reutilizan solo cuando coincide exactamente el encargo, incluido su contenido; una petición distinta genera sus propios recursos.

Si el servicio reinicia durante un trabajo, este queda marcado como interrumpido y requiere un reintento explícito. No se vuelve a gastar automáticamente la cuota.

## Límites

Las imágenes son ayudas visuales generadas y pueden requerir revisión, especialmente en diagramas técnicos. El texto se conserva en el modo de redacción original; los demás modos lo adaptan solo en el EPUB. El ejemplo se revisó visualmente, pero no hay aún un verificador semántico automático de las ilustraciones.

El EPUB es adaptable, con texto seleccionable. No es una revista escaneada ni una maquetación fija de varias columnas.

Desde 0.3 los pies de foto utilizan `div` y `p` en lugar de depender de `figure` y `figcaption`. El fondo y el espaciado pertenecen al contenedor; el párrafo mantiene altura automática e interlineado relativo al tamaño de letra. Esta separación evita depender del tratamiento de elementos HTML5 en lectores EPUB.
