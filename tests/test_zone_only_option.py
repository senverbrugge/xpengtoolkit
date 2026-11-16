"""The "Report zone only" privacy option: constant, helper and options form."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _component  # noqa: E402

PKG_DIR = _component.component_dir()


def _load_layout():
    pkg = types.ModuleType("zo_pkg")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["zo_pkg"] = pkg
    for name in ("command_policy", "entity_layout"):
        spec = importlib.util.spec_from_file_location(f"zo_pkg.{name}", PKG_DIR / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"zo_pkg.{name}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["zo_pkg.entity_layout"]


layout = _load_layout()


class ZoneOnlyOptionTests(unittest.TestCase):
    def test_option_defaults_off(self):
        self.assertFalse(layout.zone_only_enabled(SimpleNamespace(options={})))

    def test_option_on(self):
        self.assertTrue(layout.zone_only_enabled(SimpleNamespace(options={"zone_only": True})))

    def test_constant_value(self):
        self.assertIn(
            'CONF_ZONE_ONLY: Final = "zone_only"',
            (PKG_DIR / "const.py").read_text(encoding="utf-8"),
        )

    def test_options_form_offers_the_field(self):
        src = (PKG_DIR / "config_flow.py").read_text(encoding="utf-8")
        self.assertIn(
            "vol.Optional(\n                        CONF_ZONE_ONLY,"
            "\n                        default=bool(current.get(CONF_ZONE_ONLY, False)),"
            "\n                    ): bool,",
            src,
        )


DESCRIPTIONS = [SimpleNamespace(key=k) for k in ("latitude", "longitude", "range")]


class ZoneOnlySensorTests(unittest.TestCase):
    def test_sensor_setup_skips_latitude_and_longitude_when_zone_only(self):
        kept = layout.sensor_descriptions(SimpleNamespace(options={"zone_only": True}), DESCRIPTIONS)
        self.assertEqual([d.key for d in kept], ["range"])

    def test_sensor_setup_keeps_them_when_off(self):
        kept = layout.sensor_descriptions(SimpleNamespace(options={}), DESCRIPTIONS)
        self.assertEqual(len(kept), 3)

    def test_registry_cleanup_removes_only_the_two_sensors(self):
        records = {
            "sensor.lat": SimpleNamespace(unique_id="xpeng_V_latitude", config_entry_id="e"),
            "sensor.lon": SimpleNamespace(unique_id="xpeng_V_longitude", config_entry_id="e"),
            "sensor.range": SimpleNamespace(unique_id="xpeng_V_range", config_entry_id="e"),
        }

        class Registry:
            def async_get_entity_id(self, domain, platform, uid):
                return next((k for k, v in records.items() if v.unique_id == uid), None)

            def async_get(self, eid):
                return records.get(eid)

            def async_remove(self, eid):
                del records[eid]

        ha = types.ModuleType("homeassistant")
        helpers = types.ModuleType("homeassistant.helpers")
        er = types.ModuleType("homeassistant.helpers.entity_registry")
        er.async_get = lambda hass: Registry()
        ha.helpers, helpers.entity_registry = helpers, er
        saved = {n: sys.modules.get(n) for n in (ha.__name__, helpers.__name__, er.__name__)}
        sys.modules.update({"homeassistant": ha, "homeassistant.helpers": helpers,
                            "homeassistant.helpers.entity_registry": er})
        try:
            off = SimpleNamespace(options={}, entry_id="e")
            layout.remove_zone_only_sensors(object(), off, "V")
            self.assertEqual(len(records), 3)
            on = SimpleNamespace(options={"zone_only": True}, entry_id="e")
            layout.remove_zone_only_sensors(object(), on, "V")
            self.assertEqual(list(records), ["sensor.range"])
        finally:
            for n, m in saved.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m


if __name__ == "__main__":
    unittest.main()
