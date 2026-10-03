import hashlib
import json
from pathlib import Path

from nuitka.plugins.PluginBase import NuitkaPluginBase


class NuitkaPluginBassManifest(NuitkaPluginBase):
    plugin_name = "cbm-bass-manifest"
    platform_key = "linux-x86_64"

    def __init__(self):
        self.vendor_dir = Path(__file__).resolve().parent.parent / "cbm_editor" / "vendor" / "bass"
        self.manifest = self._read_verified_manifest()

    def _read_verified_manifest(self):
        manifest = json.loads((self.vendor_dir / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["libraries"][self.platform_key].values():
            library_path = self.vendor_dir / self.platform_key / entry["filename"]
            digest = hashlib.sha256(library_path.read_bytes()).hexdigest()
            if digest != entry["sha256"].lower():
                raise RuntimeError(f"BASS source integrity check failed: {library_path}")
        return manifest

    def getExtraDlls(self, module):
        if module.getFullName() != "cbm_editor.bass_audio":
            return
        for entry in self.manifest["libraries"][self.platform_key].values():
            relative_path = Path("cbm_editor") / "vendor" / "bass" / self.platform_key / entry["filename"]
            yield self.makeDllEntryPoint(
                source_path=str(self.vendor_dir / self.platform_key / entry["filename"]),
                dest_path=str(relative_path),
                module_name=module.getFullName(),
                package_name=module.getFullName().getPackageName(),
                reason="Verified BASS library",
            )

    def onStandaloneDistributionFinished(self, dist_dir):
        vendor_dir = Path(dist_dir) / "cbm_editor" / "vendor" / "bass"
        manifest_path = vendor_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest != self.manifest or self._read_verified_manifest() != self.manifest:
            raise RuntimeError("BASS manifest changed during compilation")
        for entry in manifest["libraries"][self.platform_key].values():
            library_path = vendor_dir / self.platform_key / entry["filename"]
            entry["sha256"] = hashlib.sha256(library_path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        self.info("Updated BASS integrity hashes after Linux library processing.")
