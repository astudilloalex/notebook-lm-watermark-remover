# Uso del procesador por consola

Los ejemplos se ejecutan desde la carpeta `app/`. La interfaz con botones se describe en [USO.md](USO.md).

Herramienta independiente para vídeos horizontales y Shorts de NotebookLM. Ejecuta FFmpeg nativo en tu equipo. El script no contiene llamadas HTTP, no carga la página analizada y no descarga motores ni modelos.

Incluye perfiles por formato, limpieza con `delogo`, recorte del cierre, imagen comparativa, lotes, exploración opcional por contraste y sustitución por un PNG propio. Requiere Python 3.10 o posterior y una instalación de FFmpeg que incluya `ffprobe`, `delogo` y `libx264`. No requiere paquetes de Python.

## Empezar

Descarga y descomprime el paquete. Abre una terminal dentro de esta carpeta y comprueba:

```bash
python3 --version
ffmpeg -version
ffprobe -version
```

En Windows puedes usar `py` en lugar de `python3`. En algunas instalaciones el comando es `python`.

FFmpeg se obtiene desde [su página oficial](https://ffmpeg.org/download.html). En Ubuntu/Debian también puedes instalarlo con `sudo apt install ffmpeg`; en macOS, con Homebrew instalado, `brew install ffmpeg`. Python está disponible en [python.org](https://www.python.org/downloads/).

Si FFmpeg no está en el PATH, indica las rutas explícitamente:

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --ffmpeg "/ruta/ffmpeg" --ffprobe "/ruta/ffprobe"
```

En Windows, por ejemplo:

```powershell
py notebooklm_ffmpeg.py "C:\Videos\video.mp4" --ffmpeg "C:\ffmpeg\bin\ffmpeg.exe" --ffprobe "C:\ffmpeg\bin\ffprobe.exe"
```

## Uso básico

```bash
python3 notebooklm_ffmpeg.py "video.mp4"
```

Genera `video_limpio.mp4` junto al original. Conserva la resolución y la tasa de fotogramas detectada en el modo predeterminado. Recodifica el vídeo en H.264 con CRF 18 y preset `medium`; el audio se exporta en AAC a 192 kbit/s.

El original se protege siempre. Una salida existente solo se reemplaza al indicar `--sobrescribir`. El resultado se genera primero en un archivo temporal de la carpeta de destino; si FFmpeg falla, se retira ese temporal.

## Perfiles y recorte del cierre

| Perfil | Identificación automática | Cierre eliminado por defecto |
|---|---|---:|
| `explainer` | Horizontal aproximadamente 16:9, cerca de 24 fps | 72 fotogramas |
| `cinematic` | Horizontal aproximadamente 16:9, cerca de 30 fps | 90 fotogramas |
| `short` | Vertical aproximadamente 9:16 | 90 fotogramas |
| `legacy` | Selección manual para Shorts antiguos | 60 fotogramas |
| `manual` | Selección manual con `--rect` | Sin recorte automático |

Se admiten, entre otras, las resoluciones 1280×720, 1920×1080, 406×720 y 720×1280 mediante el escalado de coordenadas. La tolerancia de identificación horizontal es de 0,1 fps, lo que incluye 23,976 y 29,97 fps.

Los perfiles son reglas basadas en los formatos revisados en octubre de 2026. La identificación comprueba proporción y FPS; no autentica que el vídeo provenga de NotebookLM ni reconoce visualmente la pantalla final. Una futura exportación puede necesitar otras coordenadas o un recorte diferente.

Para forzar un perfil:

```bash
python3 notebooklm_ffmpeg.py "horizontal.mp4" --perfil cinematic
python3 notebooklm_ffmpeg.py "vertical.mp4" --perfil short
python3 notebooklm_ffmpeg.py "short_antiguo.mp4" --perfil legacy
```

Conserva todo el cierre o cambia el corte:

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --sin-recorte
python3 notebooklm_ffmpeg.py "video.mp4" --recortar-fotogramas 60
python3 notebooklm_ffmpeg.py "video.mp4" --recortar-segundos 2.5
```

Estas tres opciones son mutuamente excluyentes. El recorte predeterminado por fotogramas usa el total indicado por el contenedor; si no existe, ffprobe lo cuenta. Si el vídeo no tiene suficientes fotogramas, se detiene con una explicación.

Para una exportación con FPS variables se recomienda `--recortar-segundos` o `--sin-recorte`; cuando la tasa media y nominal difieren de forma apreciable, el corte automático por fotogramas se rechaza. La salida se normaliza a una cadencia constante: en modo calidad usa la tasa media detectada. Esta comprobación de FPS variables es aproximada.

## Comprobar la región antes de exportar

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --previsualizar "vista.png" --segundo 1
```

Genera un PNG con dos paneles: a la izquierda el original con la región marcada en rojo; a la derecha el resultado. Esta operación no crea un MP4 ni recorta el cierre. Para vídeos inferiores a un segundo usa, por ejemplo, `--segundo 0.2`.

Para exportar solo una muestra breve:

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --duracion-prueba 5 -o "prueba.mp4"
```

La muestra empieza en el inicio del vídeo y respeta el recorte configurado. Para comprobar un archivo corto sin descontar el cierre, añade `--sin-recorte`.

Para inspeccionar el plan y obtener un comando FFmpeg equivalente sin crear resultados:

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --simular
```

La simulación puede leer el vídeo completo si necesita contar fotogramas o si activas la exploración inteligente.

## Ajustar coordenadas

`--rect X:Y:ANCHO:ALTO` utiliza píxeles de la resolución del vídeo. El origen `(0,0)` es la esquina superior izquierda. El rectángulo debe dejar al menos un píxel exterior en cada lado para que `delogo` pueda interpolar.

Ejemplo para el perfil horizontal normal a 1280×720:

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --rect 1141:686:134:24 --previsualizar "zona.png"
```

Para una exportación no reconocida:

```bash
python3 notebooklm_ffmpeg.py "otro.mp4" --perfil manual --rect 1141:686:134:24
```

`manual` conserva el cierre salvo que indiques un corte explícito. Si solo necesitas corregir la posición y mantener los 72 fotogramas del perfil Explainer, usa `--perfil explainer --rect ...`.

Coordenadas calculadas para perfiles habituales:

| Formato | Región X:Y:ANCHO:ALTO |
|---|---|
| Horizontal 1280×720 | `1141:686:134:24` |
| Horizontal 1920×1080 | `1712:1029:203:36` |
| Short 406×720 | `291:688:109:27` |
| Short 720×1280 | `516:1223:193:48` |

Para Explainer con el logo a la izquierda, usa `--rtl`. En Cinematic se conserva el perfil inferior derecho, como en el comportamiento analizado. `--rect` permite elegir cualquier otra posición.

## Detección inteligente opcional

```bash
python3 notebooklm_ffmpeg.py "horizontal.mp4" --deteccion-inteligente
```

Explora una imagen por segundo, calcula la varianza del promedio RGB en dos ventanas predefinidas —inferior y superior central— y agrupa las muestras en intervalos. El umbral predeterminado es 400. Se aplica `delogo` únicamente en los intervalos elegidos; las transiciones se amplían ligeramente. Si no encuentra candidatos, vuelve al rectángulo fijo del perfil.

La estrategia reproduce la idea del método inspeccionado con FFmpeg nativo. El muestreo temporal y los límites de los intervalos pueden variar ligeramente respecto de la versión del navegador. Es una heurística de contraste: un título o un dibujo dentro de las ventanas también puede activar la limpieza. Revisa el resultado cuando la utilices.

```bash
python3 notebooklm_ffmpeg.py "horizontal.mp4" --deteccion-inteligente --umbral 600
```

Solo corresponde a los perfiles horizontales y no se combina con `--rect` ni con `--logo`. Recorre el vídeo completo y aumenta el tiempo de trabajo.

## Calidad, velocidad y audio

| Modo | FPS de salida | CRF | Preset |
|---|---|---:|---|
| `calidad` —predeterminado— | Tasa detectada | 18 | `medium` |
| `equilibrado` | 30 | 23 | `veryfast` |
| `rapido` | 15 | 28 | `ultrafast` |

Los modos rápido y equilibrado usan los FPS y CRF identificados en la página. El modo calidad utiliza el mismo CRF 18 con un preset orientado a una mejor eficiencia de compresión. `medium` requiere más tiempo que `superfast`; el tamaño y aspecto de los archivos no serán idénticos a los generados por la página.

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --modo rapido
python3 notebooklm_ffmpeg.py "video.mp4" --modo calidad --crf 16 --preset slow
python3 notebooklm_ffmpeg.py "video.mp4" --audio copiar
python3 notebooklm_ffmpeg.py "video.mp4" --audio sin
```

El vídeo se recodifica. CRF 18 conserva buena calidad visual, pero no constituye una copia sin pérdidas. `--crf 0` cambia la compresión del vídeo; la interpolación de la región sigue modificando píxeles.

El audio predeterminado se recodifica a AAC para recortar su duración. `--audio copiar` conserva sus paquetes originales, siempre que su códec sea compatible con MP4; el corte queda limitado a la granularidad de esos paquetes. Solo se conserva la primera pista de audio. No se copian subtítulos, pistas de datos, capítulos ni todas las etiquetas del original.

## Añadir un logo propio

```bash
python3 notebooklm_ffmpeg.py "video.mp4" --logo "mi_logo.png"
```

El PNG se ajusta proporcionalmente, se centra dentro de la región limpiada y se superpone. Se recomienda transparencia. También funciona con `--previsualizar`; no se combina con la exploración inteligente.

## Procesar varios archivos

```bash
python3 notebooklm_ffmpeg.py "uno.mp4" "dos.mp4" --carpeta-salida "limpios"
```

Si una entrada falla, continúa con las demás y termina con código de salida 1. Evita lotes cuyos archivos tengan el mismo nombre base dentro de una misma carpeta de salida. En terminales que expanden comodines también puedes utilizar `*.mp4`.

## Qué hace la limpieza

`delogo` reconstruye un rectángulo mediante los píxeles vecinos. Funciona mejor sobre fondos uniformes. Si el logo cubre una ilustración, textura o texto, esa información puede no ser recuperable; una región demasiado grande también borrará contenido válido.

El script está pensado para los MP4 habituales de NotebookLM, con píxeles cuadrados, dimensiones pares y orientación aplicada a la imagen. Rechaza rotación por metadatos y geometrías incompatibles para evitar calcular la región sobre una orientación equivocada. Los nombres con espacios se pasan como argumentos, sin ejecutar su contenido como instrucciones de terminal.

## Validación

Las pruebas generan vídeos sintéticos y ejecutan FFmpeg real. Comprueban los cuatro tamaños de la tabla, perfiles y cierres, audio, número de fotogramas, FPS, previsualización, reducción de variación de píxeles en la región, PNG propio, detección superior, lotes, nombres con caracteres especiales y protección de originales/salidas.

```bash
python3 -m unittest discover -s tests -v
```

No se ha validado con una exportación real aportada por el usuario. La prueba sintética verifica el funcionamiento técnico; el ajuste visual de una exportación concreta se revisa con la previsualización.

Referencias técnicas: [filtro delogo](https://ffmpeg.org/ffmpeg-filters.html#delogo), [ffprobe](https://ffmpeg.org/ffprobe.html), [opciones de FFmpeg](https://ffmpeg.org/ffmpeg.html). El código se escribió de forma independiente a partir del análisis del comportamiento; no necesita ni incluye los paquetes JavaScript de la página.
