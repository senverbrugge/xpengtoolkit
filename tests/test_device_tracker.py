"""The tracker's map-card contract: ``course`` must come from the car's own angle.

Home Assistant's map card rotates the vehicle marker from ``course``. The tracker
exposed the angle only as a ``bearing`` extra attribute, so the marker always pointed
north; a number that the car never sent must stay None rather than defaulting to 0.
"""
from __future__ import annotations

import ast
import pathlib
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _component  # noqa: E402

TREE = ast.parse(
    (_component.component_dir() / "device_tracker.py").read_text(encoding="utf-8")
)
TRACKER = next(
    node
    for node in TREE.body
    if isinstance(node, ast.ClassDef) and node.name == "XPengDeviceTracker"
)


def _properties(*names, **injected):
    """Execute the real property bodies without importing Home Assistant."""
    nodes = [
        node
        for node in TRACKER.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *nodes,
        ],
        type_ignores=[],
    )
    namespace: dict = {"time": time, **injected}
    exec(compile(ast.fix_missing_locations(module), "<device_tracker>", "exec"), namespace)
    return namespace


def _enabled(entry):
    return bool(entry)


_zone_ns: dict = {}
exec(
    compile(
        (_component.component_dir() / "zone_match.py").read_text(encoding="utf-8"),
        "zone_match",
        "exec",
    ),
    _zone_ns,
)
resolve_zone = _zone_ns["resolve_zone"]

ZONES = [("zone.home", "Home", 52.0, 5.0, 100.0, False)]


class Fix:
    def __init__(self, position, valid=True, age=3.2):
        self.position = position
        self.coord_valid = valid
        self._age = age

    def age_seconds(self, now):
        return self._age


class Stub:
    hass = None

    def __init__(self, zone_only, position=(52.0, 5.0)):
        self._entry = zone_only
        self.coordinator = type("C", (), {"gps_fix": Fix(position)})()

    def _get_nested_value(self, path):
        return {"speed": "12.34", "angle": 90, "coordType": "wgs84"}[path.rsplit(".", 1)[1]]


def _props():
    return _properties(
        "latitude", "longitude", "course", "extra_state_attributes", "location_name",
        zone_only_enabled=_enabled, resolve_zone=resolve_zone, _zones=lambda hass: ZONES,
    )


def _get(name, stub):
    return _props()[name].fget(stub)


class ZoneOnlyTests(unittest.TestCase):
    def test_zone_only_hides_position_attributes(self):
        attrs = _get("extra_state_attributes", Stub(True))
        self.assertEqual(set(attrs), {"fix_age_s", "coord_valid"})

    def test_zone_only_latitude_longitude_course_are_none(self):
        stub = Stub(True)
        for name in ("latitude", "longitude", "course"):
            self.assertIsNone(_get(name, stub), name)

    def test_zone_only_location_name_is_the_zone(self):
        self.assertEqual(_get("location_name", Stub(True)), "home")
        self.assertEqual(_get("location_name", Stub(True, (10.0, 10.0))), "not_home")

    def test_unknown_fix_gives_no_location_name(self):
        self.assertIsNone(_get("location_name", Stub(True, None)))

    def test_a_non_home_zone_gives_its_friendly_name(self):
        zones = [*ZONES, ("zone.work", "Work", 53.0, 6.0, 50.0, False)]
        ns = _properties(
            "location_name", zone_only_enabled=_enabled,
            resolve_zone=resolve_zone, _zones=lambda hass: zones,
        )
        self.assertEqual(ns["location_name"].fget(Stub(True, (53.0, 6.0))), "Work")

    def test_one_filtered_listener_covers_all_zone_changes(self):
        import asyncio

        calls = {}

        class Tracker:
            def async_remove(self):
                pass

        def track(hass, track_states, action):
            calls["states"] = track_states
            return Tracker()

        class Base:
            async def async_added_to_hass(self):
                pass

        node = next(
            n for n in TRACKER.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_added_to_hass"
        )
        cls = ast.ClassDef(
            name="Host", bases=[ast.Name("Base", ast.Load())], keywords=[],
            body=[node], decorator_list=[], type_params=[],
        )
        ns = {
            "Base": Base, "zone_only_enabled": _enabled,
            "TrackStates": lambda *a: a, "async_track_state_change_filtered": track,
            "callback": lambda f: f, "Event": object,
        }
        exec(compile(ast.fix_missing_locations(ast.Module([cls], [])), "<t>", "exec"), ns)

        class Host(ns["Host"]):
            hass = object()

            def __init__(self, on):
                self._entry = on
                self.removers = []

            def async_on_remove(self, fn):
                self.removers.append(fn)

        host = Host(True)
        asyncio.run(host.async_added_to_hass())
        self.assertEqual(calls["states"], (False, set(), {"zone"}))
        self.assertEqual(len(host.removers), 1)

        calls.clear()
        off = Host(False)
        asyncio.run(off.async_added_to_hass())
        self.assertEqual((calls, off.removers), ({}, []))

    def test_option_off_is_unchanged(self):
        stub = Stub(False)
        self.assertEqual(_get("latitude", stub), 52.0)
        self.assertEqual(_get("longitude", stub), 5.0)
        self.assertEqual(_get("course", stub), 90.0)
        self.assertEqual(
            set(_get("extra_state_attributes", stub)),
            {"speed", "bearing", "coord_type", "coord_valid", "fix_age_s"},
        )
        self.assertIsNone(_get("location_name", stub))


class CourseTests(unittest.TestCase):
    def _course(self, angle):
        getter = _properties("course", zone_only_enabled=_enabled)["course"]
        self.assertIsInstance(getter, property)
        requested = []

        class Stub:
            _entry = None

            def _get_nested_value(self, path):
                requested.append(path)
                return angle

        value = getter.fget(Stub())
        self.assertEqual(requested, ["msg_content.interval.drive.angle"])
        return value

    def test_the_angle_becomes_a_float_course(self):
        self.assertEqual(self._course(90), 90.0)
        self.assertEqual(self._course(186.4), 186.4)

    def test_no_angle_is_none_not_zero(self):
        """0 degrees is north: a car that sent nothing must not point there."""
        self.assertIsNone(self._course(None))

    def test_a_malformed_angle_does_not_raise(self):
        for bad in ("north", {}, []):
            self.assertIsNone(self._course(bad), bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
