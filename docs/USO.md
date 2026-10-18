# Usar NotebookLM Studio

Descarga el paquete para tu sistema desde los artefactos de Actions o desde una versión publicada. Descomprime todo y abre NotebookLM Studio, NotebookLM Studio.exe o NotebookLM Studio.app. Python y FFmpeg están incluidos en esos paquetes.

Para ejecutar el código fuente necesitas Python 3.10+ y FFmpeg/ffprobe; ejecuta `python app/interfaz_local.py`.

## 1. Añadir varios vídeos

Pulsa **Añadir vídeos** y selecciona varios archivos a la vez, o arrástralos sobre el recuadro de carga. Puedes mezclar Shorts y vídeos horizontales en la misma selección. Se admiten MP4, MOV, MKV y WebM, siempre que su contenido y geometría sean compatibles con los perfiles del procesador.

Cada vídeo aparecerá como una fila con su nombre, duración, tamaño, formato detectado y estado. Se añaden marcados para procesarlos. La copia de cada archivo muestra su avance.

La interfaz hace una copia temporal en tu propio equipo para que FFmpeg pueda trabajar con ella. Esa copia no modifica el original. Es necesario contar con espacio libre para las entradas temporales y los resultados.

## 2. Revisar cada vídeo

Haz clic en la fila que quieras revisar. El panel de previsualización permite:

- **Antes / después:** comparar un fotograma. A la izquierda aparece el original con un rectángulo rojo; a la derecha, la limpieza calculada. La primera vista del primer vídeo se genera automáticamente.
- **Original:** reproducir el archivo original desde su copia local.
- **Resultado:** reproducir el MP4 terminado cuando esté disponible.

Elige otro instante con **Fotograma en el segundo** y pulsa **Actualizar vista**. Esta operación usa los ajustes del vídeo seleccionado y no genera el MP4 completo.

### Revisar los últimos segundos antes de recortar

Abre la pestaña **Cierre y corte**. Se prepara una vista local del final del vídeo original, con su audio cuando existe. Puedes escoger los últimos **5, 10, 20, 30 o 60 segundos**; si el vídeo dura menos, se muestra completo. No tienes que generar primero el resultado ni procesar el lote. Esta vista conserva el cierre y el logo originales para que puedas decidir el corte.

La barra indica en **verde lo que se conserva** y en **rojo lo que se elimina** con los ajustes actuales. Arrastra el cursor, reproduce el vídeo o usa **−1 fotograma / +1 fotograma** para afinar. El reloj corresponde al instante en el vídeo completo, aunque el reproductor muestre el tiempo de este tramo.

Pulsa **Terminar aquí · incluir este fotograma** para guardar el corte de ese vídeo. Se conserva el fotograma que estás viendo y se eliminan todos los siguientes. En vídeos con total y FPS constantes declarados, el ajuste queda guardado como número de fotogramas originales. **Ir al último fotograma que se conservará** permite revisar el límite configurado. Si el corte queda antes del tramo visible, amplía la vista.

En archivos sin total fiable o con diferencias apreciables entre la cadencia media y nominal, la vista es aproximada y el punto se guarda en segundos. La detección de cadencia variable es heurística. Los modos de calidad Rápida y Equilibrada pueden cambiar los FPS de salida; el corte por fotogramas se calcula siempre sobre la entrada.

Al seleccionar otro vídeo, se abre su propio cierre. El punto elegido se guarda por vídeo y se puede aplicar a una selección con el botón habitual. La vista se genera una vez por tramo solicitado y se reutiliza al cambiar el recorte. Para limitar el consumo solo se prepara el vídeo que estás revisando, con resolución de vista de hasta 1280 × 720; el vídeo final conserva su resolución. Puedes detener su preparación con **Detener**.

Los cambios de formato, calidad, recorte y posición se guardan automáticamente por vídeo. Si cambias un ajuste después de generar una vista, aparecerá un aviso para actualizarla.

## 3. Elegir ajustes

**Formato automático** distingue Shorts por su proporción vertical, Explainer horizontal por una tasa cercana a 24 fps y Cinematic horizontal por una tasa cercana a 30 fps. Puedes seleccionar otro perfil si la detección no coincide con tu exportación.

**Calidad de salida:** Alta conserva la tasa detectada; Equilibrada exporta a 30 fps; Rápida a 15 fps. La resolución se conserva.

**Recortar el cierre de NotebookLM** permite elegir cuánto quitar del final de cada vídeo:

- **Automático según el formato:** 72 fotogramas en Explainer, 90 en Short/Cinematic y 60 en Short antiguo. En región personalizada no recorta automáticamente.
- **Número de fotogramas:** introduce un entero, por ejemplo 30. Se cuenta sobre el vídeo original; 30 fotogramas equivalen a 1,25 segundos a 24 FPS y a 1 segundo a 30 FPS.
- **Duración en segundos:** introduce una duración, incluidos decimales, por ejemplo 1,5 segundos. FFmpeg ajusta el límite a los fotogramas disponibles.

Desactiva el interruptor para conservar todo el cierre; una cantidad de 0 también lo conserva. Debajo aparece el recorte y la duración estimada del resultado. Los cortes personalizados que igualan o superan la duración del vídeo se rechazan. Se recorta únicamente el final y se ajusta también el audio; no hay reconocimiento visual de la pantalla de cierre.

Los ajustes se guardan por vídeo al cambiar de campo o de fila. Para dar el mismo recorte a **todo el lote**, marca **Seleccionar todos**, configura el modo y la cantidad en un vídeo, y pulsa **Aplicar ajustes a los seleccionados**. También puedes marcar solo una parte de la lista. La aplicación comprueba todos los vídeos antes de aplicar el cambio; si alguno es demasiado corto, indica su nombre y conserva los ajustes del conjunto. Cada fila muestra su tipo y cantidad de recorte para poder revisarlos.

En **Ajustes de posición** encontrarás:

- **Buscar el logo superior:** exploración por contraste para horizontales. En una selección mixta con perfil automático, solo se aplica a los vídeos horizontales.
- **Logo a la izquierda:** para exportaciones Explainer que lo necesitan.
- **Región personalizada:** `X:Y:ANCHO:ALTO`, en píxeles de ese vídeo. Se valida que quede dentro de la imagen. Una región absoluta puede no ser válida para resoluciones distintas.

Pulsa **Aplicar ajustes a los seleccionados** para copiar la configuración al conjunto marcado. Se validan todos los destinos antes de aplicar el cambio. Con el formato automático cada vídeo conserva su detección individual.

## 4. Procesar la lista

Marca las filas que quieras y pulsa **Procesar seleccionados**. Los archivos se trabajan **uno detrás de otro** para limitar el consumo de memoria y evitar saturar el procesador con varias conversiones simultáneas.

Verás el estado por archivo y el progreso general. Los vídeos terminados se omiten en la siguiente ejecución, salvo que cambies sus ajustes. Si uno falla, queda señalado para revisar y el lote continúa con los demás.

**Detener** cancela el archivo en curso y deja el resto pendiente. Los resultados terminados siguen disponibles para descargar hasta cerrar la aplicación. Puedes corregir ajustes y volver a procesar los pendientes. Durante una tarea se bloquean los cambios de configuración y la eliminación de filas; puedes seguir consultando otros vídeos.

## 5. Descargar y conservar los resultados

**Todos los archivos generados pertenecen a una sesión temporal. Al cerrar la aplicación se eliminan los MP4, las entradas copiadas, los ZIP de trabajo y las previsualizaciones de esa sesión, aunque no los hayas descargado.**

- La flecha de cada fila descarga ese MP4 mediante tu navegador.
- **Descargar resultados ZIP** descarga los resultados actuales juntos.
- La copia descargada queda donde tengas configurado el navegador, habitualmente en Descargas. Esa copia se conserva al cerrar.

Descargar no mueve el archivo interno: guarda una copia fuera de la sesión. Espera a que finalicen las descargas antes de cerrar. El programa no puede confirmar que el navegador haya terminado de escribirlas solo porque pulses un enlace.

Los resultados usan nombres distintos si coinciden varios vídeos. Al reprocesar un vídeo se sustituye su resultado temporal anterior, una vez que la nueva conversión termina correctamente. Quitar una fila elimina sus archivos internos, incluido su resultado temporal. Descarga antes cualquier versión que quieras conservar.

No existe una carpeta permanente de resultados nuevos. Las carpetas de sesiones activas se mantienen separadas para que una instancia no limpie los datos de otra. Los resultados creados por versiones anteriores en una carpeta persistente no se eliminan automáticamente con esta actualización.

## Cerrar y eliminar la sesión

Pulsa **Cerrar aplicación**, en la esquina superior derecha. El diálogo indica que se perderán los resultados sin descargar y permite descargar un ZIP antes de salir.

**Eliminar sesión y cerrar** detiene la tarea y las transferencias activas, elimina la carpeta de la sesión y solicita apagar el servidor. Solo se conservan los originales y las copias que descargaste fuera de esa carpeta. Si la limpieza no puede completarse, se muestra un error y puedes reintentar; no se confirma una limpieza que haya fallado.

Cerrar únicamente la pestaña o Chrome **no apaga el servidor**. Para liberar la sesión utiliza el botón de la aplicación. Si fuerzas la salida o se corta la energía, los archivos que queden de esta versión se intentan eliminar en el próximo inicio. Se comprueba un bloqueo del sistema para conservar las sesiones que siguen activas; no se borran carpetas ajenas ni Descargas.

La lista y sus ajustes no se restauran al reiniciar. Los archivos temporales sin descargar tampoco se recuperan.

## Funcionamiento local y límites

La aplicación escucha exclusivamente en `127.0.0.1` y abre una sesión privada para esa ejecución. Los vídeos se copian desde tu navegador al procesador del mismo equipo; no se envían a un servicio de Internet. No utiliza la página analizada ni carga recursos externos.

La limpieza utiliza `delogo`. Sobre fondos complejos puede dejar una mancha, por lo que conviene revisar la comparación antes de ejecutar un lote grande. La comprobación automática de formato se basa en proporción/FPS y puede necesitar ajuste en futuras exportaciones de NotebookLM.

Las pruebas de la interfaz se realizaron en Linux con vídeos sintéticos y FFmpeg real. Se verificaron lotes mixtos, previsualización, fotogramas y duración de salida, errores individuales, cancelación del proceso y sus hijos, configuración conjunta, archivos con nombres repetidos, descarga individual y ZIP. Los iniciadores de Windows y macOS se incluyen, pero no se ejecutaron en esos sistemas.
