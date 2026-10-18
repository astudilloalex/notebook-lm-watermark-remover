"""Validate a complete tagged build and render its English release notes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def render(tag, repository, assets):
    version = (ROOT / "VERSION").read_text().strip()
    if tag != "v" + version or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Release tag must match VERSION")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected repository in owner/name format")
    installers = [f"NotebookLM-Studio-{version}-{name}" for name in (
        "Windows-x64-Setup.exe", "Linux-x64.deb", "Linux-x64.rpm",
        "macOS-AppleSilicon.pkg", "macOS-Intel.pkg")]
    portable = ["NotebookLM-Studio-" + name for name in (
        "Windows-x64.zip", "Linux-x64.tar.gz", "macOS-AppleSilicon.zip", "macOS-Intel.zip")]
    expected = set(installers + portable)
    for name in tuple(expected):
        path = assets / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        checksum = name + ".sha256"
        if (assets / checksum).read_text().strip() != digest + "  " + name:
            raise ValueError("Invalid checksum: " + name)
        expected.add(checksum)
    for target in ("windows-x64", "linux-x64", "macos-arm64", "macos-x64"):
        labels = ["portable", "installer", "installed-exe" if target.startswith("windows")
                  else "installed-deb" if target.startswith("linux") else "installed-pkg"]
        if target == "linux-x64":
            labels.append("installed-rpm")
        for label in labels:
            name = f"verification-{label}-{target}.json"
            record = json.loads((assets / name).read_text())
            if record.get("result") != "OK" or record.get("target") != target:
                raise ValueError("Verification failed: " + name)
            expected.add(name)
    actual = {path.name for path in assets.iterdir()}
    if actual != expected:
        raise ValueError(f"Unexpected/missing release assets: {actual ^ expected}")
    template = (ROOT / "docs/releases" / (version + ".md")).read_text()
    return template.replace("@VERSION@", version).replace("@REPOSITORY@", repository)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(render(args.tag, args.repository, args.assets), encoding="utf-8")
    print("Verified all installers, portable packages, hashes and reports.")
