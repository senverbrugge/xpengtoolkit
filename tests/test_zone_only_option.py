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


if __name__ == "__main__":
    unittest.main()
