"""Check the fixed-distance rule independently of game geometry."""
from pathlib import Path
import random
import unittest
from lupa.lua52 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class SpacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.spacing = cls.lua.execute(
            (ROOT / "content/auto_signal/spacing.lua").read_text(encoding="utf-8")
        )

    def plan(self, length, gap, reversed=False, clearance=0, maximum=1000, blocked=None):
        exclusions = self.lua.table_from(blocked or [], recursive=True)
        result = self.spacing.plan(length, gap, reversed, clearance, maximum, exclusions)
        if isinstance(result, tuple):
            return result
        return [result[i] for i in range(1, len(result)+1)]

    def test_user_1050_meter_examples_anchor_at_forward_end(self):
        self.assertEqual(self.plan(1050, 300), [150, 450, 750, 1050])
        self.assertEqual(self.plan(1050, 200), [50, 250, 450, 650, 850, 1050])

    def test_reverse_direction_mirrors_the_positions(self):
        forward = self.plan(1050, 300)
        reverse = self.plan(1050, 300, True)
        self.assertEqual(reverse, [0, 300, 600, 900])
        self.assertEqual(reverse, [1050-p for p in forward[::-1]])

    def test_short_section_keeps_one_at_forward_end_not_center(self):
        self.assertEqual(self.plan(100, 300, clearance=1), [99])
        self.assertEqual(self.plan(100, 300, True, clearance=1), [1])
        self.assertEqual(self.plan(2, 300, clearance=1), [1])

    def test_exact_multiple_does_not_add_a_duplicate(self):
        self.assertEqual(self.plan(900, 300), [0, 300, 600, 900])

    def test_small_and_large_typed_spacing_is_not_clamped(self):
        self.assertEqual(self.plan(4, 1), [0, 1, 2, 3, 4])
        self.assertEqual(self.plan(5000, 1200), [200, 1400, 2600, 3800, 5000])
        self.assertEqual(self.plan(1050, 2**53-1), [1050])

    def test_endpoint_setback_moves_the_anchor_without_changing_gap(self):
        self.assertEqual(self.plan(1050, 300, clearance=1),
                         [149, 449, 749, 1049])

    def test_no_room_or_over_limit_layout_is_rejected(self):
        self.assertIsNone(self.plan(1.9, 300, clearance=1)[0])
        result, reason = self.plan(1050, 300, maximum=3)
        self.assertIsNone(result)
        self.assertIn("count limit", reason)

    def test_invalid_spacing_is_rejected(self):
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(Exception):
                self.plan(100, value)

    def test_blocked_target_moves_then_restarts_spacing_from_actual_light(self):
        self.assertEqual(self.plan(1050, 300, clearance=1, blocked=[(739, 759)]),
                         [139, 439, 739, 1049])

    def test_reverse_direction_uses_the_other_side_of_the_forbidden_range(self):
        self.assertEqual(self.plan(1050, 300, True, clearance=1, blocked=[(291, 311)]),
                         [1, 311, 611, 911])

    def test_crossing_between_targets_does_not_change_the_distance_grid(self):
        self.assertEqual(self.plan(1050, 300, clearance=1, blocked=[(600, 650)]),
                         [149, 449, 749, 1049])

    def test_overlapping_and_touching_ranges_do_not_leave_false_free_points(self):
        ranges = [(749, 760), (740, 749), (720, 745)]
        self.assertEqual(self.plan(1050, 300, clearance=1, blocked=ranges),
                         [120, 420, 720, 1049])

    def test_multiple_crossings_continue_from_each_shifted_light(self):
        self.assertEqual(self.plan(1050, 300, clearance=1, blocked=[(739, 759), (425, 445)]),
                         [125, 425, 739, 1049])

    def test_blocked_first_light_moves_but_does_not_split_the_section(self):
        self.assertEqual(self.plan(1050, 300, clearance=1, blocked=[(1030, 1070)]),
                         [130, 430, 730, 1030])

    def test_fully_blocked_section_leaves_original_lights_untouched(self):
        result, reason = self.plan(1050, 300, clearance=1, blocked=[(-5, 1100)])
        self.assertIsNone(result)
        self.assertIn("no room", reason)

    def test_fractional_lengths_keep_exact_gap_and_anchor(self):
        rng = random.Random(5813)
        for _ in range(300):
            clearance = rng.random()*20
            length = 2*clearance+rng.random()*5000
            gap = rng.randint(10, 1200)
            for reversed in (False, True):
                points = self.plan(length, gap, reversed, clearance)
                anchor = clearance if reversed else length-clearance
                self.assertAlmostEqual(points[0] if reversed else points[-1], anchor)
                for a, b in zip(points, points[1:]):
                    self.assertAlmostEqual(b-a, gap)
                self.assertGreaterEqual(points[0]+1e-7, clearance)
                self.assertLessEqual(points[-1]-1e-7, length-clearance)
                remainder = length-clearance-points[-1] if reversed else points[0]-clearance
                self.assertLess(remainder, gap+1e-7)


if __name__ == "__main__":
    unittest.main()
