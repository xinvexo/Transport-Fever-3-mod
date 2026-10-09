import unittest
from pathlib import Path

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class SpacingWidgetTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            local builtin = {
                type = { Orientation = { Horizontal = "horizontal" } }
            }
            for _, name in ipairs({"DoubleSpinBox", "Button", "TextView", "BoxLayout", "Slider"}) do
                builtin[name] = function(params)
                    params.kind = name
                    return params
                end
            end
            local stateSlots, stateIndex = {}, 0
            function beginRender() stateIndex = 0 end
            local react = {
                RegisterRecipe = function(name, render)
                    return function(params)
                        return { kind = "Recipe", name = name, params = params, render = render }
                    end
                end,
                useState = function(initial)
                    stateIndex = stateIndex + 1
                    if not stateSlots[stateIndex] then
                        stateSlots[stateIndex] = {
                            value = initial,
                            old = function(self) return self.value end,
                            set = function(self, value) self.value = value end,
                        }
                    end
                    return stateSlots[stateIndex]
                end,
            }
            local scriptParamUtil = {
                wrap = function(name, vertical, control, addSpacer, onHover)
                    return {
                        kind = "Wrapper", name = name, vertical = vertical,
                        control = control, addSpacer = addSpacer, onHover = onHover,
                    }
                end,
            }
            local modules = {
                ["::/gui/main/builtin.lua"] = builtin,
                ["::/gui/main/react.lua"] = react,
                ["::/gui/main/script_param_util.tl"] = scriptParamUtil,
            }
            function ug_require(path) return assert(modules[path], path) end
            api = {
                gui = { StyleSheet = { new = function() return {} end } },
                type = {
                    Vec2f = { new = function(x, y) return {x = x, y = y} end },
                    Vec4f = { new = function(x, y, z, w) return {x=x, y=y, z=z, w=w} end },
                },
            }
        """)
        self.widget = self.lua.execute(
            (ROOT / "content/auto_signal/spacing_widget.lua").read_text(encoding="utf-8")
        )
        self.commits = []
        self.param = self.lua.table_from({
            "scriptParam": self.lua.table_from({
                "name": "间距",
                "formatValueFn": lambda value: f"{int(value)} 米",
            }),
            "currentValue": 300,
            "vertical": True,
            "addSpacer": True,
            "disableGamepadNavigation": True,
        })

        def commit(value):
            self.commits.append(value)
            self.param.currentValue = value

        self.param.onValueChange = commit

    def render(self):
        outer = self.widget.build(self.param)
        recipe = outer.control if outer.kind == "Wrapper" else outer
        self.lua.globals().beginRender()
        return recipe.render(recipe.params)

    def test_slider_uses_integer_meters_and_updates_display(self):
        row = self.render()
        slider = row.children[1]
        self.assertEqual((slider.min, slider.max, slider.step, slider.pageStep),
                         (50, 800, 1, 50))
        self.assertEqual(slider.value, 300)
        slider.onValueChange(375)
        row = self.render()
        self.assertEqual(self.commits, [375])
        self.assertEqual(row.children[1].value, 375)
        self.assertEqual(row.children[2].content.text, "375 米")

    def test_click_edit_commit_and_exit_share_the_slider_value(self):
        self.render().children[2].onClick()
        spin = self.render().children[2]
        self.assertEqual(spin.kind, "DoubleSpinBox")
        self.assertTrue(spin.startInEditMode)
        self.assertEqual((spin.min, spin.step), (1, 1))
        self.assertGreater(spin.max, 2000)
        spin.onValueChange(375)
        row = self.render()
        self.assertEqual(row.children[1].value, 375)
        self.assertEqual(row.children[2].value, 375)
        row.children[2].onStopEditMode()
        display = self.render().children[2]
        self.assertEqual(display.kind, "Button")
        self.assertEqual(display.content.text, "375 米")
        self.assertEqual(self.commits, [375])

    def test_leaving_edit_mode_without_a_change_keeps_the_value(self):
        self.render().children[2].onClick()
        self.render().children[2].onStopEditMode()
        self.assertEqual(self.render().children[2].content.text, "300 米")
        self.assertEqual(self.commits, [])

    def test_numeric_input_accepts_positive_meters_outside_slider_range(self):
        self.render().children[2].onClick()
        spin = self.render().children[2]
        spin.onValueChange(375.6)
        spin.onValueChange(25)
        spin.onValueChange(2200)
        spin.onValueChange(0)
        self.assertEqual(self.commits, [376, 25, 2200, 1])

    def test_typed_value_survives_edit_toggle_and_clamped_slider_display(self):
        for value, thumb in ((25, 50), (1, 50), (1200, 800), (320, 320)):
            with self.subTest(value=value):
                self.render().children[2].onClick()
                self.render().children[2].onValueChange(value)
                row = self.render()
                self.assertEqual(row.children[1].value, thumb)
                self.assertEqual(row.children[2].value, value)
                row.children[2].onStopEditMode()
                row = self.render()
                self.assertEqual(row.children[2].content.text, f"{value} 米")
                self.assertEqual(self.param.currentValue, value)
        self.assertEqual(self.commits, [25, 1, 1200, 320])

    def test_nonfinite_input_is_ignored(self):
        self.render().children[2].onClick()
        spin = self.render().children[2]
        spin.onValueChange(float("inf"))
        spin.onValueChange(float("nan"))
        self.assertEqual(self.commits, [])
        self.assertEqual(self.param.currentValue, 300)

    def test_exact_large_integer_input_is_not_rounded_up(self):
        self.render().children[2].onClick()
        spin = self.render().children[2]
        for value in (2147483648, 4503599627370497, 2**53-1):
            with self.subTest(value=value):
                spin.onValueChange(value)
                self.assertEqual(self.commits[-1], value)


if __name__ == "__main__":
    unittest.main()
