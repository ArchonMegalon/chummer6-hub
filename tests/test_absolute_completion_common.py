from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "absolute_completion_common.py"


def load_module():
    spec = importlib.util.spec_from_file_location("absolute_completion_common", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AbsoluteCompletionCommonTests(unittest.TestCase):
    def test_workspace_root_override_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory(prefix="absolute-completion-workspace-") as temp_dir:
            workspace = Path(temp_dir)

            with mock.patch.dict(os.environ, {"CHUMMER_WORKSPACE_ROOT": str(workspace)}):
                module = load_module()

            self.assertEqual(workspace, module.WORKSPACE_ROOT)
            self.assertEqual(workspace / "Chummer6", module.CHUMMER6_ROOT)
            self.assertEqual(workspace / "_completion" / "chummer6_absolute_completion", module.DEFAULT_COMPLETION_ROOT)

    def test_local_hub_no_build_falls_back_when_debug_binary_is_missing(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="absolute-completion-run-services-") as temp_dir:
            run_services = Path(temp_dir)

            with mock.patch.object(module, "RUN_SERVICES_ROOT", run_services):
                self.assertFalse(module.LocalHubApp(no_build=True)._should_skip_build())

                binary = run_services / "Chummer.Run.Api" / "bin" / "Debug" / "net10.0" / "Chummer.Run.Api"
                binary.parent.mkdir(parents=True)
                binary.write_text("", encoding="utf-8")
                self.assertTrue(module.LocalHubApp(no_build=True)._should_skip_build())

    def test_local_hub_strict_no_build_keeps_requested_flag(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="absolute-completion-run-services-") as temp_dir:
            with (
                mock.patch.object(module, "RUN_SERVICES_ROOT", Path(temp_dir)),
                mock.patch.dict(os.environ, {"CHUMMER_LOCAL_HUB_STRICT_NO_BUILD": "1"}),
            ):
                self.assertTrue(module.LocalHubApp(no_build=True)._should_skip_build())


if __name__ == "__main__":
    unittest.main()
