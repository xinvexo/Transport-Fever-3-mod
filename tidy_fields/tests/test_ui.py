import json
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class TidyFieldsUiTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.translations = json.loads((ROOT / 'strings.json').read_text(encoding='utf-8'))
        self.lua.globals()._ = self.translations['zh_CN'].__getitem__
        self.lua.execute("""
            local builtin = {type = {Orientation = {Vertical = 'vertical', Horizontal = 'horizontal'}}}
            for _, name in ipairs({'BoxLayout', 'Button', 'TextView', 'ToggleButton', 'Component'}) do
                builtin[name] = function(params) params.kind = name; return params end
            end
            local states, stateIndex = {}, 0
            function beginRender() stateIndex = 0 end
            local react = {
                RegisterPluginRecipe = function(extension, name, render) return render end,
                useState = function(initial)
                    stateIndex = stateIndex + 1
                    if not states[stateIndex] then
                        states[stateIndex] = {
                            value = initial,
                            old = function(self) return self.value end,
                            set = function(self, value)
                                assert(not expired, 'Cannot write expired React state')
                                self.value = value
                            end,
                            hasExpired = function() return expired == true end,
                        }
                    end
                    return states[stateIndex]
                end,
            }
            construction = {params = {}}
            attempts, commands = {}, {}
            proposals = {
                getTarget = function() return 10, construction end,
                make = function(entity, mode)
                    attempts[#attempts + 1] = {entity = entity, mode = mode}
                    return {mode = mode}, {player = 7}
                end,
            }
            local modules = {
                ['::/gui/main/builtin.lua'] = builtin,
                ['::/gui/main/react.lua'] = react,
                ['::/gui/entity_window/industry/industry_eow.script.tl'] = {IndustryEowExtensionPoint = {}},
                ['xin_tidy_fields_1::/tidy_fields/proposal.lua'] = proposals,
                ['::/scripts/table_util.tl'] = {},
                ['xin_tidy_fields_1::/tidy_fields/layout.lua'] = {},
            }
            function ug_require(name) return assert(modules[name], name) end
            log = {warning = function() end}
            local ninePatches = setmetatable({}, {__mode = 'k'})
            api = {
                gui = {
                    NinePatch = {new = function()
                        local patch = {}; ninePatches[patch] = true; return patch
                    end},
                    StyleSheet = {new = function()
                        return setmetatable({}, {__newindex = function(style, key, value)
                            if key == 'backgroundImage1' or key == 'borderImage' then
                                assert(ninePatches[value], 'Expected a native NinePatch')
                            end
                            rawset(style, key, value)
                        end})
                    end},
                },
                type = {
                    Vec2f = {new = function(x, y) return {x = x, y = y} end},
                    Vec4f = {new = function(x, y, z, w) return {x = x, y = y, z = z, w = w} end},
                },
                cmd = {
                makeWorldBuildProposalCmd = function(candidate, context, ignoreErrors, playerInitiated)
                    return {candidate = candidate, context = context,
                        ignoreErrors = ignoreErrors, playerInitiated = playerInitiated}
                end,
                sendCommand = function(command, callback)
                    commands[#commands + 1] = command
                    pendingCallback = callback
                end,
            }}
            function find(node, kind, tag)
                if type(node) ~= 'table' then return nil end
                if node.kind == kind and (not tag or node.meta and node.meta.tag == tag) then return node end
                for _, child in ipairs(node.children or {}) do
                    local result = find(child, kind, tag)
                    if result then return result end
                end
                return find(node.content, kind, tag) or find(node.child, kind, tag)
                    or find(node.layout, kind, tag)
            end
        """)
        proposal = self.lua.execute((ROOT / "content/tidy_fields/proposal.lua").read_text(encoding="utf-8"))
        self.lua.globals().proposals.describeFailure = proposal.describeFailure
        self.lua.execute((ROOT / "content/tidy_fields/ui.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("ui = data(); uiParams = {entityId = 11, ownershipState = 'Own'}")

    def render(self):
        self.lua.execute("beginRender(); node = ui.TidyFieldsPlugin(uiParams)")

    def element(self, kind, tag=None):
        return self.lua.globals().find(self.lua.globals().node, kind, tag)

    def direction_button(self, side):
        return self.element("ToggleButton", f"industryWindow.tidyFields.{side}")

    def select_sides(self, sides):
        for side in ("front", "back", "left", "right"):
            self.direction_button(side).onValueChange(1 if side in sides else 0)
            self.render()

    def test_saved_layout_and_success_allow_another_tidy(self):
        self.lua.execute("construction.params = {xinTidyFields = true, xinTidyLayout = 'left_back'}")
        self.render()
        for side in ("front", "back", "left", "right"):
            self.assertEqual(self.direction_button(side).value, 1 if side in ("left", "back") else 0)
        button = self.element("Button")
        self.assertTrue(button.meta.enabled)
        button.onClick()
        self.render()
        self.assertFalse(self.element("Button").meta.enabled)
        for side in ("front", "back", "left", "right"):
            self.assertFalse(self.direction_button(side).meta.enabled)
        self.element("Button").onClick()
        self.assertEqual(self.lua.eval("#commands"), 1)
        self.lua.execute("pendingCallback({}, true)")
        self.render()
        self.assertTrue(self.element("Button").meta.enabled)
        self.direction_button("right").onValueChange(1)
        self.render()
        self.element("Button").onClick()
        self.assertEqual(self.lua.eval("#commands"), 2)
        self.assertEqual(self.lua.eval("commands[2].candidate.mode"), "left_right_back")
        self.lua.execute("pendingCallback({}, true)")
        self.render()
        self.select_sides(())
        self.assertFalse(self.element("Button").meta.enabled)
        self.assertTrue(self.direction_button("front").meta.enabled)

    def test_failure_detail_leaves_layout_selectable_for_retry(self):
        cases = (
            ({"errorState": {"messages": ["road connection mismatch"]}}, "无法整理：road connection mismatch"),
            ({"collisionInfo": {"collisionEntities": [40], "buildingEntities": [], "removableModules": []}},
             "原版施工检查未通过，具体原因请查看游戏日志。"),
            ({}, "原版施工检查未通过，具体原因请查看游戏日志。"),
        )
        for details, expected in cases:
            with self.subTest(details=details):
                self.setUp()
                self.render()
                self.element("Button").onClick()
                self.lua.globals().pendingCallback(self.lua.table_from({"resultProposalData": details}, recursive=True), False)
                self.render()
                self.assertTrue(self.element("Button").meta.enabled)
                self.assertEqual(self.lua.eval("#commands"), 1)
                self.assertEqual(self.element("TextView", "industryWindow.tidyFields.result").text, expected)
                self.select_sides(("back",))
                self.element("Button").onClick()
                self.assertEqual(self.lua.eval("#commands"), 2)
                self.assertEqual(self.lua.eval("commands[#commands].candidate.mode"), "back")

    def test_command_creation_and_submission_errors_allow_retry(self):
        for failing_api in ("makeWorldBuildProposalCmd", "sendCommand"):
            with self.subTest(failing_api=failing_api):
                self.setUp()
                self.render()
                self.lua.execute(f"""
                    originalCommandFunction = api.cmd.{failing_api}
                    api.cmd.{failing_api} = function() error('native command unavailable') end
                """)
                self.element("Button").onClick()
                self.render()
                self.assertTrue(self.element("Button").meta.enabled)
                self.assertEqual(self.lua.eval("#commands"), 0)
                self.assertEqual(self.element("TextView", "industryWindow.tidyFields.result").text,
                                 self.translations["zh_CN"]["Could not prepare a plot layout."])
                self.lua.execute(f"api.cmd.{failing_api} = originalCommandFunction")
                self.element("Button").onClick()
                self.assertEqual(self.lua.eval("#commands"), 1)

    def test_result_after_industry_window_closes_does_not_access_expired_state(self):
        self.render()
        self.element("Button").onClick()
        self.lua.execute("""
            expired = true
            proposals.describeFailure = function() error('Closed window should ignore the result') end
            pendingCallback({}, false)
        """)


if __name__ == "__main__":
    unittest.main()
