from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime, lua_type


ROOT = Path(__file__).resolve().parents[1]
CARGO, PASSENGER, TRACK, ROOF, ADDON = 6400000, 7400000, 8400000, 10400000, 10800000


def slot(base, i, j):
    return base + 1000 * i + 10 * j


def module(name, variant=1):
    return {"name": name, "metadata": {"variant": variant}, "enabled": True}


class RowTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.rows = self.lua.execute((ROOT / "content/station_rows/rows.lua").read_text(encoding="utf-8"))

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def plain(self, value):
        if lua_type(value) != "table":
            return value
        return {key: self.plain(item) for key, item in value.items()}

    def apply(self, modules, change):
        params = self.table({
            "modules": modules,
            "trackType": 4,
            "catenary": True,
            "seed": 123,
            "custom": {"height": 3, "style": "brick"},
        })
        result = self.rows.apply(params, self.table(change))
        self.assertTrue(self.lua.eval("rawequal")(result, params))
        self.assertEqual(params.trackType, 4)
        self.assertTrue(params.catenary)
        self.assertEqual(params.seed, 123)
        self.assertEqual(self.plain(params.custom), {"height": 3, "style": "brick"})
        return self.plain(params.modules)

    def test_shift_cargo_platform_follows_existing_four_module_station_length(self):
        modules = {
            slot(base, i, j): module(name)
            for base, i, name in ((TRACK, 0, "rail"), (PASSENGER, 1, "passenger"))
            for j in range(-2, 2)
        }
        cargo = module("cargo", 7)
        result = self.apply(modules, {
            "added": True, "slotId": slot(CARGO, -2, 1), "module": cargo,
        })
        expected = dict(modules)
        expected.update({slot(CARGO, -2, j): cargo for j in range(-2, 2)})
        self.assertEqual(result, expected)

    def test_negative_coordinates_and_outer_columns_include_clicked_position(self):
        for base, i, j in (
            (CARGO, -8, -10),
            (PASSENGER, -2, -3),
            (TRACK, 16, 10),
        ):
            with self.subTest(base=base, i=i, j=j):
                modules = {slot(TRACK, 0, p): module("rail") for p in (-2, 1)}
                added = module("selected", 2)
                result = self.apply(modules, {
                    "added": True, "slotId": slot(base, i, j), "module": added,
                })
                expected = dict(modules)
                expected.update({
                    slot(base, i, p): added for p in range(min(-2, j), max(1, j) + 1)
                })
                self.assertEqual(result, expected)

    def test_row_add_fills_gaps_and_keeps_existing_platforms(self):
        modules = {slot(TRACK, 0, j): module("rail") for j in range(-3, 3)}
        modules.update({slot(PASSENGER, 1, j): module("old", 1) for j in (-3, 1)})
        modules[slot(PASSENGER, 2, 0)] = module("neighbour", 9)
        modules[13000000] = module("building")
        selected = module("new", 5)
        result = self.apply(modules, {
            "added": True, "slotId": slot(PASSENGER, 1, 0), "module": selected,
        })
        expected = dict(modules)
        expected.update({
            slot(PASSENGER, 1, j): selected for j in range(-3, 3) if j not in (-3, 1)
        })
        self.assertEqual(result, expected)

    def test_track_and_passenger_rows_fill_only_unoccupied_cells(self):
        for base, other in ((TRACK, PASSENGER), (PASSENGER, TRACK)):
            with self.subTest(base=base):
                modules = {slot(TRACK, 3, j): module("rail") for j in range(-2, 3)}
                modules.update({
                    slot(other, 0, -2): module("existing structure"),
                    slot(CARGO, -1, -1): module("cargo left"),
                    slot(CARGO, 0, 0): module("cargo right"),
                    slot(base, 0, 1): module("existing row module", 9),
                    slot(CARGO, 1, 2): module("adjacent cargo"),
                })
                selected = module("selected")
                result = self.apply(modules, {
                    "added": True, "slotId": slot(base, 0, 2), "module": selected,
                })
                expected = dict(modules)
                expected[slot(base, 0, 2)] = selected
                self.assertEqual(result, expected)

    def test_cargo_row_checks_both_cells_and_overlapping_cargo_columns(self):
        modules = {slot(TRACK, 4, j): module("rail") for j in range(-3, 4)}
        modules.update({
            slot(TRACK, 0, -3): module("left cell track"),
            slot(PASSENGER, 1, -2): module("right cell platform"),
            slot(CARGO, -1, -1): module("cargo across left cell"),
            slot(CARGO, 1, 0): module("cargo across right cell"),
            slot(CARGO, 0, 1): module("existing cargo", 9),
            slot(CARGO, 2, 2): module("adjacent cargo"),
        })
        selected = module("selected cargo")
        result = self.apply(modules, {
            "added": True, "slotId": slot(CARGO, 0, 3), "module": selected,
        })
        expected = dict(modules)
        expected.update({slot(CARGO, 0, j): selected for j in (2, 3)})
        self.assertEqual(result, expected)

    def test_row_delete_crosses_gaps_and_removes_platform_attachments(self):
        for base in (CARGO, PASSENGER):
            with self.subTest(base=base):
                positions = (-10, -2, 2, 10)
                modules = {
                    slot(kind, i, j): module(str(kind))
                    for kind in (base, TRACK, ROOF, ADDON)
                    for i in (-2, -1)
                    for j in positions
                }
                modules[13000000] = module("building")
                result = self.apply(modules, {
                    "added": False, "slotId": slot(base, -2, 2),
                })
                expected = dict(modules)
                for kind in (base, ROOF, ADDON):
                    for j in positions:
                        expected.pop(slot(kind, -2, j))
                self.assertEqual(result, expected)

    def test_roof_and_addon_fill_only_existing_passenger_platform_positions(self):
        for base in (ROOF, ADDON):
            with self.subTest(base=base):
                positions = (-4, -1, 2)
                modules = {slot(PASSENGER, -2, j): module("platform") for j in positions}
                modules.update({slot(TRACK, -2, j): module("rail") for j in range(-5, 5)})
                modules[slot(PASSENGER, -1, 0)] = module("other platform")
                modules[slot(CARGO, -2, 3)] = module("cargo")
                modules[slot(base, -2, -4)] = module("old attachment")
                selected = module("selected attachment", 3)
                result = self.apply(modules, {
                    "added": True, "slotId": slot(base, -2, -1), "module": selected,
                })
                expected = dict(modules)
                expected.update({slot(base, -2, j): selected for j in (-1, 2)})
                self.assertEqual(result, expected)

    def test_track_and_roof_deletion_keep_other_module_types(self):
        for base in (TRACK, ROOF, ADDON):
            with self.subTest(base=base):
                modules = {
                    slot(kind, i, j): module(str(kind))
                    for kind in (TRACK, PASSENGER, ROOF, ADDON)
                    for i in (0, 1)
                    for j in (-2, 0, 2)
                }
                result = self.apply(modules, {
                    "added": False, "slotId": slot(base, 0, 0),
                })
                expected = dict(modules)
                for j in (-2, 0, 2):
                    expected.pop(slot(base, 0, j))
                self.assertEqual(result, expected)



if __name__ == "__main__":
    unittest.main()
