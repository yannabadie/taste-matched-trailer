"""Release gates exercised offline; these checks never call Qloo or a model."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qloo_runtime as runtime


NEW_BACKEND = {
    "status": "ok",
    "adapter_version": "2.7.0-propose-confirm-20261027",
    "qloo_key_present_on_server": True,
    "llm_route_configured": "guarded_qwen_18080",
}
NEW_GATEWAY = {"status": "ok", "gateway_version": "1.2.0-movie-choice-20261027"}


class ReleaseGates(unittest.TestCase):
    def health(self, backend, gateway):
        def reply(request, **_kwargs):
            url = request if isinstance(request, str) else request.full_url
            return io.BytesIO(json.dumps(backend if ":49324/" in url else gateway).encode())
        with patch.object(runtime.urllib.request, "urlopen", side_effect=reply):
            return runtime.backend_health()

    def test_legacy_backend_is_not_admitted_by_successful_health(self):
        legacy = NEW_BACKEND | {"adapter_version": "2.6.2-physical-signal-coverage-20261020"}
        self.assertFalse(self.health(legacy, NEW_GATEWAY))

    def test_legacy_gateway_cannot_be_paired_with_new_backend(self):
        legacy = NEW_GATEWAY | {"gateway_version": "1.1.2-recorded-2.6.3-20261020"}
        self.assertFalse(self.health(NEW_BACKEND, legacy))

    def test_both_expected_versions_and_existing_route_are_required(self):
        self.assertTrue(self.health(NEW_BACKEND, NEW_GATEWAY))
        self.assertFalse(self.health(NEW_BACKEND | {"llm_route_configured": "other"}, NEW_GATEWAY))

    def test_live_legacy_process_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "processes.json"
            metadata.write_text(json.dumps({"managed_by": runtime.LABEL, "release": "2.6.3",
                "components": {"backend": {"pid": 321, "start": "preserved", "command_sha256": "preserved"}}}))
            supervisor = runtime.Supervisor()
            with patch.object(runtime, "META", metadata), patch.object(runtime, "alive", return_value=True), \
                    patch.object(runtime, "matches", return_value=True), patch.object(runtime, "log"):
                with self.assertRaisesRegex(RuntimeError, "CONTROLLED_RESTART"):
                    supervisor.adopt()
            self.assertEqual(supervisor.roles, {})

    def test_dead_legacy_metadata_allows_a_controlled_fresh_start(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "processes.json"
            metadata.write_text(json.dumps({"managed_by": runtime.LABEL, "release": "2.6.3",
                "components": {"backend": {"pid": 321, "start": "preserved", "command_sha256": "preserved"}}}))
            supervisor = runtime.Supervisor()
            with patch.object(runtime, "META", metadata), patch.object(runtime, "alive", return_value=False), \
                    patch.object(runtime, "matches", return_value=False):
                supervisor.adopt()
            self.assertEqual(supervisor.roles, {})


if __name__ == "__main__":
    unittest.main()
