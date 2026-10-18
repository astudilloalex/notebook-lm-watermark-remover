# NotebookLM Studio

Process NotebookLM videos locally with FFmpeg. Add horizontal videos and Shorts to one queue, compare the original with the processed result, and choose exactly how much to trim from the end of each video or an entire batch.

**[Download the latest release](https://github.com/astudilloalex/notebook-lm-watermark-remover/releases/latest)** · [Installation](docs/INSTALLATION.md) · [User guide](docs/USAGE.md) · [Build from source](docs/BUILDING.md)

## Install and open

| System | Download | Open after installation |
| --- | --- | --- |
| Windows 10/11 x64 | `Windows-x64-Setup.exe` | NotebookLM Studio in the Start menu |
| Ubuntu / Debian x64 | `Linux-x64.deb` | NotebookLM Studio in the applications menu |
| Fedora / compatible RPM distributions x64 | `Linux-x64.rpm` | NotebookLM Studio in the applications menu |
| Mac with Apple Silicon | `macOS-AppleSilicon.pkg` | NotebookLM Studio in Applications |
| Mac with an Intel processor | `macOS-Intel.pkg` | NotebookLM Studio in Applications |

Choose the installer from the release's **Assets** section and open it. Python, FFmpeg and ffprobe are included; you do not need to install them or use a terminal. A web browser is required. Linux needs a desktop package installer associated with DEB/RPM files; the [installation guide](docs/INSTALLATION.md) explains alternatives.

Portable ZIP/tar.gz packages remain available. GitHub's **Source code** downloads are for developers.

The Windows and Mac installers are currently unsigned; the Mac packages are not notarized. Windows or macOS may require an explicit security approval. Fully trusted first-run installation requires the publisher's signing certificates and Apple notarization credentials. See [installation and signing limits](docs/INSTALLATION.md#signing-and-system-approval).

## Features

- Multiple-file upload, mixed horizontal/Short batches, and sequential processing.
- Before/after image comparison and original/result video playback.
- End trimming in frames or seconds, individually or for a selection.
- Preview the final seconds with audio and select the last frame to keep.
- Individual MP4 downloads or one ZIP containing completed results.
- Local processing: videos are handled on your computer, without a cloud upload.

Logo cleanup uses FFmpeg's `delogo` interpolation. It can leave a visible patch on detailed backgrounds, so review the preview. Automatic profiles use aspect ratio and FPS rather than recognizing an actual NotebookLM closing screen. This independent project is not affiliated with Google.

## Download before closing

All internal results, uploaded working copies and previews belong to a temporary session. **Close app → Delete session and close** stops work and transfers, deletes that session, and requests server shutdown. Undownloaded results are lost. Originals and copies downloaded outside the session are preserved.

Closing only the browser tab does not stop the local server. Abandoned sessions are cleaned on the next start when their process lock is no longer held. Separate running instances do not delete each other's sessions. Older persistent results created before temporary-session support are not removed automatically.

## Source-only repository

```text
app/                 Python processor/server and HTML/CSS/JavaScript interface
launchers/           Native C/shell launchers and SVG icon source
installers/          Inno Setup, Linux desktop integration and CI test recipes
scripts/             Build, package, verification and release tooling
tests/               Real FFmpeg, HTTP, session and cleanup tests
docs/                Installation, usage, CLI and build documentation
.github/workflows/   Native builds and tagged release publication
dependencies.json    Download origins and integrity checks
VERSION              Application/release version
```

Only text source and documentation are versioned. Runtimes, executables, videos, caches and installers are generated in ignored `.build/` and `dist/` directories. The app uses Python's standard library, with no pip dependencies.

For development, install Python 3.10+ and FFmpeg/ffprobe with `delogo` and `libx264`, then run:

```sh
python app/interfaz_local.py
python -m unittest discover -s tests -v
```

The application interface currently uses Spanish. Repository documentation, installer dialogs and release notes use English. Existing module names, CLI flags and internal API fields retain their original Spanish names for compatibility. The [CLI guide](docs/CLI.md) documents them in English.

## GitHub Actions and releases

Every push to `main`, pull request and manual run builds on Windows, Linux, Mac Intel and Mac Apple Silicon. CI verifies source-only tracking, dependency hashes, the 35-test suite, the portable package, and the installed application. Installer checks cover install, launch, batch processing/downloads, session cleanup, reinstall and removal. DEB is installed on Ubuntu; RPM is installed with dependency resolution in a Fedora 44 container.

Successful jobs upload installers, portable packages, SHA-256 files and verification reports as Actions artifacts for 30 days. A tag such as `v2.5.0` also publishes those files to a public GitHub Release after every platform passes. The tag must match `VERSION`; release notes are generated in English from a versioned template.

Python and Mac FFmpeg downloads have fixed URLs and SHA-256 hashes. Linux/Windows FFmpeg is resolved from BtbN's official 8.1 channel and verified against the asset's published SHA-256. That channel may change between builds. Each package records the exact resolved downloads in `LICENSES/COMPONENTS.json`. CI compiles this project's launchers and downloads third-party runtimes; it does not compile Python or FFmpeg themselves.

Build instructions, dependency updates and installer implementation details are in [BUILDING.md](docs/BUILDING.md).
