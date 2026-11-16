"""resolve_zone: map a position onto the zone state Home Assistant would report."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _component  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "zone_match", _component.component_dir() / "zone_match.py"
)
zone_match = importlib.util.module_from_spec(_spec)
sys.modules["zone_match"] = zone_match
_spec.loader.exec_module(zone_match)
resolve_zone = zone_match.resolve_zone

HOME = ("zone.home", "Home", 52.0, 5.0, 100.0, False)
WORK = ("zone.work", "Work", 52.1, 5.1, 200.0, False)


class ResolveZoneTest(unittest.TestCase):
    def test_inside_home_reports_home(self):
        self.assertEqual(resolve_zone(52.0, 5.0005, [HOME, WORK]), "home")

    def test_inside_named_zone_reports_friendly_name(self):
        self.assertEqual(resolve_zone(52.1, 5.1, [HOME, WORK]), "Work")

    def test_closest_centre_wins_over_smaller_radius(self):
        big = ("zone.city", "City", 52.0, 5.0, 2000.0, False)
        small = ("zone.garden", "Garden", 52.0009, 5.0, 150.0, False)
        # point is 10 m from the big zone's centre and ~ 90 m from the small one
        self.assertEqual(resolve_zone(52.0001, 5.0, [big, small]), "City")
        self.assertEqual(resolve_zone(52.0009, 5.0, [big, small]), "Garden")

    def test_equal_distance_goes_to_the_smaller_radius(self):
        big = ("zone.city", "City", 52.0, 5.0, 2000.0, False)
        small = ("zone.garden", "Garden", 52.0, 5.0, 150.0, False)
        self.assertEqual(resolve_zone(52.0, 5.0, [big, small]), "Garden")
        self.assertEqual(resolve_zone(52.0, 5.0, [small, big]), "Garden")

    def test_point_exactly_on_the_edge_is_outside(self):
        d = zone_match._distance_m(52.0, 5.0, 52.001, 5.0)
        edge = ("zone.edge", "Edge", 52.0, 5.0, d, False)
        self.assertEqual(resolve_zone(52.001, 5.0, [edge]), "not_home")
        wider = ("zone.edge", "Edge", 52.0, 5.0, d + 0.01, False)
        self.assertEqual(resolve_zone(52.001, 5.0, [wider]), "Edge")

    def test_outside_every_zone_is_not_home(self):
        self.assertEqual(resolve_zone(53.0, 6.0, [HOME, WORK]), "not_home")

    def test_no_zones_is_not_home(self):
        self.assertEqual(resolve_zone(52.0, 5.0, []), "not_home")

    def test_passive_zone_is_ignored(self):
        passive = ("zone.home", "Home", 52.0, 5.0, 100.0, True)
        self.assertEqual(resolve_zone(52.0, 5.0, [passive]), "not_home")

    def test_none_or_zero_zero_fix_is_none(self):
        self.assertIsNone(resolve_zone(None, 5.0, [HOME]))
        self.assertIsNone(resolve_zone(52.0, None, [HOME]))
        self.assertIsNone(resolve_zone(0, 0, [HOME]))


if __name__ == "__main__":
    unittest.main()
