# NotebookLM Studio

Aplicación local para procesar vídeos horizontales y Shorts con FFmpeg: carga múltiple, comparación antes/después, recorte del cierre por fotogramas o segundos y previsualización del tramo final con audio.

**Descarga los resultados antes de cerrar.** Los resultados internos, entradas copiadas y previsualizaciones son temporales y se eliminan al confirmar **Eliminar sesión y cerrar**. Las copias descargadas y los originales se conservan. Cerrar solo la pestaña no apaga el servidor. Las sesiones abandonadas de esta versión se intentan limpiar en el próximo inicio.

## Descargar la aplicación

En [Actions](https://github.com/astudilloalex/notebook-lm-watermark-remover/actions/workflows/build.yml), abre una ejecución correcta y descarga el artefacto de tu sistema. Las versiones etiquetadas se publican en [Releases](https://github.com/astudilloalex/notebook-lm-watermark-remover/releases).

| Paquete | Sistema |
| --- | --- |
| Windows-x64 | Windows 10/11 x64 |
| Linux-x64 | Linux x86_64 con glibc 2.28+ y kernel 4.18+ |
| macOS-AppleSilicon | Mac con Apple Silicon, macOS 12+ |
| macOS-Intel | Mac Intel, macOS 12+ |

Extrae el artefacto y luego el paquete de aplicación que contiene. Conserva completa la carpeta y abre **NotebookLM Studio.exe**, **NotebookLM Studio** o **NotebookLM Studio.app**. Python, FFmpeg y ffprobe están incluidos en los paquetes; necesitas un navegador instalado. Los paquetes no tienen certificado comercial de firma ni notarización Apple.

Guía de botones y recorte: [docs/USO.md](docs/USO.md).

## Código fuente

```text
app/                 Motor Python, servidor local e interfaz HTML/CSS/JavaScript
tests/               Pruebas de vídeo, HTTP, descargas, sesiones y limpieza
launchers/           Fuentes C/shell y geometría SVG del icono
scripts/             Construcción, generación de iconos y comprobaciones de CI
.github/workflows/   GitHub Actions para cuatro sistemas/arquitecturas
dependencies.json    Orígenes de Python y FFmpeg y verificación de integridad
VERSION              Versión de la aplicación
docs/                Uso y procesador de consola
```

Git contiene únicamente texto fuente y documentación. Los ejecutables, intérpretes, vídeos, archivos temporales, cachés y paquetes se generan fuera del historial, en `.build/` y `dist/`, y están excluidos mediante `.gitignore`.

La aplicación utiliza la biblioteca estándar de Python, sin paquetes de pip. Para trabajar con las fuentes necesitas Python 3.10+ y FFmpeg/ffprobe con `delogo` y `libx264`:

```sh
python app/interfaz_local.py
python -m unittest discover -s tests -v
```

El procesador por consola se describe en [docs/CLI.md](docs/CLI.md). Sus salidas explícitas se conservan; la política temporal pertenece a la interfaz.

## Construcción automática

Cada push a `main`, pull request o ejecución manual construye los cuatro paquetes en sus sistemas nativos. Cada trabajo:

1. Comprueba que Git solo contiene fuentes.
2. Descarga las dependencias y verifica SHA-256 antes de extraerlas.
3. Compila el lanzador propio y genera los iconos desde código.
4. Empaqueta el código junto con Python, FFmpeg, ffprobe y sus licencias.
5. Ejecuta las pruebas con el FFmpeg que se distribuirá.
6. Abre el paquete sin Python/FFmpeg en `PATH`, procesa un lote, descarga MP4/ZIP y comprueba la eliminación de la sesión.
7. Guarda paquetes, hashes e informe como artefactos durante 30 días.

Los trabajos de construcción solo tienen permiso de lectura. La publicación en Releases requiere una etiqueta `vX.Y.Z` coincidente con `VERSION` y que los cuatro trabajos terminen correctamente. El permiso de escritura se limita a ese trabajo de publicación.

Para construir localmente necesitas Python 3.13+ y el compilador nativo: GCC con bibliotecas estáticas en Linux; Visual Studio Build Tools C++/Windows SDK en Windows. Mac utiliza un lanzador shell. Ejecuta en la arquitectura de destino:

```sh
python scripts/build.py --target linux-x64
python scripts/test.py --target linux-x64
python scripts/smoke.py --target linux-x64
```

Los demás destinos son `windows-x64`, `macos-arm64` y `macos-x64`. No se necesitan las carpetas temporales ni los paquetes producidos en el equipo de desarrollo.

## Dependencias y trazabilidad

Python y FFmpeg de Mac tienen URL y SHA-256 fijados en `dependencies.json`. Para Linux/Windows se consulta el canal oficial de FFmpeg 8.1 de BtbN y se comprueba el SHA-256 del activo declarado por GitHub. Ese canal puede recibir actualizaciones: no se garantiza que dos construcciones en fechas distintas usen el mismo binario de FFmpeg. Cada paquete incluye las URL y hashes exactos resueltos en `Licencias/COMPONENTES.json`, además de la licencia y configuración obtenidas del FFmpeg distribuido.

Las descargas dependen de la disponibilidad de los proveedores. Para actualizar Python o FFmpeg, revisa `dependencies.json` y ejecuta las comprobaciones completas. Los intérpretes y ejecutables de terceros se descargan durante CI; no se compilan Python ni FFmpeg desde sus fuentes en este flujo. Los lanzadores propios sí se compilan desde este repositorio.

La limpieza del logo utiliza interpolación mediante `delogo`; en fondos complejos puede dejar una mancha. Los perfiles automáticos se basan en proporción y FPS. La herramienta es independiente y no está afiliada a Google.
