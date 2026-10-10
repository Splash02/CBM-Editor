import hashlib
import json
from pathlib import Path
import sys

from nuitka.plugins.PluginBase import NuitkaPluginBase

class NuitkaPluginFmodManifest(NuitkaPluginBase):
    plugin_name = "cbm-fmod-manifest"

    def __init__(self):
        self.platform_key = "win-x64" if sys.platform.startswith("win") else "linux-x86_64"
        self.vendor_dir = Path(__file__).resolve().parent.parent / "cbm_editor/vendor/fmod"
        self.manifest = self._read_verified_manifest()

    def _read_verified_manifest(self):
        manifest = json.loads((self.vendor_dir / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["libraries"].get(self.platform_key, {}).values():
            path = self.vendor_dir / self.platform_key / entry["filename"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"].lower():
                raise RuntimeError(f"FMOD source integrity check failed: {path}")
        return manifest

    def getExtraDlls(self, module):
        if module.getFullName() != "cbm_editor.fmod_audio":
            return
        for entry in self.manifest["libraries"].get(self.platform_key, {}).values():
            relative_path = Path("cbm_editor/vendor/fmod") / self.platform_key / entry["filename"]
            yield self.makeDllEntryPoint(
                source_path=str(self.vendor_dir / self.platform_key / entry["filename"]),
                dest_path=str(relative_path),
                module_name=module.getFullName(),
                package_name=module.getFullName().getPackageName(),
                reason="Verified FMOD runtime",
            )

    def onStandaloneDistributionFinished(self, dist_dir):
        if self._read_verified_manifest() != self.manifest:
            raise RuntimeError("FMOD manifest changed during compilation")
        vendor_dir = Path(dist_dir) / "cbm_editor/vendor/fmod"
        path = vendor_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest != self.manifest:
            raise RuntimeError("FMOD distribution manifest changed during compilation")
        for entry in manifest["libraries"].get(self.platform_key, {}).values():
            entry["sha256"] = hashlib.sha256((vendor_dir / self.platform_key / entry["filename"]).read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.info("Verified FMOD runtime and updated distribution integrity hashes.")
