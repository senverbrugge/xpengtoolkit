"""Zone-only mode: the other places inside Home Assistant that could show the car's position.

Audit of ``grep -rn "latitude\\|longitude" custom_components/xpeng/*.py`` plus the
whole-frame logging, with each site's disposition:

* abrp.py: sends lat/lon to ABRP, an external service the owner chose. Out of scope.
* coordinator.latitude/longitude (_drive_coord): in-memory only; read by the tracker
  (Task 3, zone only) and by the REST weather fetch (``__init__._fetch_rest_data_sync``,
  an XPENG cloud request, not HA). Not written to state, logs or attributes.
* device_tracker.py: handled in Task 3. sensor.py latitude/longitude: Task 4.
* drive_evidence.py: FixTracker/view hold coordinates in memory; nothing logs them.
  ``redact_position`` is the helper for any mapping that has to be shown.
* teslamate_mapping.py / teslamate_provider.py: an HTTP server serving the position
  to the LAN. Refused in the options flow and not started when zone-only is on.
* services.py ``send_navigation``: latitude/longitude are the caller's destination
  (out of scope); the car's own position is never read, returned or logged.
* mqtt_client.py logging: frames are logged by size and section keys only. The one
  site that logs payload text is the listener (``Listener message ... %s``).
* MQTT listener (coordinator.set_listener_message, sensor attribute ``last_payload``,
  ``xpeng_mqtt_message`` event, ``listener_log``, listener INFO/DEBUG log): subscribes
  to arbitrary topics, including state frames, and shows 200-4000 characters of them.
  Refused in the options flow; not started when zone-only is on.
* capture.py raw capture: writes whole frames to disk. Refused the same way.
* mqtt_explorer.py: a standalone CLI script that prints payloads; never runs in HA.
* Diagnostics: the integration has no diagnostics platform and creates no
  persistent notification with position.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _component  # noqa: E402

PKG = _component.component_dir()
LAT, LON = 52.3702, 4.8952


def _load(name):
    spec = importlib.util.spec_from_file_location(f"zl_{name}", PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"zl_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def _validator():
    tree = ast.parse((PKG / "config_flow.py").read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_validate_zone_only"
    )
    fn.returns = None
    for a in fn.args.args:
        a.annotation = None
    ns = {
        "CONF_ZONE_ONLY": "zone_only",
        "CONF_MQTT_LISTENER_ENABLED": "mqtt_listener_enabled",
        "CONF_CAPTURE_ENABLED": "capture_enabled",
        "CONF_TESLAMATE_ENABLED": "teslamate_provider_enabled",
    }
    exec(compile(ast.Module([fn], []), "cf", "exec"), ns)
    return ns["_validate_zone_only"]


def _floats(value):
    if isinstance(value, float):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _floats(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _floats(v)


class ZoneOnlyLeakTests(unittest.TestCase):
    def test_no_state_attribute_carries_coordinates_in_zone_only_mode(self):
        evidence = _load("drive_evidence")
        drive = {"latitude": LAT, "longitude": LON, "coordType": 1, "angle": 90.0, "speed": 0.0}
        shown = evidence.redact_position(drive)
        self.assertEqual(shown, {"speed": 0.0})
        self.assertIn("latitude", drive)  # a copy, the original is untouched
        self.assertFalse(
            [f for f in _floats(shown) if abs(f - LAT) < 0.001 or abs(f - LON) < 0.001]
        )
        self.assertEqual(evidence.redact_position(None), None)

    def test_mqtt_listener_and_capture_are_refused_in_zone_only_mode(self):
        check = _validator()
        for key in ("mqtt_listener_enabled", "capture_enabled"):
            self.assertEqual(
                check(None, {"zone_only": True, key: True}),
                {"zone_only": "zone_only_incompatible"},
            )
            self.assertEqual(check(None, {"zone_only": False, key: True}), {})
        self.assertEqual(check(None, {"zone_only": True}), {})

    def test_teslamate_provider_is_refused_in_zone_only_mode(self):
        check = _validator()
        self.assertEqual(
            check(None, {"zone_only": True, "teslamate_provider_enabled": True}),
            {"zone_only": "zone_only_incompatible"},
        )

    def test_setup_does_not_start_the_listener_capture_or_provider_in_zone_only_mode(self):
        src = (PKG / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("CONF_MQTT_LISTENER_ENABLED, False) and not zone_only", src)
        self.assertIn("CONF_CAPTURE_ENABLED, False) and not zone_only", src)
        self.assertIn("CONF_TESLAMATE_ENABLED) and not zone_only_enabled(entry)", src)

    def test_error_string_is_in_every_language(self):
        import json

        files = [PKG / "strings.json", *sorted((PKG / "translations").glob("*.json"))]
        for f in files:
            err = json.loads(f.read_text(encoding="utf-8"))["options"]["error"]
            self.assertIn("zone_only_incompatible", err, f.name)


if __name__ == "__main__":
    unittest.main()
