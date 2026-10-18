# Building and releasing

The repository contains source files only. `.build/` holds downloaded dependencies, staging trees and test workspaces; `dist/` holds distributable files. Neither directory is tracked.

## Native build requirements

Use Python 3.13+ to run the build scripts on the target OS and architecture.

| Target | Host | Additional tools |
| --- | --- | --- |
| `windows-x64` | Windows x64 | Visual Studio C++ Build Tools/Windows SDK and Inno Setup 6 |
| `linux-x64` | Linux x86_64 | GCC/static libc, dpkg-deb, rpmbuild, desktop-file-validate |
| `macos-arm64` | Apple Silicon Mac | Apple's pkgbuild/productbuild tools |
| `macos-x64` | Intel Mac | Apple's pkgbuild/productbuild tools |

GitHub-hosted runners provide these tools or install the Linux packaging dependencies. No pip dependencies are needed.

```sh
python scripts/build.py --target linux-x64
python scripts/test.py --target linux-x64
python scripts/smoke.py --target linux-x64
python scripts/installers.py --target linux-x64
```

Substitute another target when running on that platform. The app and launchers come from this checkout. Third-party Python/FFmpeg binaries are downloaded over HTTPS and verified before extraction; they are not compiled from source by this workflow.

Installer lifecycle tests deliberately require a GitHub-hosted Actions runner. They install/remove system files and must not be run against a personal installation. Linux DEB and both Mac packages use the runner's package installer; Windows uses Inno Setup's unattended mode. RPM is installed through DNF inside a disposable Fedora 44 container. Tests open the installed launcher as an ordinary user, process/download a batch, close/clean the session, reinstall and remove the app. The Mac test also verifies removal of an obsolete bundle file during upgrade.

## Layout and installers

Windows installs per user in `%LOCALAPPDATA%\Programs\NotebookLM Studio`, using a stable Inno Setup `AppId`, Start menu shortcut and registered uninstaller. Desktop shortcuts are optional. No startup item or Windows service is registered.

Linux packages install the complete payload into `/opt/notebooklm-studio`, with an executable link, a desktop entry and an SVG icon. Dependency metadata declares required system libraries and desktop-opening utilities; bundled shared libraries are not advertised as system RPM providers. RPM build hooks are disabled to avoid rewriting third-party binaries. Debian/RPM packages rely on the system package manager for updates and removal.

Mac packages install a complete `.app` into `/Applications`. A distribution wrapper restricts the CPU architecture and minimum OS version. The component is nonrelocatable and replaces the old bundle on upgrade. Documentation and component notices live inside `Contents/Resources`, so installation preserves them.

No installer configures the app to run at login or as a background system service. The application's explicit close operation controls session deletion and local-server shutdown.

## Signing

Windows Authenticode and Apple Developer ID signing/notarization are not configured. Producing an installer is separate from establishing publisher trust. Do not represent unsigned output as signed or notarized. Publisher credentials would need to be supplied securely and a signing/notarization step added before checksums, testing and release upload. Credentials and private keys must never be committed.

## Release workflow

Pushes to `main`, pull requests and manual runs build/test four native targets and upload artifacts. Installer and portable files have adjacent SHA-256 files. JSON reports distinguish staged/portable tests, installed-app tests and installer lifecycle checks.

For a release:

1. Update `VERSION` and add the corresponding English `docs/releases/<version>.md` notes template.
2. Push and verify the builds on `main`.
3. Create and push an annotated `v<version>` tag at that commit.
4. Actions rebuilds/tests every platform, verifies the tag/version match, renders release links from the template and publishes all assets.

The source-check step rejects binaries and unexpected file types. Build jobs have read-only repository permissions; only the tagged release job can write release contents. Action versions are pinned to commit SHAs. Published version tags are not moved when later versions are released.

## Dependency updates

Update `dependencies.json` and rerun the full native checks. Python and Mac FFmpeg URLs/hashes are fixed. BtbN Linux/Windows FFmpeg uses its current 8.1 channel; the asset's SHA-256 is required and checked before use. Downloaded caches are also verified. The channel can change, so two builds from one commit need not contain identical FFmpeg versions.

Packages record exact resolved URLs and hashes in `LICENSES/COMPONENTS.json`, the distributed FFmpeg license/configuration and the Python license. Linux also includes the static launcher's glibc notice and source/build reference. Network failures, changed vendor assets or missing hashes stop the build instead of silently accepting another binary.
