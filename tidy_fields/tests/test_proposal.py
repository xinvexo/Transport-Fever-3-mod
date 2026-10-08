import json
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.translations = json.loads((ROOT / 'strings.json').read_text(encoding='utf-8'))
        self.lua.globals()._ = self.translations['zh_CN'].__getitem__
        self.lua.execute("""
            function copy(value)
              if type(value) ~= 'table' then return value end
              local result = {}
              for k, v in pairs(value) do result[k] = copy(v) end
              return result
            end
            construction = {
              fileName = '::/industries/farm/farm.con',
              transf = {100, 200, 0, transformPosition = function(self, point)
                return {x = self[1] + point.x, y = self[2] + point.y, z = self[3] + point.z}
              end},
              params = {seed = 123, year = 1950, modules = {
                [2] = {name = 'field.module', variant = 1},
                [8] = {name = 'field.module', variant = 2},
              }},
            }
            owner = nil
            samples, nativeRequests = {}, {}
            log = {warning = function() end}
            api = {
              type = {
                ComponentType = {CONSTRUCTION = 1, PLAYER_OWNED = 2},
                Context = {new = function() return {} end},
                Vec3f = {new = function(x, y, z) return {x = x, y = y, z = z} end},
                Vec2f = {new = function(x, y) return {x = x, y = y} end},
              },
              engine = {
                entityExists = function(entity) return entity == 10 or entity == 11 end,
                terrain = {
                  isValidCoordinate = function(point) return not invalidCoordinate or not invalidCoordinate(point) end,
                  isOnWater = function(point)
                    samples[#samples + 1] = {x = point.x, y = point.y}
                    return water and water(point) or false
                  end,
                },
                getComponent = function(_, kind) return kind == 1 and construction or owner end,
                system = {streetConnectorSystem = {getConstructionEntityForSubconstruction = function() return 10 end}},
                util = {
                  getPlayer = function() return 7 end,
                  getEntityName = function() return 'Test Farm' end,
                  proposal = {},
                },
              },
              res = {constructionRep = {
                find = function(name) return name end,
                get = function(name)
                  local kinds = {farm = 'farm_field', livestock_farm = 'livestock_field',
                    cotton_farm = 'cotton_field', rubber_farm = 'rubber_field', forest = 'forest_field'}
                  local kind = name:match('/industries/([^/]+)/')
                  local fields = {}
                  for index = 1, 8 do
                    fields[index] = {pos = {80 * index, 240}, size = {80, 80}, road = {0, 0, 0, 0}}
                  end
                  return {updateScript = {params = {fieldConfig = {
                    type = kinds[kind], fields = fields, alignToTerrain = true,
                  }}}}
                end,
              }},
            }
            api.engine.util.proposal.createProposalReplaceConstruction = function(entity, params)
              nativeRequests[#nativeRequests + 1] = {entity = entity, params = copy(params)}
              return {
                toRemove = {entity}, old2new = {[entity] = 0},
                toAdd = {{fileName = construction.fileName,
                  transf = copy(construction.transf), playerEntity = owner and owner.player or -1,
                  construction = {params = copy(params), frozenNodes = {501}, frozenEdges = {502}},
                }},
              }
            end
            function resultData()
              return {
                errorState = {critical = false, messages = errors or {}},
                collisionInfo = {
                  collisionEntities = collisions or {}, buildingEntities = {},
                  removableModules = removableModules or {},
                },
              }
            end
            function ug_require(path)
              if path == '::/scripts/table_util.tl' then return {copy = copy} end
              return layout
            end
        """)
        self.lua.globals().layout = self.lua.execute(
            (ROOT / "content/tidy_fields/layout.lua").read_text(encoding="utf-8")
        )
        self.lua.globals().proposal = self.lua.execute(
            (ROOT / "content/tidy_fields/proposal.lua").read_text(encoding="utf-8")
        )

    def test_keeps_modules_and_original_parameters(self):
        self.lua.execute("""
            local candidate, context, reason = proposal.make(10)
            assert(candidate and context.player == 7 and reason == nil)
            local replacement = candidate.toAdd[1]
            local params = replacement.construction.params
            assert(replacement.fileName == construction.fileName)
            assert(replacement.transf[1] == 100 and replacement.transf[2] == 200)
            assert(replacement.playerEntity == -1)
            assert(replacement.construction.frozenNodes[1] == 501 and replacement.construction.frozenEdges[1] == 502)
            assert(candidate.toRemove[1] == 10 and candidate.old2new[10] == 0)
            assert(params.xinTidyFields and params.seed == 123 and params.year == 1950)
            assert(params.xinTidyLayout == 'all')
            assert(params.upgrade == true)
            assert(params.modules[2].variant == 1 and params.modules[8].variant == 2)
            assert(params.xinTidyFieldOrder[1] == 2 and params.xinTidyFieldOrder[2] == 8)
            assert(#params.xinTidyFieldLayout == 8)
            assert(params.xinTidyFieldSlots[2] and params.xinTidyFieldSlots[8])
            assert(not construction.params.xinTidyFields)
            assert(not construction.params.xinTidyFieldOrder)
            assert(not construction.params.xinTidyFieldLayout)
        """)

    def test_accepts_each_layout_choice(self):
        for kind in ("farm", "livestock_farm", "cotton_farm", "rubber_farm", "forest"):
            for mode in ("left", "right", "front", "back", "left_right", "left_front", "left_back",
                         "right_front", "right_back", "front_back", "left_right_front", "left_right_back",
                         "left_front_back", "right_front_back", "all"):
                with self.subTest(kind=kind, mode=mode):
                    self.lua.globals().construction.fileName = f"::/industries/{kind}/{kind}.con"
                    self.lua.globals().chosenMode = mode
                    self.lua.execute("""
                        local candidate = assert(proposal.make(10, chosenMode))
                        local replacement = candidate.toAdd[1]
                        assert(replacement.construction.params.xinTidyLayout == chosenMode)
                        assert(replacement.construction.params.upgrade == true)
                        assert(replacement.fileName == construction.fileName)
                    """)
        self.lua.execute("local candidate, _, reason = proposal.make(10, 'unknown'); assert(not candidate and reason)")

    def test_repeated_tidy_uses_current_modules_and_new_layout(self):
        self.lua.execute("""
            local first = assert(proposal.make(10, 'left'))
            construction.params = first.toAdd[1].construction.params
            construction.params.modules[3] = {name = 'field.module', variant = 3}
            construction.params.xinTidyFieldLayout[8].pos = {10000, 10000}
            local second = assert(proposal.make(10, 'right_back'))
            local replacement = second.toAdd[1]
            local params = replacement.construction.params
            assert(params.xinTidyFields and params.xinTidyLayout == 'right_back')
            assert(params.xinTidyFieldOrder[1] == 2)
            assert(params.xinTidyFieldOrder[2] == 3)
            assert(params.xinTidyFieldOrder[3] == 8)
            assert(params.xinTidyFieldLayout[3] and #params.xinTidyFieldLayout == 8)
            assert(math.abs(params.xinTidyFieldLayout[8].pos[1]) < 1000 and math.abs(params.xinTidyFieldLayout[8].pos[2]) < 1000)
            assert(params.modules[2].variant == 1 and params.modules[3].variant == 3 and params.modules[8].variant == 2)
            assert(replacement.playerEntity == -1)
            assert(replacement.transf[1] == 100 and replacement.transf[2] == 200)
            assert(construction.params.xinTidyLayout == 'left')
            assert(construction.params.xinTidyFieldOrder[2] == 8)
        """)

    def test_coastal_plan_samples_rotated_footprints_and_retains_future_slots(self):
        self.lua.execute("""
            construction.transf.transformPosition = function(self, point)
              return {x = self[1] - point.y, y = self[2] + point.x, z = self[3] + point.z}
            end
            water = function(point) return point.y >= 270 end
            local candidate = assert(proposal.make(10, 'left_right'))
            local params = candidate.toAdd[1].construction.params
            assert(#params.xinTidyFieldLayout == 8)
            for slot, field in ipairs(params.xinTidyFieldLayout) do
              if params.xinTidyFieldSlots[slot] then
                assert(field.pos[1] + field.size[1] / 2 <= -60)
                local corner = construction.transf:transformPosition({x = field.pos[1] - field.size[1] / 2, y = field.pos[2] - field.size[2] / 2, z = 0})
                local sampled = false
                for _, point in ipairs(samples) do
                  if math.abs(point.x - corner.x) < 1e-6 and math.abs(point.y - corner.y) < 1e-6 then sampled = true end
                end
                assert(sampled)
              end
            end
            local impossible, _, reason = proposal.make(10, 'left')
            assert(not impossible and reason)
            assert(#nativeRequests == 1)
        """)

    def test_nearby_island_and_water_between_factory_and_field_are_not_used(self):
        self.lua.execute("""
            water = function(point)
              local x, y = point.x - 100, point.y - 200
              return not (x <= 60 or x <= 160 and y >= -30 and y <= 90 or x >= 320)
            end
            local candidate = assert(proposal.make(10, 'left'))
            local params = candidate.toAdd[1].construction.params
            assert(#params.xinTidyFieldLayout == 8)
            local available = 0
            for slot, field in ipairs(params.xinTidyFieldLayout) do
              if params.xinTidyFieldSlots[slot] then
                available = available + 1
                assert(field.pos[1] + field.size[1] / 2 <= 160)
              end
            end
            assert(available == 2 and params.xinTidyFieldSlots[2] and params.xinTidyFieldSlots[8])
            construction.params.modules[3] = {name = 'field.module'}
            local tooMany, _, reason = proposal.make(10, 'left')
            assert(not tooMany and reason and #nativeRequests == 1)
            construction.params.modules[3] = nil
            water = function(point) return point.x > 168 and point.x < 176 end
            local disconnected, _, blocked = proposal.make(10, 'left')
            assert(not disconnected and blocked and #nativeRequests == 1)
        """)

    def test_plan_checks_interior_terrain_points(self):
        self.lua.execute("""
            local initial = assert(proposal.make(10, 'left'))
            local field = initial.toAdd[1].construction.params.xinTidyFieldLayout[2]
            local center = construction.transf:transformPosition({x = field.pos[1], y = field.pos[2], z = 0})
            water = function(point)
              return math.abs(point.x - center.x - 10) < 1 and math.abs(point.y - center.y - 20) < 1
            end
            local candidate = assert(proposal.make(10, 'left'))
            local params = candidate.toAdd[1].construction.params
            for slot in pairs(params.modules) do
              local dry = params.xinTidyFieldLayout[slot]
              assert(math.abs(dry.pos[1] - field.pos[1]) >= (dry.size[1] + field.size[1]) / 2
                or math.abs(dry.pos[2] - field.pos[2]) >= (dry.size[2] + field.size[2]) / 2)
            end
        """)

    def test_terrain_refusal_is_localized_without_submitting_a_proposal(self):
        self.lua.execute('water = function() return true end')
        for language, expected in (
            ('en', 'Not enough connected land in the selected directions for the existing plots.'),
            ('zh_CN', '所选方向没有足够与厂区相连的陆地容纳现有地块。'),
        ):
            with self.subTest(language=language):
                self.lua.globals()._ = self.translations[language].__getitem__
                candidate, context, reason = self.lua.globals().proposal.make(10, 'left')
                self.assertIsNone(candidate)
                self.assertIsNone(context)
                self.assertEqual(reason, expected)
                self.assertEqual(self.lua.eval('#nativeRequests'), 0)

    def test_describes_native_failure_details(self):
        for setup, expected in (
            ("collisions = {{entity = 40}}", "原版施工检查未通过，具体原因请查看游戏日志。"),
            ("removableModules = {44}", "原版施工检查未通过，具体原因请查看游戏日志。"),
            ("errors = {'road connection mismatch'}", "无法整理：road connection mismatch"),
        ):
            with self.subTest(setup=setup):
                self.lua.execute("collisions = nil; removableModules = nil; errors = nil")
                self.lua.execute(setup)
                self.lua.globals().expectedReason = expected
                self.lua.execute("assert(proposal.describeFailure(resultData()) == expectedReason)")

    def test_supports_unowned_and_player_owned_industries(self):
        self.lua.execute("""
            assert(proposal.getTarget(11) == 10)
            owner = {player = 7}
            local candidate = proposal.make(10)
            assert(candidate.toAdd[1].playerEntity == 7)
            owner = {player = 8}
            assert(not proposal.make(10))
        """)


if __name__ == "__main__":
    unittest.main()
