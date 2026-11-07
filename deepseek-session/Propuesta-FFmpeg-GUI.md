# Propuesta funcional: aplicación de escritorio (Windows) como front‑end de FFmpeg

> Análisis basado en la build incluida en este directorio y en su documentación local
> (`doc/ffmpeg.html`, `doc/ffmpeg-filters.html`, `doc/ffmpeg-formats.html`, `doc/ffmpeg-devices.html`, `doc/ffprobe.html`).
> Todos los comandos de la sección 7 se ejecutaron realmente sobre esta build; los resultados anotados son observados, no supuestos.

---

## 1. Resumen ejecutivo

La aplicación no debe ser "una caja de texto donde escribir comandos de FFmpeg". Debe ser **una capa de intención**: el usuario describe *qué quiere conseguir* ("comprimir este vídeo para WhatsApp", "sacar el audio en MP3", "cortar del minuto 1 al 2") y la app construye, valida y ejecuta el comando.

Eso se apoya en tres piezas técnicas:

| Pieza | Herramienta | Papel |
|---|---|---|
| **Inspección** | `ffprobe -of json` | Saber qué hay dentro del archivo antes de decidir nada |
| **Ejecución** | `ffmpeg` como proceso hijo con `-progress` | Trabajo real + progreso fiable y cancelable |
| **Plantillas** | Presets declarativos (JSON) | Convertir decisiones técnicas en opciones de usuario |

**Recomendación de alcance:** 8 funciones cubren el 80 % del uso real de un usuario doméstico/prosumer; otras 7 son el salto a "herramienta seria"; el resto son extras diferenciadores.

---

## 2. Base técnica detectada (y lo que condiciona el diseño)

```
ffmpeg version N-128532-g5d85b7bfb2-20261106  (rama 9.0)
libavcodec 63.26.101 · libavformat 63.18.100 · libavfilter 12.12.100 · libavutil 61.20.100
Windows x86_64 · build estática · GPLv3 (--enable-gpl --enable-version3)
```

**Aceleración por hardware compilada:** `cuda`, `d3d11va`, `d3d12va`, `dxva2`, `qsv`, `amf`, `vaapi`, `vulkan`, `opencl`.
En la máquina de pruebas, **NVENC funcionó** (`h264_nvenc`) y **QSV/AMF no están disponibles** (no hay GPU Intel/AMD). Conclusión de diseño: *la detección de hardware debe ser en tiempo de ejecución, nunca asumida*.

**Codificadores relevantes presentes:** `libx264`, `libx265`, `libsvtav1`, `libaom-av1`, `librav1e`, `libvpx-vp9`, `libvvenc` (VVC), `prores_ks`, `dnxhd`, `ffv1`, `libjxl`, `libwebp`, `h264_nvenc`/`hevc_nvenc`/`av1_nvenc`, `h264_qsv`/`hevc_qsv`/`av1_qsv`, `h264_amf`/`hevc_amf`/`av1_amf`, `aac`, `libmp3lame`, `libopus`, `libvorbis`, `flac`, `alac`, `ac3`/`eac3`, `pcm_*`, y subtítulos `mov_text`, `srt`, `ass`, `webvtt`.

**Filtros clave disponibles:** `scale`, `crop`, `pad`, `fps`, `yadif`/`bwdif`, `subtitles`/`ass`, `drawtext`, `loudnorm`/`ebur128`, `volume`/`afade`/`atempo`, `concat`, `overlay`/`xfade`, `palettegen`/`paletteuse`, `thumbnail`/`tile`, `vidstabdetect`/`vidstabtransform`, `deshake`, `unsharp`, `eq`, `tonemap`/`zscale`/`colorspace`, `libplacebo`, `libvmaf`/`xpsnr`, `blackdetect`/`silencedetect`/`freezedetect`, `signalstats`.

**Dos avisos que afectan al producto:**

1. **Licencia.** Es una build **GPLv3** con `libx264`/`libx265`. Si la app se distribuye *empaquetando* este binario, hay obligaciones GPL que conviene revisar con legal. Alternativas: publicación GPL del conjunto, o descargar FFmpeg aparte en la primera ejecución.
2. **`-hwaccel_output_format` ya no aparece** en la documentación de esta versión (sí `-hwaccel`, `-hwaccel_device`, `-hwaccels`). No diseñes la interfaz alrededor de ese modificador: el camino sin copias se documenta hoy vía `-hwaccel qsv` y codificadores `*_nvenc`/`*_qsv`.

---

## 3. Las cinco reglas de FFmpeg que la interfaz debe esconder

Estas reglas explican el 90 % de los comandos "que no funcionan" que reportarán los usuarios.

1. **Las opciones pertenecen al siguiente archivo, y el orden importa.** `-ss` antes de `-i` busca rápido; después de `-i` decodifica y descarta. Por eso el modelo de datos interno debe ser `{ entradas[], salidas[] }`, no una lista plana de argumentos.
2. **`-c copy` no recodifica.** Es rapidísimo y sin pérdida, pero **no admite filtros** y **no corta donde quieres**: corta en el fotograma clave anterior. En la prueba, pedir 1 s dio **1,067 s**.
3. **Cada salida elige sus pistas con `-map`.** Si no se usa `-map`, FFmpeg elige automáticamente (mayor resolución, más canales). Un usuario que "no le sale el audio" casi siempre necesita `-map 0:a:0`.
4. **Los filtros son cadenas**, y los "complejos" permiten varias entradas/salidas (`-filter_complex`). Unir, superponer o quemar subtítulos exige grafo complejo.
5. **Si una salida es inválida, falla todo.** FFmpeg no "hace lo que puede": valida antes de arrancar. La app debe validar antes de lanzar.

---

## 4. Catálogo priorizado de funciones

### Nivel 1 — Núcleo (el 80 % del uso)

| # | Función | Problema que resuelve | Primitiva FFmpeg | Esfuerzo |
|---|---|---|---|---|
| F1 | **Inspector de medios** | "¿Qué es este archivo?" | `ffprobe -of json -show_format -show_streams` | Bajo |
| F2 | **Convertir formato/códec** | MKV→MP4, MOV→MP4, AVI→MP4… | `-c:v/-c:a` + preset | Bajo |
| F3 | **Comprimir para compartir** | "Pesa demasiado para enviarlo" | `scale` + CRF + `-movflags +faststart` | Medio |
| F4 | **Recortar** | "Quiero solo este trozo" | `-ss` + `-t` (copiar o preciso) | Medio |
| F5 | **Extraer / convertir audio** | MP3, M4A, WAV, Opus | `-vn -c:a …` | Bajo |
| F6 | **Unir clips** | "Juntar grabaciones" | concat demuxer o filtro `concat` | Medio |
| F7 | **GIF / WebP animado** | Compartir en chat/foro | `palettegen` + `paletteuse` | Bajo |
| F8 | **Miniatura / póster** | Portada, preview, catálogo | `-frames:v 1 -update 1` | Bajo |

### Nivel 2 — Herramienta "seria"

| # | Función | Primitiva FFmpeg | Esfuerzo |
|---|---|---|---|
| F9 | **Subtítulos**: quemar, incrustar (`mov_text`), extraer, elegir pista | `subtitles=`, `-c:s`, `-map 0:s` | Alto |
| F10 | **Normalizar audio** (EBU R128) | `loudnorm` (1 o 2 pasadas) | Medio |
| F11 | **Secuencias**: vídeo→fotogramas y fotogramas→vídeo | `image2`, `-framerate`, `fps=` | Bajo |
| F12 | **Metadatos, capítulos y carátula** | `-metadata`, `-map_chapters`, `-attach`/`disposition` | Medio |
| F13 | **Cambiar contenedor / fps / velocidad** | `-c copy`, `fps_mode`, `setpts`+`atempo` | Medio |
| F14 | **Encuadre**: recortar imagen, rotar, voltear, rellenar | `crop`, `transpose`, `rotate`, `pad` | Bajo |
| F15 | **Cola por lotes con perfiles** (transversal) | motor de trabajos | Medio |

### Nivel 3 — Diferenciación

| # | Función | Primitiva FFmpeg |
|---|---|---|
| F16 | HDR→SDR con tonemapping correcto | `zscale`/`tonemap` o `libplacebo` |
| F17 | Estabilizar y limpiar ruido | `vidstabdetect`+`vidstabtransform`, `afftdn`, `arnndn` |
| F18 | Hoja de contactos / storyboard | `thumbnail`+`tile` |
| F19 | Grabar pantalla o webcam | `gdigrab`, `dshow` |
| F20 | Medir calidad objetiva | `libvmaf`, `xpsnr` |
| F21 | Editor visual de grafo de filtros | `-filter_complex` |

### Lo que **no** debería estar en el MVP

- Editor de filtros visual (atractivo, pero es un producto aparte).
- Streaming (RTMP/SRT): otro modelo mental, otra gestión de errores.
- Reproducción integrada con previsualización en tiempo real: `ffplay` existe, pero sincronizar *scrub* con el corte es el problema más caro de todo el proyecto. Empieza con **miniaturas del fotograma en el punto de corte**, que resuelve el 90 % de la necesidad por el 5 % del coste.

---

## 5. Fichas de las funciones principales

### F1 · Inspector de medios
**Interfaz:** al arrastrar un archivo, tarjeta con duración, resolución, fps, códecs, bitrate, pistas (con idioma y título), subtítulos, capítulos y tamaño. Es también el *gate* de validación de todo lo demás.

```bash
ffprobe -v error -print_format json -show_format -show_streams "in.mp4"
```

Devuelve `format.duration`, `format.bit_rate`, `streams[].codec_type/codec_name/width/height/r_frame_rate/channels/language/disposition`. Úsalo para: calcular el porcentaje de progreso, decidir si `-c copy` es viable, y poblar los desplegables de pistas.

**Extra útil:** `-show_chapters` para capítulos, `-show_frames` (con `-read_intervals`) solo si necesitas keyframes para el scrubbing.

---

### F2 · Convertir formato/códec
**Interfaz:** "Formato de salida" (MP4, MKV, MOV, WebM, AVI, MP3, WAV…) y, en avanzado, códec de vídeo/audio. La app debe **filtrar los contenedores compatibles** con el códec elegido (ver tabla §6.3).

```bash
ffmpeg -y -i in.mkv -c:v libx264 -preset medium -crf 21 -pix_fmt yuv420p \
       -c:a aac -b:a 160k -movflags +faststart out.mp4
```

**Regla de producto:** si el usuario solo cambia de contenedor y los códecs son compatibles, ofrece **"sin recodificar (rápido, sin pérdida)"** y usa `-c copy`. Es la función más valorada y la más barata de implementar. En la prueba, MP4→MKV con `-c copy` fue instantáneo.

---

### F3 · Comprimir para compartir
**Interfaz:** un *slider* de "Calidad" (Alta / Buena / Compacta) que traduzca a CRF, más "resolución máxima" (2160/1440/1080/720/480) y un tamaño estimado.

```bash
ffmpeg -y -i in.mp4 -vf "scale='min(1920,iw)':-2" \
       -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
       -c:a aac -b:a 128k -movflags +faststart out.mp4
```

- `scale='min(1920,iw)':-2` **no amplía** si el original es menor, y `-2` mantiene el alto par (obligatorio para H.264 4:2:0).
- CRF no permite predecir el tamaño. Para estimarlo: o codificas 10 s de muestra y extrapolas, o usas modo bitrate (`-b:v 2M`) con dos pasadas.
- Ofrece "solo si es más pequeño": tras terminar, compara tamaños y avisa si el resultado pesa más.

---

### F4 · Recortar (la función con más matices)
**Interfaz:** línea de tiempo con dos tiradores, campos `mm:ss.mmm`, y un conmutador **"Corte rápido"** vs **"Corte exacto"**.

| Modo | Comando | Resultado real |
|---|---|---|
| Rápido (`-c copy`) | `ffmpeg -ss 1 -i in.mp4 -t 1 -c copy out.mp4` | **1,067 s** — empieza en el keyframe anterior |
| Exacto (recodifica) | `ffmpeg -i in.mp4 -ss 1.2 -t 1 -c:v libx264 -crf 20 -c:a aac out.mp4` | **1,000 s** clavados |

**Decisión de diseño:** por defecto, exacto; ofrecer rápido solo cuando el usuario marque "sin recodificar", y **avisar** de que el corte puede desplazarse hasta el keyframe anterior. Muestra la duración resultante calculada antes de ejecutar.

**Casos límite a cubrir:** `-ss` mayor que la duración; `-t` que excede el final (FFmpeg corta sin error); origen sin keyframes; audio con retardo inicial (`-avoid_negative_ts make_zero` si aparecen desajustes).

---

### F5 · Extraer / convertir audio
```bash
ffmpeg -y -i in.mp4 -vn -c:a libmp3lame -q:a 2 out.mp3          # VBR ~190 kbps
ffmpeg -y -i in.mp4 -vn -c:a aac -b:a 192k out.m4a
ffmpeg -y -i in.mp4 -vn -c:a libopus -b:a 96k out.opus
ffmpeg -y -i in.mp4 -vn -c:a copy out.ac3                        # sin recodificar
```

**Interfaz:** selector de pista (si hay varias), formato, calidad (buena/estándar/compacta) y "conservar original" cuando el códec ya coincide con el contenedor. Añade "quitar audio" (`-an`) como acción hermana: es la misma pantalla con otra salida.

---

### F6 · Unir clips
Dos caminos, y la app debe elegir por el usuario:

| Situación | Técnica | Comando |
|---|---|---|
| Mismos códecs, resolución y fps | **concat demuxer** (instantáneo) | `-f concat -safe 0 -i list.txt -c copy out.mp4` |
| Distintos códecs/resolución/fps | **filtro concat** (recodifica) | `-filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]" -map "[v]" -map "[a]"` |

**Verificado:** con dos clips MP4 idénticos, el demuxer produjo 4,09 s (3,00 + 1,07) sin recodificar.

**Trampa:** `-safe 0` es necesario con rutas absolutas; el archivo de lista usa `file 'ruta'` con **comillas simples** y barras normales. La app debe escribirlo en UTF‑8 y escapar las comillas simples del nombre.

---

### F7 · GIF / WebP animado
La calidad de un GIF depende casi por completo de la paleta. Un solo `-vf gif` produce bandas y colores sucios; la receta de dos etapas en un único grafo es la correcta:

```bash
ffmpeg -y -i in.mp4 -vf "fps=12,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" out.gif
```

**Interfaz:** fps (10/12/15/24), ancho (320/480/640), y aviso de peso ("un GIF de 10 s a 480 px ronda 3–8 MB"). Para WebP animado: `-c:v libwebp_anim -loop 0 -q:v 75`.

---

### F8 · Miniatura / póster
```bash
ffmpeg -y -ss 2 -i in.mp4 -frames:v 1 -update 1 -vf "scale=320:-1" thumb.jpg
```

`-update 1` es imprescindible: sin él, el muxer `image2` espera un patrón de nombres y falla o genera `thumb1.jpg`. **Mejora de producto:** botón "elegir fotograma" que muestra 6 miniaturas (`-vf thumbnail` o muestreo cada N segundos) y deja escoger.

---

### F9 · Subtítulos (la función más delicada)
Cuatro acciones distintas que el usuario percibe como una:

| Acción | Comando |
|---|---|
| Quemar (hardcode) | `-vf "subtitles=filename='RUTA':force_style='FontName=Arial,FontSize=24'"` |
| Incrustar en MP4 | `-c:s mov_text -map 0:s:0` |
| Convertir SRT↔ASS↔VTT | `-c:s srt` / `ass` / `webvtt` |
| Extraer a archivo | `ffmpeg -i in.mkv -map 0:s:0 out.srt` |

**Hallazgo verificado:** el filtro `subtitles` resuelve rutas relativas contra el **directorio de trabajo del proceso**, no contra el del vídeo. Un `subtitles=subs.srt` falla con `Unable to open subs.srt` aunque el archivo esté junto al vídeo. La forma que funciona:

```bash
-vf "subtitles=filename='D\:/ruta/completa/subs.srt'"
```

Es decir: ruta **absoluta**, barras normales, `:` escapado con `\` y todo el valor **entre comillas simples**. Sin las comillas, FFmpeg parte el valor en el `:` e intenta interpretar `/ruta/...` como `original_size` (`Unable to parse "original_size"`). Verificado con nombres de vídeo con espacios y acentos.

**Avisos de interfaz:** `mov_text` **no conserva estilos ASS** (posición, colores, karaoke se pierden); quemar es irreversible; y el tamaño de fuente debe escalar con la resolución para que no quede diminuto en 4K.

---

### F10 · Normalizar audio (EBU R128)
Para que todos los vídeos suenen al mismo volumen (el problema real de "este vídeo suena bajísimo").

```bash
ffmpeg -y -i in.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:v copy out.mp4
```

Una pasada basta para consumo doméstico. La **dos pasadas** (medir con `print_format=json`, luego aplicar `measured_*`) da resultados más precisos y lineales, pero duplica el tiempo y complica la UI. Recomendación: una pasada por defecto, dos pasadas como opción "máxima precisión".

**Verificado:** la variante de una pasada con `print_format=json` emite el bloque JSON de medición por *stderr*, mezclado con el log. Si lo necesitas, filtra las líneas entre la primera `{` y la última `}`.

Compañeros de pantalla: "subir/bajar volumen" (`volume=1.5`), "fundido" (`afade`), "quitar silencios" (`silenceremove`) — este último es de nivel 3 por sus efectos secundarios.

---

### F11 · Secuencias de fotogramas
```bash
ffmpeg -i in.mp4 -vf fps=1 frames/img%03d.png        # vídeo → imágenes
ffmpeg -framerate 1 -i frames/img%03d.png -c:v libx264 -pix_fmt yuv420p -r 25 out.mp4  # imágenes → vídeo
```

**Verificado:** 3 imágenes generadas y reconstruidas en un MP4 de 3,00 s. `-framerate` (entrada) fija la cadencia de la secuencia; `-r` (salida) la del archivo final. Confundirlos es el error clásico: un timelapse "a cámara rápida" suele ser un `-framerate` mal puesto.

---

### F12 · Metadatos, capítulos y carátula
```bash
ffmpeg -y -i in.mp4 -c copy -metadata title="Mi vídeo" -metadata:s:a:0 language=spa out.mp4
ffmpeg -y -i in.mp4 -i cover.jpg -map 0 -map 1 -c copy -disposition:v:1 attached_pic out.mp4
```

**Interfaz:** formulario (título, artista, álbum, comentario, fecha, idioma por pista) + "pista por defecto" (`-disposition default`). Los capítulos se editan en una tabla y se exportan como `metadata.txt` para `-map_chapters`. Es una función de "pulido" que fideliza: pocas apps gratuitas lo hacen bien.

---

## 6. Arquitectura recomendada

### 6.1 Flujo

```
[UI] ──arrastra──▶ Inspector (ffprobe JSON) ──▶ Job (modelo) ──▶ CommandBuilder ──▶ ProcessRunner ──▶ ffmpeg
                                                                       │                    │
                                                                       ▼                    ▼
                                                                  Vista previa        -progress → barra
                                                                  del comando         stderr → log/errores
```

### 6.2 Reglas de implementación

- **Nunca construyas una cadena de comando.** Usa un array de argumentos y el API de proceso del lenguaje (`ProcessStartInfo.ArgumentList`, `Command::args`, `spawn(file, args)`). En Windows, no pases por `cmd.exe`: evitas el infierno de comillas y los caracteres `&`, `^`, `%`.
- **Escapa solo donde FFmpeg lo exige:** dentro de valores de filtro (`:` → `\:`, `\` → `\\`, `'` → `\'`) y en el archivo de lista del concat. Las rutas normales (`-i`, salida) van como argumento literal.
- **Progreso:** `-progress pipe:1 -nostats -loglevel error`. Lee **stdout y stderr en paralelo** (si no drenas stderr, el proceso se bloquea cuando el buffer se llena — el bug clásico de los front-ends de FFmpeg).
- **Porcentaje:** `out_time_us / duracion_us` (la duración viene de ffprobe). **ETA:** `restante / speed`, donde `speed=27.6x` es el valor que FFmpeg ya reporta.
- **Cancelar:** escribe `q` en la entrada estándar: FFmpeg cierra el MP4 correctamente. Si no responde en ~5 s, mata el proceso y **borra la salida parcial**.
- **Salida atómica:** escribe en `salida.mp4.part` y renombra al terminar. Evita archivos corruptos y permite reintentar sin sobrescribir.
- **Nunca sobrescribas la entrada.** Compara rutas resueltas, no cadenas.
- **Colisión de nombres:** `(1)`, `(2)`, o mejor `nombre_2026-11-07_1430.mp4`.
- **Concurrencia:** 1 trabajo pesado a la vez (FFmpeg ya usa todos los núcleos). Cola secuencial con posibilidad de pausar.
- **Espacio en disco:** estima antes (`duración × bitrate / 8`) y avisa si queda menos del doble.

### 6.3 Matriz contenedor ↔ códec (para validar antes de ejecutar)

| Contenedor | Vídeo admitido | Audio admitido | Subtítulos |
|---|---|---|---|
| MP4 | H.264, HEVC, AV1 | AAC, MP3, AC3, E-AC3, Opus (limitado) | `mov_text` |
| MKV | prácticamente todo | prácticamente todo | SRT, ASS, PGS, VTT |
| WebM | VP8, VP9, AV1 | Vorbis, Opus | WebVTT |
| MOV | H.264, HEVC, ProRes | AAC, PCM, ALAC | `mov_text` |
| AVI | MPEG‑4, H.264, DV | MP3, PCM | — |
| MP3 / WAV / FLAC | — | MP3 / PCM / FLAC | — |
| GIF | GIF | — | — |

Esta tabla, en código, es la que impide que el usuario configure "AV1 en AVI" y reciba un error críptico.

### 6.4 Modelo de datos sugerido (JSON)

```json
{
  "id": "job_01H...",
  "inputs": [{ "path": "D:/video.mkv", "seek": "00:01:00.000", "duration": "00:00:30.000" }],
  "output": {
    "path": "D:/salida.mp4",
    "container": "mp4",
    "video": { "codec": "libx264", "crf": 21, "preset": "medium", "scale": "1920:-2", "fps": null },
    "audio": { "codec": "aac", "bitrate": "160k", "channels": 2 },
    "subtitles": { "mode": "copy", "stream": 0 },
    "filters": [],
    "map": ["0:v:0", "0:a:0"]
  },
  "options": { "overwrite": false, "faststart": true, "twoPass": false, "hwaccel": "auto" }
}
```

Ventaja: la vista previa del comando, el guardado de presets y la cola salen gratis del mismo objeto.

### 6.5 Detección de hardware al arrancar
1. `ffmpeg -hide_banner -encoders` → lista de codificadores disponibles.
2. Para cada familia candidata (`h264_nvenc`, `h264_qsv`, `h264_amf`), codificar **1 fotograma** de `testsrc` a `NUL`, con timeout de 3 s.
3. Guardar el resultado por máquina y ofrecer "Automático" / "CPU" / "GPU" en los ajustes.

En la prueba, `h264_nvenc` funcionó a la primera y `h264_qsv`/`h264_amf` fallaron con `-1313558101` (dispositivo no disponible). Sin este *probe*, la app habría mostrado "GPU" a un usuario sin GPU.

### 6.6 Mapa de errores (los que verás de verdad)

| Código / mensaje | Significado | Acción en la UI |
|---|---|---|
| `-2` / `No such file or directory` | Ruta inexistente (típico: dentro de un filtro) | Revisar rutas absolutas; nunca usar relativas en filtros |
| `-5` / `I/O error` | Disco lleno, ruta sin permisos, log de two-pass ausente | Comprobar espacio y carpeta |
| `-22` / `Invalid argument` | Filtro o parámetro mal formado | Mostrar el fragmento del filtro |
| `-1313558101` | Hardware no disponible | Reintentar en CPU automáticamente |
| `moov atom not found` | Archivo incompleto/corrupto | Avisar antes de gastar tiempo |
| `Output file #0 does not contain any stream` | `-map` incorrecto | Validar contra las pistas reales |
| `Conversion failed!` | Error genérico al final del log | Enseñar las últimas 15 líneas + botón "copiar log" |

**Detalle:** en Windows los códigos negativos son `AVERROR` (errno de FFmpeg). No los compares con `1`; normalízalos.

---

## 7. Comandos verificados en esta build

Todo lo siguiente se ejecutó realmente; "OK" = salida válida comprobada con ffprobe.

| # | Prueba | Comando (resumido) | Resultado |
|---|---|---|---|
| 1 | Transcoder base | `-c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -movflags +faststart` | OK · 3,000 s |
| 2 | Recorte rápido | `-ss 1 -i in -t 1 -c copy` | OK · **1,067 s** (keyframe) |
| 3 | Recorte exacto | `-i in -ss 1.2 -t 1 -c:v libx264 -crf 20` | OK · **1,000 s** |
| 4 | GIF con paleta | `-vf fps=12,scale=480:-1,split…palettegen…paletteuse` | OK |
| 5 | Miniatura | `-ss 2 -frames:v 1 -update 1 -vf scale=320:-1` | OK |
| 6 | Concatenar | `-f concat -safe 0 -i list.txt -c copy` | OK · 4,088 s |
| 7 | Loudness 1 pasada | `-af loudnorm=I=-16:TP=-1.5:LRA=11` | OK |
| 8 | Extraer audio | `-vn -c:a libmp3lame -q:a 2` | OK |
| 9 | Remux | `-c copy` MP4→MKV | OK · instantáneo |
| 10 | NVENC | `-c:v h264_nvenc -preset p4 -cq 23` | OK |
| 11 | QSV / AMF | `-c:v h264_qsv` / `h264_amf` | **Fallo** `-1313558101` (sin hardware) |
| 12 | Progreso | `-progress prog.txt -nostats` | OK · claves `frame/fps/out_time_us/speed/progress` |
| 13 | ffprobe JSON | `-of json -show_format -show_streams` | OK |
| 14 | Quemar subtítulos | `-vf "subtitles=filename='D\:/…/subs.srt'"` | OK (con comillas y ruta absoluta) |
| 15 | Subtítulos, ruta relativa | `-vf "subtitles=subs.srt"` | **Fallo** `Unable to open subs.srt` |
| 16 | Velocidad 2× | `setpts=0.5*PTS` + `atempo=2.0` | OK · 1,567 s |
| 17 | Velocidad 0,5× | `setpts=2.0*PTS` + `atempo=0.5` | OK · 5,986 s |
| 18 | Two‑pass (audio solo en pasada 2) | `-pass 1 -an` … `-pass 2` | **Fallo** `-5`, busca `x264pass-1.log` |
| 19 | Two‑pass (mismas pistas) | `-pass 1 -c:a aac` … `-pass 2 -c:a aac` | OK |
| 20 | Añadir pista de audio | `-map 0:v:0 -map 1:a:0 -shortest -c:v copy` | OK |
| 21 | Vídeo → frames | `-vf fps=1 frames/img%03d.png` | OK · 3 archivos |
| 22 | Frames → vídeo | `-framerate 1 -i img%03d.png -r 25` | OK · 3,000 s |

**Lección de la prueba 18:** las dos pasadas deben tener **exactamente el mismo número y tipo de pistas**. FFmpeg asigna un archivo de estadísticas por pista y, si en la pasada 2 aparece una que no existía en la 1, aborta. La app debe forzar esta simetría al construir el comando.

---

## 8. Trampas que la interfaz debe absorber

1. **Rutas en filtros** (subtítulos, `drawtext`, `movie=`): absolutas, comillas simples, `:` escapado. Es el fallo más frecuente y el más opaco.
2. **`-c copy` + filtros = error**. Si el usuario activa un filtro, la app debe cambiar automáticamente a recodificar y decírselo.
3. **Cortes que no cuadran** por keyframes (tabla de F4). Muestra la duración resultante *antes* de ejecutar.
4. **`-update 1`** al escribir una sola imagen; sin él, nombres inesperados.
5. **Subpistas ocultas:** si no hay `-map`, FFmpeg elige una pista de audio y descarta las demás. La UI debe mostrar todas y permitir marcar "todas".
6. **Nombres con espacios, acentos, `#`, `%`, `[]`:** funcionan como argumentos, pero rompen filtros y archivos de lista. Prueba con `clip con espacios y ñ.mp4` desde el primer día.
7. **Rutas largas (>260 caracteres)** en Windows: usa `\\?\` o rutas relativas al directorio temporal.
8. **Antivirus/OneDrive:** pueden bloquear la escritura del `.part`. Reintenta en `%TEMP%` si falla el renombrado.
9. **Logs en UTF‑16:** si implementas en PowerShell, la redirección nativa escribe UTF‑16 y rompe el parseo. En la app, captura bytes y decodifica como UTF‑8 (FFmpeg emite UTF‑8).
10. **`progress=end` no significa éxito:** comprueba siempre el código de salida.

---

## 9. Experiencia de uso recomendada

**Una sola ventana, tres zonas:** lista de archivos (izquierda), ajustes de la tarea (centro), cola y progreso (abajo).

- **Modo simple / avanzado.** Simple: 3 decisiones (formato, calidad, resolución). Avanzado: códecs, bitrate, filtros, mapa de pistas.
- **"Ver comando" siempre visible** (plegable) y botón "copiar". Los usuarios avanzados confían en una app que no les oculta nada; además sirve de soporte técnico.
- **Presets con nombre de resultado**, no de parámetro: "Para WhatsApp (3 min, < 16 MB)" en lugar de "H.264 CRF 26 720p".
- **Estimación antes de ejecutar:** peso aproximado, duración resultante, y "va a recodificar / no va a recodificar".
- **Nada de jerga en la superficie:** "Calidad" con tres posiciones y una nota ("más calidad = más peso").
- **Al terminar:** notificación del sistema, "abrir carpeta", "reproducir", "comparar tamaños".
- **Errores en lenguaje humano** con el detalle técnico detrás de "ver detalles".
- **Recordar la última configuración** por tipo de tarea.

---

## 10. Stack y plan

| Opción | Ventaja | Coste | Cuándo |
|---|---|---|---|
| **Tauri 2** (Rust + web) | 5–15 MB, control de procesos excelente, multiplataforma gratis | Curva de Rust | Recomendado si el equipo sabe JS/TS |
| **Electron** | Ecosistema y velocidad de desarrollo | 100 MB+, consumo alto | Equipo 100 % JS, prioridad a tiempo de entrega |
| **.NET 8 + WinUI 3 / WPF** | Integración nativa Windows, `ProcessStartInfo.ArgumentList` limpio | Solo Windows | Equipo .NET, app "de sistema" |

**Recomendación:** para una app Windows‑first con mucho trabajo de proceso y progreso, **WinUI 3 (.NET)** o **Tauri**. Electron solo si el equipo ya es JS y la prioridad es velocidad.

**Plan en tres fases:**

| Fase | Contenido | Duración estimada |
|---|---|---|
| MVP | F1–F5 + F8 + cola con progreso/cancelación + presets básicos | 4–6 semanas |
| v1.0 | F6, F7, F9, F11, F13, F14 + detección de hardware + metadatos | +4–5 semanas |
| v1.5 | F10, F12, F15, F18 + perfiles por lotes + "ver comando" avanzado | +3–4 semanas |
| v2 | F16, F17, F19, F20, editor de filtros | a demanda |

**Riesgos principales:** subtítulos (F9) y unión con clips heterogéneos (F6) son las dos funciones que más tiempo consumen; ambas parecen triviales desde fuera. Presupuéstales el doble.

---

## 11. Anexo: por dónde seguir leyendo (documentación local)

| Necesitas | Archivo | Sección |
|---|---|---|
| Modelo general, opciones, `-map`, `-progress` | [`doc/ffmpeg.html`](ffmpeg-master-latest-win64-gpl/doc/ffmpeg.html) | §3 (Streamcopy/Transcoding), §4 (Stream selection), §5.4 (Main options) |
| `-ss`, `-to`, `-t`, `-metadata`, `-disposition` | mismo | §5.4 |
| `-fps_mode`, `-shortest`, `-filter_complex` | mismo | §5.5–5.11 |
| Catálogo de filtros (`scale`, `loudnorm`, `subtitles`, `concat`…) | [`doc/ffmpeg-filters.html`](ffmpeg-master-latest-win64-gpl/doc/ffmpeg-filters.html) | por nombre de filtro |
| `movflags +faststart`, concat demuxer, `image2`, `-update` | [`doc/ffmpeg-formats.html`](ffmpeg-master-latest-win64-gpl/doc/ffmpeg-formats.html) | muxers MP4, concat, image2 |
| `gdigrab`, `dshow` | [`doc/ffmpeg-devices.html`](ffmpeg-master-latest-win64-gpl/doc/ffmpeg-devices.html) | §3.5, §3.7 |
| Inspección JSON (`-show_streams`, `-show_chapters`, `-of`) | [`doc/ffprobe.html`](ffmpeg-master-latest-win64-gpl/doc/ffprobe.html) | §5 |
| Sintaxis de duraciones (`00:01:30.5`, `90s`) | [`doc/ffmpeg-utils.html`](ffmpeg-master-latest-win64-gpl/doc/ffmpeg-utils.html) | Time duration |

---

*Documento generado a partir del análisis de la build `N-128532` y de 22 pruebas de ejecución reales. Los presets listos para usar están en `presets-ffmpeg-gui.json`.*
