import unittest
from pathlib import Path

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class SpacingUiEntryTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            calls = { definitions = 0, native = 0, custom = 0, plugins = 0 }
            local function formatter()
                return function(value) return tostring(value) .. " m" end
            end
            constructionUtil = {
                getConstructionDefinitions = function()
                    calls.definitions = calls.definitions + 1
                    return {
                        { params = {
                            { key = "oneWay", name = "One-Way" },
                            { key = "asEnabled", name = "Auto placement" },
                            { key = "asMinimumSpacing", name = "最小间距", formatValueFn = formatter() },
                        } },
                        { params = {
                            { key = "otherSpacing", name = "最小间距", formatValueFn = formatter() },
                        } },
                        { params = {
                            { key = "asMinimumSpacing", name = "Other construction", formatValueFn = formatter() },
                        } },
                        { params = {
                            { key = "asEnabled" },
                            { key = "asMinimumSpacing" },
                        } },
                    }
                end,
            }
            scriptParamUtil = {
                buildScriptParamCompSimple = function(param)
                    calls.native = calls.native + 1
                    return { kind = "native", value = param.currentValue }
                end,
            }
            local spacingWidget = {
                build = function(param)
                    calls.custom = calls.custom + 1
                    return { kind = "custom", value = param.currentValue, onValueChange = param.onValueChange }
                end,
            }
            extension = { id = "::ModEntryPointExtension" }
            local react = {
                RegisterPluginRecipe = function(point, name, recipe)
                    calls.plugins = calls.plugins + 1
                    plugin = { point = point, name = name }
                    return recipe
                end,
            }
            local modules = {
                ["::/gui/main/react.lua"] = react,
                ["::/gui/main/mod_entry_point.tl"] = { ModEntryPointExtension = extension },
                ["::/gui/construction/construction_react_util.tl"] = constructionUtil,
                ["::/gui/main/script_param_util.tl"] = scriptParamUtil,
                ["xin_auto_signal_1::/auto_signal/spacing_widget.lua"] = spacingWidget,
            }
            function ug_require(path) return assert(modules[path], path) end
        """)
        self.lua.execute(
            (ROOT / "content/auto_signal/ui_entry.script.lua").read_text(encoding="utf-8")
        )
        self.entry = self.lua.globals().data()
        self.construction = self.lua.globals().constructionUtil
        self.params_ui = self.lua.globals().scriptParamUtil
        self.calls = self.lua.globals().calls

    def control(self, source_param, value=375, on_change=None):
        # The native ConstructionParam deliberately copies only the display fields.
        display_param = self.lua.table_from({
            "name": source_param.name,
            "formatValueFn": source_param.formatValueFn,
        })
        return self.params_ui.buildScriptParamCompSimple(self.lua.table_from({
            "scriptParam": display_param,
            "currentValue": value,
            "onValueChange": on_change,
        }))

    def test_signal_spacing_routes_without_a_key_in_the_control_params(self):
        definitions = self.construction.getConstructionDefinitions()
        committed = []
        control = self.control(definitions[1].params[3], on_change=committed.append)
        self.assertEqual(control.kind, "custom")
        self.assertEqual(control.value, 375)
        control.onValueChange(425)
        self.assertEqual(committed, [425])

    def test_other_construction_controls_use_the_native_builder(self):
        definitions = self.construction.getConstructionDefinitions()
        for param in (definitions[1].params[1], definitions[2].params[1],
                      definitions[3].params[1], definitions[4].params[2]):
            self.assertEqual(self.control(param).kind, "native")
        self.assertEqual(self.calls.native, 4)

    def test_rebuilt_definitions_are_marked_for_the_custom_control(self):
        first = self.construction.getConstructionDefinitions()
        second = self.construction.getConstructionDefinitions()
        self.assertEqual(self.control(first[1].params[3]).kind, "custom")
        self.assertEqual(self.control(second[1].params[3]).kind, "custom")
        self.assertEqual(self.calls.definitions, 2)

    def test_entry_render_has_no_repeated_hook_work(self):
        for _ in range(3):
            self.assertIsNone(self.entry.entry())
        definitions = self.construction.getConstructionDefinitions()
        self.assertEqual(self.control(definitions[1].params[3]).kind, "custom")
        self.assertEqual(self.calls.definitions, 1)
        self.assertEqual(self.calls.custom, 1)
        self.assertEqual(self.calls.plugins, 1)

    def test_resource_points_to_the_registered_gui_entry(self):
        self.lua.execute((ROOT / "content/auto_signal/ui_entry.res.lua").read_text(encoding="utf-8"))
        resource = self.lua.globals().data()
        self.assertEqual(resource.type, "react-plugin ::ModEntryPointExtension")
        self.assertEqual(resource.data.filePath,
                         "xin_auto_signal_1::/auto_signal/ui_entry.script@entry")
        self.assertEqual(self.lua.globals().plugin.point.id, "::ModEntryPointExtension")


if __name__ == "__main__":
    unittest.main()
