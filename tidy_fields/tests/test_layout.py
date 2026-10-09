"""Layout geometry and saved-layout behavior under Lua 5.2."""

from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


def values(table):
    return {key: values(value) if hasattr(value, "items") else value for key, value in table.items()}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.layout = self.lua.execute((ROOT / "content/tidy_fields/layout.lua").read_text(encoding="utf-8"))

    def config(self, kind="farm_field", count=20):
        return self.lua.table_from({
            "type": kind,
            "alignToTerrain": True,
            "fields": [
                {"pos": [120 - i * 30, -180 + i * 40], "size": [60, 120],
                 "road": [0, 1, 0, 0], "type": i % 3}
                for i in range(count)
            ],
        }, recursive=True)

    def params(self, config, active=(2, 7, 11, 18), mode="all"):
        modules = self.lua.table_from({slot: {"name": "field.module"} for slot in active}, recursive=True)
        return self.lua.table_from({
            "xinTidyFields": True,
            "xinTidyLayout": mode,
            "xinTidyFieldOrder": self.layout.makeOrder(modules, len(config.fields)),
            "modules": modules,
            "seed": 42,
            "industrySize": 4,
            "sizeFactor": 2,
            "disableStation": True,
        })

    def test_sparse_active_slots_are_placed_before_future_slots(self):
        config = self.config()
        params = self.params(config)
        order = list(params.xinTidyFieldOrder.values())
        self.assertEqual(order[:4], [2, 7, 11, 18])
        self.assertEqual(order[4:], [i for i in range(1, 21) if i not in (2, 7, 11, 18)])
        fields = self.layout.rearrange(config, params).fields
        dense = self.layout.rearrange(config, self.params(config, active=range(1, 5))).fields
        for index, slot in enumerate(order[:4], 1):
            self.assertEqual(values(fields[slot].pos), values(dense[index].pos))

    def test_fifteen_layouts_use_selected_sides_and_keep_the_road_clear(self):
        sites = (
            ("farm_field", -60, 60, -90, 90, -100.5, 20),
            ("livestock_field", -81.1353, 68.8647, -60, 60, -72.5, 20),
            ("cotton_field", -60, 60, -80, 60, -90.5, 21),
            ("rubber_field", -90, 90, -50, 50, -61.3, 23),
            ("forest_field", -70, 60, -60, 60, -70.5, 20),
        )
        modes = {
            "left": ("left",), "right": ("right",), "front": ("front",), "back": ("back",),
            "left_right": ("left", "right"), "left_front": ("left", "front"),
            "left_back": ("left", "back"), "right_back": ("right", "back"),
            "right_front": ("right", "front"), "front_back": ("front", "back"),
            "left_right_front": ("left", "right", "front"),
            "left_right_back": ("left", "right", "back"),
            "left_front_back": ("left", "front", "back"),
            "right_front_back": ("right", "front", "back"),
            "all": ("left", "right", "front", "back"),
        }
        for kind, left, right, front, rear, road_y, count in sites:
            for mode, sides in modes.items():
                with self.subTest(kind=kind, mode=mode):
                    config = self.config(kind, count)
                    params = self.params(config, active=range(1, 14), mode=mode)
                    fields = self.layout.rearrange(config, params).fields
                    self.assertEqual(len(fields), count)
                    touches_factory = False
                    ordered = list(params.xinTidyFieldOrder.values())
                    for slot in ordered:
                        field = fields[slot]
                        self.assertTrue(all(0 < size <= 80 for size in field.size.values()))
                        self.assertEqual(list(field.road.values()), [0, 0, 0, 0])
                        x, y = field.pos[1], field.pos[2]
                        half_x, half_y = field.size[1] / 2, field.size[2] / 2
                        in_front = y + half_y + 4 <= road_y - 8 + 1e-9
                        allowed = {
                            "left": not in_front and x - half_x >= right - 1e-9,
                            "right": not in_front and x + half_x <= left + 1e-9,
                            "front": in_front,
                            "back": not in_front and y - half_y >= rear - 1e-9,
                        }
                        self.assertTrue(any(allowed[side] for side in sides))
                        if not in_front:
                            self.assertGreaterEqual(y - half_y - 4, road_y + 4 - 1e-9)
                        if slot in params.modules:
                            touches_factory |= any((
                                abs(x - half_x - right) < 1e-9,
                                abs(x + half_x - left) < 1e-9,
                                abs(y - half_y - rear) < 1e-9,
                            ))
                    if "front" not in sides:
                        self.assertTrue(touches_factory)
                    for i in range(1, count + 1):
                        for j in range(i + 1, count + 1):
                            a, b = fields[i], fields[j]
                            self.assertTrue(abs(a.pos[1] - b.pos[1]) >= (a.size[1] + b.size[1]) / 2 - 1e-9
                                            or abs(a.pos[2] - b.pos[2]) >= (a.size[2] + b.size[2]) / 2 - 1e-9)

    def test_selected_sides_form_compact_connected_layouts(self):
        roads = {"farm_field": -100.5, "livestock_field": -72.5,
                 "cotton_field": -90.5, "rubber_field": -61.3, "forest_field": -70.5}
        for kind in ("farm_field", "livestock_field", "cotton_field", "rubber_field", "forest_field"):
            for mode in ("left", "right", "front", "back"):
                with self.subTest(kind=kind, mode=mode):
                    config = self.config(kind)
                    params = self.params(config, active=range(1, 7), mode=mode)
                    fields = self.layout.rearrange(config, params).fields
                    xs = {fields[slot].pos[1] for slot in params.modules}
                    ys = {fields[slot].pos[2] for slot in params.modules}
                    if mode == "front":
                        self.assertAlmostEqual(max(ys) + 44, roads[kind] - 8)
                    if mode in ("front", "back"):
                        nearest_y = max(ys) if mode == "front" else min(ys)
                        nearest = sorted(
                            (fields[slot].pos[1] - fields[slot].size[1] / 2,
                             fields[slot].pos[1] + fields[slot].size[1] / 2)
                            for slot in params.modules if abs(fields[slot].pos[2] - nearest_y) < 1e-9
                        )
                        for previous, following in zip(nearest, nearest[1:]):
                            self.assertAlmostEqual(previous[1], following[0])
                    self.assertGreater(len(xs), 1)
                    self.assertGreater(len(ys), 1)
                    self.assertLessEqual(max(xs) - min(xs), (4 if mode in ("front", "back") else 3) * 80 + 1e-9)
                    self.assertLessEqual(max(ys) - min(ys), 3 * 80 + 1e-9)
                    axis = 1 if mode in ("left", "right") else 2
                    root_layer = (max if mode in ("right", "front") else min)(xs if axis == 1 else ys)
                    for slot in params.modules:
                        a = fields[slot]
                        if mode not in ("front", "back") and abs(a.pos[axis] - root_layer) < 1e-9:
                            continue
                        self.assertTrue(any(
                            (abs(abs(a.pos[1] - fields[other].pos[1]) - (a.size[1] + fields[other].size[1]) / 2) < 1e-9
                             and abs(a.pos[2] - fields[other].pos[2]) < 1e-9)
                            or (abs(abs(a.pos[2] - fields[other].pos[2]) - (a.size[2] + fields[other].size[2]) / 2) < 1e-9
                                and abs(a.pos[1] - fields[other].pos[1]) < 1e-9)
                            for other in params.modules if other != slot
                        ))

        sites = (
            ("farm_field", -60, 60, -90, 90, -100.5),
            ("livestock_field", -81.1353, 68.8647, -60, 60, -72.5),
            ("cotton_field", -60, 60, -80, 60, -90.5),
            ("rubber_field", -90, 90, -50, 50, -61.3),
            ("forest_field", -70, 60, -60, 60, -70.5),
        )

        def connected(rectangles):
            def adjacent(a, b):
                return ((abs(a[1] - b[0]) < 1e-9 or abs(b[1] - a[0]) < 1e-9)
                        and min(a[3], b[3]) - max(a[2], b[2]) > 1e-9
                        or (abs(a[3] - b[2]) < 1e-9 or abs(b[3] - a[2]) < 1e-9)
                        and min(a[1], b[1]) - max(a[0], b[0]) > 1e-9)
            reached = {0}
            while True:
                additions = {i for i, rect in enumerate(rectangles)
                             if i not in reached and any(adjacent(rect, rectangles[j]) for j in reached)}
                if not additions:
                    return len(reached) == len(rectangles)
                reached.update(additions)

        for kind, left, right, front, rear, road_y in sites:
            for active_count in (5, 8, 9, 13):
                with self.subTest(kind=kind, active=active_count, mode="left_right_front"):
                    config = self.config(kind)
                    params = self.params(config, active=range(1, active_count + 1), mode="left_right_front")
                    fields = self.layout.rearrange(config, params).fields
                    front_fields, factory_fields = [], [(left, right, front, rear)]
                    left_count, right_count = 0, 0
                    for slot in params.modules:
                        field = fields[slot]
                        x, y, hx, hy = field.pos[1], field.pos[2], field.size[1] / 2, field.size[2] / 2
                        rect = (x - hx, x + hx, y - hy, y + hy)
                        if y + hy + 4 <= road_y - 8 + 1e-9:
                            front_fields.append(rect)
                        else:
                            factory_fields.append(rect)
                            if x - hx >= right - 1e-9:
                                left_count += 1
                            else:
                                self.assertLessEqual(x + hx, left + 1e-9)
                                right_count += 1
                    self.assertEqual(len(front_fields) + len(factory_fields) - 1, active_count)
                    if front_fields:
                        self.assertTrue(connected(front_fields))
                    self.assertTrue(connected(factory_fields))
                    if kind == "livestock_field" and active_count == 8:
                        self.assertEqual((left_count, right_count, len(front_fields)), (2, 2, 4))
                        self.assertEqual(len({rect[3] for rect in front_fields}), 1)
                        self.assertTrue(all(rect[3] <= rear + 1e-9 for rect in factory_fields[1:]))
                        ordered_front = sorted(front_fields)
                        for previous, following in zip(ordered_front, ordered_front[1:]):
                            self.assertAlmostEqual(previous[1], following[0])

    def test_saved_order_keeps_existing_fields_still_during_growth(self):
        config = self.config()
        params = self.params(config, mode="left_right")
        fields, reason, slots = self.layout.plan(config, params, self.lua.eval("function(field) return field.pos[1] > 60 end"))
        self.assertIsNone(reason)
        params.xinTidyFieldLayout, params.xinTidyFieldSlots = fields, slots
        before = self.layout.rearrange(config, params)
        self.assertEqual(values(before.fields), values(params.xinTidyFieldLayout))
        params.modules[1] = self.lua.table_from({"name": "field.module"})
        after = self.layout.rearrange(config, params)
        for slot in params.modules.keys():
            self.assertEqual(values(before.fields[slot].pos), values(after.fields[slot].pos))

    def test_layout_preserves_shared_configuration_and_module_state(self):
        config = self.config()
        params = self.params(config)
        config_before, params_before = values(config), values(params)
        result = self.layout.rearrange(config, params)
        self.assertEqual(values(config), config_before)
        self.assertEqual(values(params), params_before)
        self.assertEqual(result.type, config.type)
        self.assertEqual(result.alignToTerrain, config.alignToTerrain)
        for slot in range(1, len(config.fields) + 1):
            self.assertEqual(result.fields[slot].type, config.fields[slot].type)
        result.fields[2].pos[1] = 999
        result.fields[2].size[1] = 1
        self.assertEqual(values(config), config_before)

    def test_wrapper_passes_original_result_and_all_other_parameters(self):
        self.lua.execute("""
            seen = {}
            originalResult = { production = 37 }
            update = function(capture, params)
                seen.capture, seen.params = capture, params
                return originalResult, 9
            end
        """)
        wrapped = self.layout.wrap(self.lua.globals().update)
        config = self.config()
        capture = self.lua.table_from({"fieldConfig": config, "stockListConfig": self.lua.table_from({"capacity": 100})})
        params = self.params(config)
        result, extra = wrapped(capture, params)
        same = self.lua.eval("rawequal")
        self.assertTrue(same(result, self.lua.globals().originalResult))
        self.assertEqual(extra, 9)
        seen = self.lua.globals().seen
        self.assertTrue(same(seen.params, params))
        self.assertTrue(same(seen.capture.stockListConfig, capture.stockListConfig))
        self.assertFalse(same(seen.capture.fieldConfig, config))
        params.xinTidyFields = False
        wrapped(capture, params)
        self.assertTrue(same(seen.capture, capture))

if __name__ == "__main__":
    unittest.main()
