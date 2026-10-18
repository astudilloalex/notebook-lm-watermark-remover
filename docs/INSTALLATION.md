# Installation

Download an installer from the [latest release](https://github.com/astudilloalex/notebook-lm-watermark-remover/releases/latest). Installers include Python, FFmpeg and ffprobe. Internet access is needed to download the installer; processing runs locally afterward. A browser is required to display the interface.

## Windows

Open `NotebookLM-Studio-<version>-Windows-x64-Setup.exe` and follow the wizard. Installation is for the current user, normally under `%LOCALAPPDATA%\Programs\NotebookLM Studio`, and does not request administrator access.

The installer adds a Start menu shortcut, offers an optional desktop shortcut and registers an uninstaller. Open NotebookLM Studio from the Start menu. To update, close the app using its own close button and run the newer installer. To remove it, use Windows Settings → Apps → Installed apps → NotebookLM Studio → Uninstall.

## Linux

Use the package for your distribution. Linux x64 requires glibc 2.28+ and kernel 4.18+; the package manager resolves the declared system dependencies.

- **Ubuntu/Debian:** open the `.deb` file with your software/package installer and select Install.
- **Fedora/RPM distributions:** open the `.rpm` file with your package installer and select Install.

Installation normally requires your administrator password. The app is installed under `/opt/notebooklm-studio`, with a launcher in the applications menu and `/usr/bin/notebooklm-studio`. Install a newer package to update. Remove NotebookLM Studio through your distribution's package manager.

Graphical DEB/RPM file handling varies by desktop and distribution. If opening a package does not show an installer, use your distribution's graphical package-management application. Developer/advanced alternatives are `sudo apt install ./package.deb` and `sudo dnf install ./package.rpm`. Portable tar.gz packages are also available for other compatible distributions.

DEB installation is tested on Ubuntu 22.04; RPM installation and dependency resolution are tested on Fedora 44. Other RPM/DEB distributions are not individually tested.

## macOS

Choose `macOS-AppleSilicon.pkg` for an M-series Mac or `macOS-Intel.pkg` for an Intel Mac. macOS 12 or newer is required. Open the `.pkg`, follow Apple's Installer and provide administrator approval when requested. The app appears in `/Applications/NotebookLM Studio.app`; open it from Applications or Spotlight.

Close the app before installing an update. The installer replaces the previous bundle, including obsolete bundle files. To remove the application, close it and move NotebookLM Studio from Applications to Trash. The small system installer receipt can remain; it does not run a service.

## Signing and system approval

These installers are unsigned. Windows may show SmartScreen or publisher warnings; macOS packages are not signed with a Developer ID Installer certificate or notarized, so Gatekeeper may block the initial opening. Installing a package does not remove these operating-system checks.

Only approve software you trust, after reviewing its source/release and integrity information. Signing and notarization require publisher-owned certificates and credentials, which are not present in this repository. The workflow does not claim a verified publisher or attempt to disable operating-system protections. See [Apple's distribution guidance](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution).

## Open, close and uninstall

Launching the app opens a private address on `127.0.0.1` in your default browser. The dynamically chosen local port is expected. No system service or login startup item is installed.

**Download your results, wait for downloads to finish, then use the application's close button and confirm session deletion.** Closing the browser tab alone does not stop the server. The session's internal videos and previews are deleted on confirmed closure; downloaded copies and originals are retained.

Close the application before updating or uninstalling it. Uninstallers remove installed program files and shortcuts; they do not remove original videos or downloaded results. User data directories may retain a small overwritten diagnostic log, lock/index files and any sessions left by a forced exit. Abandoned owned sessions are cleaned the next time the app starts.

## Portable packages and checksums

ZIP/tar.gz downloads still contain complete portable folders. Extract them entirely before opening the launcher. They are optional alternatives to the installers. On Mac, the `.app` bundle contains the documentation and component notices in `Contents/Resources`.

Each downloadable application/installer has an adjacent `.sha256` file. Verification reports describe the CI checks; they are not application installers. GitHub's generated Source code archives contain the development sources and do not include Python or FFmpeg.
