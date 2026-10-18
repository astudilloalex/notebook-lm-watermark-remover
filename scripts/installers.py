"""Build native installers and test them on disposable GitHub Actions runners."""

import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import time

from build import BUILD, ROOT, TARGETS, digest, layout

ID = "io.github.astudilloalex.NotebookLMStudio"
OUTPUT = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text().strip()


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def checksum(path):
    path.with_name(path.name + ".sha256").write_text(
        digest(path) + "  " + path.name + "\n", encoding="utf-8")


def linux_payload(base, work):
    payload = work / "payload"
    if payload.exists():
        shutil.rmtree(payload)
    app = payload / "opt/notebooklm-studio"
    shutil.copytree(base, app, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for directory in ("usr/bin", "usr/share/applications",
                      "usr/share/icons/hicolor/scalable/apps"):
        (payload / directory).mkdir(parents=True)
    (payload / "usr/bin/notebooklm-studio").symlink_to(
        "/opt/notebooklm-studio/NotebookLM Studio")
    shutil.copyfile(ROOT / f"installers/linux/{ID}.desktop",
                    payload / f"usr/share/applications/{ID}.desktop")
    shutil.copyfile(ROOT / "launchers/icon.svg",
                    payload / f"usr/share/icons/hicolor/scalable/apps/{ID}.svg")
    for path in payload.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    run("desktop-file-validate", payload / f"usr/share/applications/{ID}.desktop")
    return payload


def build_linux(base, work):
    payload = linux_payload(base, work)
    debroot = work / "deb"
    if debroot.exists():
        shutil.rmtree(debroot)
    shutil.copytree(payload, debroot, symlinks=True)
    control = debroot / "DEBIAN"
    control.mkdir()
    size = sum(p.stat().st_size for p in payload.rglob("*") if p.is_file()) // 1024
    (control / "control").write_text(
        f"Package: notebooklm-studio\nVersion: {VERSION}\nArchitecture: amd64\n"
        "Maintainer: Alex Astudillo <astudilloalex1@gmail.com>\n"
        "Section: video\nPriority: optional\n"
        f"Installed-Size: {size}\n"
        "Depends: libc6 (>= 2.28), libgcc-s1, libstdc++6, zlib1g, xdg-utils\n"
        "Homepage: https://github.com/astudilloalex/notebook-lm-watermark-remover\n"
        "Description: Local batch video processor for NotebookLM\n"
        " Includes Python, FFmpeg and a browser interface with end-trim previews.\n",
        encoding="utf-8")
    deb = OUTPUT / f"NotebookLM-Studio-{VERSION}-Linux-x64.deb"
    run("dpkg-deb", "--root-owner-group", "--build", debroot, deb)
    rpmroot = work / "rpmbuild"
    for directory in ("BUILD", "BUILDROOT", "RPMS", "SPECS", "SOURCES", "SRPMS"):
        (rpmroot / directory).mkdir(parents=True, exist_ok=True)
    spec = rpmroot / "SPECS/notebooklm-studio.spec"
    spec.write_text(
        f"Name: notebooklm-studio\nVersion: {VERSION}\nRelease: 1\n"
        "Summary: Local batch video processor for NotebookLM\n"
        "License: See bundled LICENSES directory\n"
        "URL: https://github.com/astudilloalex/notebook-lm-watermark-remover\n"
        "BuildArch: x86_64\nAutoReqProv: no\n"
        "Requires: glibc >= 2.28, libgcc, libstdc++, zlib, xdg-utils\n"
        "%description\nLocal video processing with bundled Python and FFmpeg.\n"
        "%prep\n%build\n%install\n"
        'mkdir -p "%{buildroot}"\n'
        f'cp -a {shlex.quote(str(payload))}/. "%{{buildroot}}/"\n'
        "%files\n/opt/notebooklm-studio\n/usr/bin/notebooklm-studio\n"
        f"/usr/share/applications/{ID}.desktop\n"
        f"/usr/share/icons/hicolor/scalable/apps/{ID}.svg\n",
        encoding="utf-8")
    run("rpmbuild", "-bb", "--define", f"_topdir {rpmroot}",
        "--define", "__os_install_post %{nil}", "--define", "_build_id_links none",
        "--define", "_binary_payload w9.xzdio", spec)
    rpms = list((rpmroot / "RPMS/x86_64").glob("*.rpm"))
    if len(rpms) != 1:
        raise RuntimeError(f"Expected one RPM, got {rpms}")
    rpm = OUTPUT / f"NotebookLM-Studio-{VERSION}-Linux-x64.rpm"
    shutil.copyfile(rpms[0], rpm)
    return [deb, rpm]


def build_windows(base):
    compiler = shutil.which("ISCC.exe")
    if not compiler:
        compiler = str(Path(os.environ["ProgramFiles(x86)"]) / "Inno Setup 6/ISCC.exe")
    run(compiler, f"/DAppVersion={VERSION}", f"/DPayloadPath={base}",
        f"/DOutputPath={OUTPUT}", f"/DIconPath={BUILD / 'icons/icon.ico'}",
        ROOT / "installers/windows/setup.iss")
    return [OUTPUT / f"NotebookLM-Studio-{VERSION}-Windows-x64-Setup.exe"]


def build_macos(package, target, work):
    components = work / "components.plist"
    components.write_bytes(plistlib.dumps([{
        "RootRelativeBundlePath": "NotebookLM Studio.app",
        "BundleIsRelocatable": False,
        "BundleIsVersionChecked": True,
        "BundleHasStrictIdentifier": True,
        "BundleOverwriteAction": "upgrade",
    }]))
    root = work / "root"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    shutil.copytree(package / "NotebookLM Studio.app", root / "NotebookLM Studio.app",
                    symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    label = TARGETS[target][3]
    component = work / "component.pkg"
    run("/usr/bin/pkgbuild", "--root", root, "--component-plist", components,
        "--identifier", ID, "--version", VERSION, "--install-location",
        "/Applications", "--ownership", "recommended", component)
    architecture = "arm64" if target == "macos-arm64" else "x86_64"
    distribution = work / "distribution.xml"
    distribution.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<installer-gui-script minSpecVersion="2">\n'
        "<title>NotebookLM Studio</title>\n"
        f'<options customize="never" require-scripts="false" hostArchitectures="{architecture}"/>\n'
        '<domains enable_localSystem="true" enable_currentUserHome="false" enable_anywhere="false"/>\n'
        '<volume-check script="true"><allowed-os-versions><os-version min="12.0"/></allowed-os-versions></volume-check>\n'
        '<choices-outline><line choice="default"/></choices-outline>\n'
        f'<choice id="default" visible="false"><pkg-ref id="{ID}"/></choice>\n'
        f'<pkg-ref id="{ID}" version="{VERSION}">component.pkg</pkg-ref>\n'
        '</installer-gui-script>\n', encoding="utf-8")
    output = OUTPUT / f"NotebookLM-Studio-{VERSION}-{label}.pkg"
    run("/usr/bin/productbuild", "--distribution", distribution,
        "--package-path", work, output)
    return [output]


def build(target):
    package, base, _, _ = layout(target)
    work = BUILD / "installers" / target
    work.mkdir(parents=True, exist_ok=True)
    if target == "linux-x64":
        artifacts = build_linux(base, work)
    elif target == "windows-x64":
        artifacts = build_windows(base)
    else:
        artifacts = build_macos(package, target, work)
    for artifact in artifacts:
        checksum(artifact)
        print("Installer created:", artifact, flush=True)


def smoke(target, base, label):
    run(sys.executable, ROOT / "scripts/smoke.py", "--target", target,
        "--base", base, "--label", label)


def saved_downloads(target, label):
    folder = BUILD / "smoke" / f"{label}-{target}" / "Downloads"
    return {path: digest(path) for path in folder.iterdir()}


def wait_missing(path):
    deadline = time.monotonic() + 60
    while path.exists():
        if time.monotonic() > deadline:
            raise RuntimeError(f"Uninstall did not remove {path}")
        time.sleep(0.2)


def test(target):
    # Installing/removing system files is intentionally restricted to ephemeral CI.
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise RuntimeError("Installer lifecycle tests run only on disposable GitHub Actions runners.")
    if target == "windows-x64":
        base = Path(os.environ["LOCALAPPDATA"]) / "Programs/NotebookLM Studio"
        setup = OUTPUT / f"NotebookLM-Studio-{VERSION}-Windows-x64-Setup.exe"
        arguments = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-")
        run(setup, *arguments)
        shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/NotebookLM Studio.lnk"
        assert shortcut.is_file(), shortcut
        smoke(target, base, "installed-exe")
        saved = saved_downloads(target, "installed-exe")
        run(setup, *arguments)  # Same-version upgrade uses the stable AppId.
        run(base / "unins000.exe", *arguments)
        wait_missing(base / "NotebookLM Studio.exe")
        wait_missing(shortcut)
    elif target == "linux-x64":
        base = Path("/opt/notebooklm-studio")
        deb = OUTPUT / f"NotebookLM-Studio-{VERSION}-Linux-x64.deb"
        run("sudo", "dpkg", "--install", deb)
        assert Path("/usr/bin/notebooklm-studio").resolve() == base / "NotebookLM Studio"
        smoke(target, base, "installed-deb")
        saved = saved_downloads(target, "installed-deb")
        run("sudo", "dpkg", "--install", deb)
        run("sudo", "dpkg", "--remove", "notebooklm-studio")
        wait_missing(base)
        assert not Path(f"/usr/share/applications/{ID}.desktop").exists()
        rpm = f"NotebookLM-Studio-{VERSION}-Linux-x64.rpm"
        run("docker", "run", "--rm", "-v", f"{ROOT}:/src", "-w", "/src",
            "fedora:44", "/bin/bash", "/src/installers/linux/test-rpm.sh", rpm, os.getuid())
        saved.update(saved_downloads(target, "installed-rpm"))
    else:
        bundle = Path("/Applications/NotebookLM Studio.app")
        base = bundle / "Contents/Resources"
        pkg = OUTPUT / f"NotebookLM-Studio-{VERSION}-{TARGETS[target][3]}.pkg"
        run("sudo", "/usr/sbin/installer", "-pkg", pkg, "-target", "/")
        smoke(target, base, "installed-pkg")
        saved = saved_downloads(target, "installed-pkg")
        sentinel = bundle / "Contents/obsolete-upgrade-check"
        run("sudo", "/usr/bin/touch", sentinel)
        run("sudo", "/usr/sbin/installer", "-pkg", pkg, "-target", "/")
        assert not sentinel.exists(), "Upgrade left an obsolete bundle file behind"
        run("sudo", "/bin/rm", "-rf", bundle)
        run("sudo", "/usr/sbin/pkgutil", "--forget", ID)
        assert not bundle.exists()
    assert saved and all(path.is_file() and digest(path) == value for path, value in saved.items())
    record = {"target": target, "result": "OK",
              "checks": "Install, launch, process/download/close, reinstall, uninstall",
              "downloads": "Saved MP4/ZIP copies survive session cleanup and uninstall"}
    (OUTPUT / f"verification-installer-{target}.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    if args.test:
        test(args.target)
    else:
        build(args.target)
