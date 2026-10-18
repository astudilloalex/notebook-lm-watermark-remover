"""Release publication refuses incomplete or corrupted build output."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_tool", ROOT / "scripts/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.assets = Path(self.temp.name)
        self.version = (ROOT / "VERSION").read_text().strip()
        names = [f"NotebookLM-Studio-{self.version}-{tail}" for tail in (
            "Windows-x64-Setup.exe", "Linux-x64.deb", "Linux-x64.rpm",
            "macOS-AppleSilicon.pkg", "macOS-Intel.pkg")]
        names += ["NotebookLM-Studio-" + tail for tail in (
            "Windows-x64.zip", "Linux-x64.tar.gz",
            "macOS-AppleSilicon.zip", "macOS-Intel.zip")]
        for name in names:
            data = ("fixture for " + name).encode()
            (self.assets / name).write_bytes(data)
            (self.assets / (name + ".sha256")).write_text(
                hashlib.sha256(data).hexdigest() + "  " + name + "\n")
        self.package = self.assets / names[0]
        for target in ("windows-x64", "linux-x64", "macos-arm64", "macos-x64"):
            labels = ["portable", "installer", "installed-exe" if target.startswith("windows")
                      else "installed-deb" if target.startswith("linux") else "installed-pkg"]
            if target == "linux-x64":
                labels.append("installed-rpm")
            for label in labels:
                (self.assets / f"verification-{label}-{target}.json").write_text(
                    json.dumps({"target": target, "result": "OK"}))

    def tearDown(self):
        self.temp.cleanup()

    def render(self, tag=None):
        return release.render(tag or "v" + self.version, "owner/project", self.assets)

    def test_complete_release_renders_versioned_english_links(self):
        notes = self.render()
        self.assertIn("## Installers", notes)
        self.assertIn(f"/owner/project/releases/download/v{self.version}/", notes)
        self.assertNotIn("@VERSION@", notes)
        self.assertNotIn("@REPOSITORY@", notes)

    def test_tag_must_match_sources(self):
        with self.assertRaises(ValueError):
            self.render("v0.0.0")

    def test_modified_package_is_rejected(self):
        self.package.write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.render()

    def test_failed_installed_app_verification_is_rejected(self):
        (self.assets / "verification-installed-pkg-macos-arm64.json").write_text(
            json.dumps({"target": "macos-arm64", "result": "FAILED"}))
        with self.assertRaisesRegex(ValueError, "Verification failed"):
            self.render()

    def test_unexpected_release_attachment_is_rejected(self):
        (self.assets / "unreviewed.txt").write_text("must not be published")
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.render()
