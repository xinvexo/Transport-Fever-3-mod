import unittest
from pathlib import Path

from lupa import LuaRuntime


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
            (ROOT / "content/auto_signal/spacing_widget.lua").read_text()
        )
        self.commits = []
        self.param = self.lua.table_from({
            "scriptParam": self.lua.table_from({
                "name": "最小间距",
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
                         (50, 2000, 1, 50))
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
        self.assertEqual((spin.min, spin.max, spin.step), (50, 2000, 1))
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

    def test_external_value_updates_both_controls_in_either_mode(self):
        self.param.currentValue = 650
        row = self.render()
        self.assertEqual(row.children[1].value, 650)
        self.assertEqual(row.children[2].content.text, "650 米")
        row.children[2].onClick()
        self.param.currentValue = 425
        row = self.render()
        self.assertEqual(row.children[1].value, 425)
        self.assertEqual(row.children[2].value, 425)
        self.assertEqual(self.commits, [])

    def test_numeric_input_commits_whole_meters_within_the_range(self):
        self.render().children[2].onClick()
        spin = self.render().children[2]
        spin.onValueChange(375.6)
        spin.onValueChange(25)
        spin.onValueChange(2200)
        self.assertEqual(self.commits, [376, 50, 2000])

    def test_native_label_wrapper_receives_layout_preferences(self):
        on_hover = lambda value: None
        self.param.onHover = on_hover
        wrapper = self.widget.build(self.param)
        self.assertEqual(wrapper.name, "最小间距")
        self.assertTrue(wrapper.vertical)
        self.assertTrue(wrapper.addSpacer)
        self.assertIs(wrapper.onHover, on_hover)
        self.param.vertical = None
        self.assertEqual(self.widget.build(self.param).kind, "Recipe")


if __name__ == "__main__":
    unittest.main()
