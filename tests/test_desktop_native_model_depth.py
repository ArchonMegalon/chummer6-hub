import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_desktop_native_model_depth.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_native_model_depth", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopNativeModelDepthTests(unittest.TestCase):
    def test_fails_when_generic_row_projection_markers_are_present(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="desktop-native-model-") as temp_dir:
            root = Path(temp_dir)
            reality = root / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json"
            bridge = root / "ClassicFormPortViewModelBridge.cs"
            section_host = root / "SectionHostControl.axaml.cs"
            output = root / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json"
            reality.write_text(json.dumps({"status": "pass", "generated_at": "2026-06-14T00:00:00Z"}), encoding="utf-8")
            bridge.write_text(
                "\n".join(
                    [
                        "public static ClassicFormPortDomainModel CreateFromRows(IReadOnlyList<SectionRowDisplayItem> rows)",
                        "public static IReadOnlyList<ClassicPortRowFact> FromRows(IReadOnlyList<SectionRowDisplayItem> rows)",
                    ] + ["IReadOnlyList<ClassicPortLineItem> Example,"] * 12 + ["Bucket(", "Bucket(", "Bucket(", "Snapshot("]
                ),
                encoding="utf-8",
            )
            section_host.write_text("public sealed record SectionRowDisplayItem(string Path, string Value)", encoding="utf-8")

            with mock.patch.object(module, "REALITY_AUDIT_PATH", reality), \
                mock.patch.object(module, "BRIDGE_PATH", bridge), \
                mock.patch.object(module, "SECTION_HOST_PATH", section_host), \
                mock.patch.object(module, "OUTPUT_PATH", output):
                with self.assertRaises(SystemExit):
                    module.main()

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertIn("desktop flagship bridge still creates domain state directly from SectionRowDisplayItem rows", payload["failures"])

    def test_passes_when_generic_projection_markers_are_absent(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="desktop-native-model-pass-") as temp_dir:
            root = Path(temp_dir)
            reality = root / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json"
            bridge = root / "ClassicFormPortViewModelBridge.cs"
            section_host = root / "SectionHostControl.axaml.cs"
            output = root / "DESKTOP_NATIVE_MODEL_DEPTH.generated.json"
            reality.write_text(json.dumps({"status": "pass", "generated_at": "2026-06-14T00:00:00Z"}), encoding="utf-8")
            bridge.write_text("public sealed record TypedGearModel(string Name, int Rating);", encoding="utf-8")
            section_host.write_text("// no generic row record", encoding="utf-8")

            with mock.patch.object(module, "REALITY_AUDIT_PATH", reality), \
                mock.patch.object(module, "BRIDGE_PATH", bridge), \
                mock.patch.object(module, "SECTION_HOST_PATH", section_host), \
                mock.patch.object(module, "OUTPUT_PATH", output):
                self.assertEqual(0, module.main())

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("DESKTOP_NATIVE_MODEL_READY", payload["verdict"])


if __name__ == "__main__":
    unittest.main()
