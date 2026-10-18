# Command-line processor

The installed application uses buttons; this guide is for source development and automation. Existing Spanish CLI option names and values are retained for compatibility. All examples below run from the `app/` directory.

The processor uses Python 3.10+ and native FFmpeg/ffprobe with `delogo` and `libx264`. It does not load an external remover website or download a model. There are no pip dependencies.

## Basic usage

```sh
python notebooklm_ffmpeg.py "video.mp4"
python notebooklm_ffmpeg.py "video.mp4" --ffmpeg "/path/to/ffmpeg" --ffprobe "/path/to/ffprobe"
```

The default output is `video_limpio.mp4` beside the input. Video is re-encoded as H.264, normally at detected FPS, CRF 18 and preset `medium`; audio is AAC at 192 kbit/s. This is not lossless reconstruction.

Originals are protected. Existing outputs require `--sobrescribir`; a failed conversion removes its temporary output. CLI outputs are persistent, unlike browser-interface sessions.

## Profiles and end trimming

| `--perfil` | Automatic detection | Default end trim |
| --- | --- | --- |
| `explainer` | Approximately 16:9 and 24 FPS | 72 frames |
| `cinematic` | Approximately 16:9 and 30 FPS | 90 frames |
| `short` | Approximately 9:16 | 90 frames |
| `legacy` | Manual legacy Short selection | 60 frames |
| `manual` | Requires an explicit region | None |

The default `auto` profile selects by aspect ratio and FPS. The horizontal tolerance is 0.1 FPS, including 23.976 and 29.97. Profiles scale coordinates for supported resolutions; they do not identify an actual NotebookLM export or recognize its closing screen.

```sh
python notebooklm_ffmpeg.py "horizontal.mp4" --perfil cinematic
python notebooklm_ffmpeg.py "vertical.mp4" --perfil short
python notebooklm_ffmpeg.py "video.mp4" --sin-recorte
python notebooklm_ffmpeg.py "video.mp4" --recortar-fotogramas 60
python notebooklm_ffmpeg.py "video.mp4" --recortar-segundos 2.5
```

The three explicit trim choices are mutually exclusive. Frame trimming uses the declared total or counts frames with ffprobe. Inputs shorter than the trim are rejected. For variable-frame-rate sources, use seconds or disable trimming: materially different nominal/average FPS cause automatic frame trimming to be rejected. This detection is heuristic, and output cadence is normalized.

## Preview and inspect

```sh
python notebooklm_ffmpeg.py "video.mp4" --previsualizar "preview.png" --segundo 1
python notebooklm_ffmpeg.py "video.mp4" --duracion-prueba 5 -o "sample.mp4"
python notebooklm_ffmpeg.py "video.mp4" --simular
```

The PNG shows the original/marked region on the left and the processed frame on the right. It does not trim or generate the complete output. For short inputs choose a timestamp within the input duration.

The sample starts at the beginning and respects the configured ending trim. Simulation prints the plan and an equivalent FFmpeg command. Simulation may still read the full input to count frames or perform contrast detection.

## Custom regions

`--rect X:Y:WIDTH:HEIGHT` uses original pixels with the origin at the upper-left corner. Leave at least one outer pixel on every side for interpolation.

```sh
python notebooklm_ffmpeg.py "video.mp4" --rect 1141:686:134:24 --previsualizar "region.png"
python notebooklm_ffmpeg.py "other.mp4" --perfil manual --rect 1141:686:134:24
```

The manual profile preserves the ending unless an explicit trim is supplied. To keep an Explainer's default trim while correcting the region, use `--perfil explainer --rect ...`.

| Geometry | Typical X:Y:WIDTH:HEIGHT |
| --- | --- |
| Horizontal 1280 × 720 | `1141:686:134:24` |
| Horizontal 1920 × 1080 | `1712:1029:203:36` |
| Short 406 × 720 | `291:688:109:27` |
| Short 720 × 1280 | `516:1223:193:48` |

`--rtl` selects a left-side logo for Explainer and contrast detection. Cinematic retains its lower-right profile; use a custom rectangle for another location.

## Optional contrast detection

```sh
python notebooklm_ffmpeg.py "horizontal.mp4" --deteccion-inteligente
python notebooklm_ffmpeg.py "horizontal.mp4" --deteccion-inteligente --umbral 600
```

One frame per second is sampled. RGB brightness variation is measured in predefined bottom and upper-center windows and grouped into intervals; the default threshold is 400. Cleanup runs in selected intervals with slightly expanded transitions. If no candidates are found, the fixed profile region is used.

This heuristic can mistake titles or drawings for a logo. It scans the complete video and adds work. It supports horizontal profiles only and cannot be combined with `--rect` or `--logo`.

## Quality, audio and logo overlay

| `--modo` | Output FPS | CRF | Preset |
| --- | --- | --- | --- |
| `calidad` (default) | Detected | 18 | `medium` |
| `equilibrado` | 30 | 23 | `veryfast` |
| `rapido` | 15 | 28 | `ultrafast` |

```sh
python notebooklm_ffmpeg.py "video.mp4" --modo rapido
python notebooklm_ffmpeg.py "video.mp4" --modo calidad --crf 16 --preset slow
python notebooklm_ffmpeg.py "video.mp4" --audio copiar
python notebooklm_ffmpeg.py "video.mp4" --audio sin
python notebooklm_ffmpeg.py "video.mp4" --logo "my-logo.png"
```

`--audio copiar` copies the first audio stream if its codec fits MP4; trimming follows audio-packet boundaries. The default AAC mode re-encodes to match output duration. `--audio sin` removes audio. Subtitles, data streams, chapters, additional audio tracks and all original tags are not preserved.

An optional PNG is proportionally fitted and centered inside the cleaned region. Transparency is recommended. It also works in image previews and cannot be combined with contrast detection.

## Batches and limits

```sh
python notebooklm_ffmpeg.py "one.mp4" "two.mp4" --carpeta-salida "processed"
```

Failed inputs do not stop later files; any failure produces exit code 1. Avoid equal base names in a shared output directory. Shell-expanded wildcards can be used where supported.

`delogo` interpolates neighboring pixels and cannot restore hidden artwork, textures or text. Typical NotebookLM inputs have square pixels, even dimensions and orientation applied to pixels. Metadata rotation and incompatible geometry are rejected. Filenames are passed as arguments without shell interpretation.

Tests use real FFmpeg with synthetic inputs to verify geometry, trim counts, FPS, audio, contrast detection, PNG overlays, batches, special filenames, previews and source/output protection. Synthetic fixtures do not establish visual accuracy for every real export; inspect the preview.

References: [FFmpeg delogo](https://ffmpeg.org/ffmpeg-filters.html#delogo), [ffprobe](https://ffmpeg.org/ffprobe.html), [FFmpeg options](https://ffmpeg.org/ffmpeg.html).
