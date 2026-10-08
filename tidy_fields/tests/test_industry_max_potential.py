"""Exercise the mod against the installed game's Lua industry generator.

Run with a Python environment containing lupa, optionally passing --game-dir.
Construction configs, field generation, production recipes, random boosters,
and the completion hook are game code. Model geometry is replaced with an
empty render scene while the actual construction/script loading chain runs.
"""

import argparse
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

from lupa import LuaRuntime


GAME_DIR = Path.home() / "Library/Application Support/Steam/steamapps/common/Transport Fever 3"
MOD_DIR = Path(__file__).resolve().parents[1]

PRELUDE = r"""
function _(value) return value end
function pGetText(_, value) return value end
function string.starts(value, prefix) return value:sub(1, #prefix) == prefix end
function math.round(value) return math.floor(value + 0.5) end
function clone(value)
   if type(value) ~= "table" then return value end
   local result = {}
   for key, item in pairs(value) do result[key] = clone(item) end
   return result
end
function equal(left, right)
   if type(left) ~= type(right) then return false end
   if type(left) ~= "table" then return left == right end
   for key, value in pairs(left) do
      if not equal(value, right[key]) then return false end
   end
   for key in pairs(right) do
      if left[key] == nil then return false end
   end
   return true
end
local function identity()
   return {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}
end
modules = {
   ["::/scripts/construction/laneutil.lua"] = {},
   ["/scripts/table_util.tl"] = {deepEquals = equal},
   ["/scripts/mat4.tl"] = {
      identity = identity,
      transl = function(position)
         local matrix = identity()
         matrix[13], matrix[14], matrix[15] = position.x, position.y, position.z
         return matrix
      end,
   },
   ["/scripts/vec3.tl"] = {},
   ["::/scripts/construction/constructionutil.lua"] = {
      addModelsAndGroups = function() end,
   },
   ["/scripts/construction/modulesutil.lua"] = {},
}
function require(path) return assert(modules[path], path) end
ug_require = require
modifiers = {}
log = {message = function() end}
function addModifier(name, callback)
   modifiers[name] = callback
end
function complete(result, fieldCount)
   for _ = 1, fieldCount do
      result.subconstructions[#result.subconstructions + 1] = {}
   end
   result.terminateConstructionHook()
end
"""


class IndustryPotentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LuaRuntime(unpack_returned_tuples=True)
        cls.lua.execute(PRELUDE)
        cls.env = cls.lua.globals()
        industry_dir = GAME_DIR / "base/content/industries"
        for name in ("fieldutil", "industryutil"):
            source = (industry_dir / f"{name}.lua").read_text(encoding="utf-8-sig")
            cls.env.modules[f"/industries/{name}.lua"] = cls.lua.execute(source)
        cls.env.modules["::/industries/industryutil.lua"] = cls.env.modules["/industries/industryutil.lua"]
        cls.layout = cls.lua.execute((MOD_DIR / "content/tidy_fields/layout.lua").read_text())
        cls.env.modules["xin_tidy_fields_1::/tidy_fields/layout.lua"] = cls.layout

        cls.constructors = {}
        for archive in sorted(industry_dir.glob("*.zip")):
            with ZipFile(archive) as zipped:
                for filename in zipped.namelist():
                    if filename.endswith(".con.lua"):
                        cls.lua.execute(zipped.read(filename).decode("utf-8-sig"))
                        cls.constructors[filename] = cls.env.data()
        if not cls.constructors:
            raise RuntimeError(f"No industry constructors found in {industry_dir}")

        entry = json.loads((MOD_DIR / "mod.json").read_text())["runScript"]["fileName"]
        resource, function = entry.split("::/", 1)[1].split("@", 1)
        cls.lua.execute((MOD_DIR / "content" / (resource + ".lua")).read_text())
        cls.env.data()[function]()
        cls.original = cls.env.modules["/industries/industryutil.lua"]["makeIndustryUpdateFn"](
            cls.lua.eval("{static = {}, level1 = {}}")
        )
        cls.lua.execute("""
            local industryutil = modules['/industries/industryutil.lua']
            local generate = industryutil.makeIndustryUpdateFn
            industryutil.makeIndustryUpdateFn = function(_modelGeometry)
                return generate({static = {}, level1 = {}})
            end
        """)
        cls.updates, cls.redirected = {}, set()
        for filename, constructor in cls.constructors.items():
            modified = cls.env.modifiers.loadConstruction("industries/" + filename, cls.env.clone(constructor))
            reference, entry_function = modified.updateScript.fileName.split("@", 1)
            if reference.startswith("xin_tidy_fields_1::/"):
                cls.redirected.add(filename)
                script_resource = reference.split("::/", 1)[1]
                source = (MOD_DIR / "content" / (script_resource + ".lua")).read_text()
                script_name = reference + ".lua"
            else:
                industry = filename.split("/", 1)[0]
                with ZipFile(industry_dir / f"{industry}.zip") as zipped:
                    script_resource = f"{industry}/{reference}.lua"
                    source = zipped.read(script_resource).decode("utf-8-sig")
                script_name = "::/industries/" + script_resource
            cls.lua.execute(source)
            cls.updates[filename] = cls.env.modifiers.loadScript(script_name, cls.env.data())[entry_function]

    def generate_pair(self, filename, constructor, seed, size, **extra_params):
        capture = constructor["updateScript"]["params"]
        params = self.lua.table_from({"seed": seed, "industrySize": size, **extra_params})
        original = self.original(self.env.clone(capture), self.env.clone(params))
        modified = self.updates[filename](self.env.clone(capture), self.env.clone(params))
        return original, modified

    def test_all_industry_caps_across_seeds_and_size_selections(self):
        self.assertEqual(self.redirected, {
            f"{name}/{name}.con.lua" for name in ("farm", "livestock_farm", "cotton_farm", "rubber_farm", "forest")
        })
        cases = 0
        expandable = 0
        for filename, constructor in self.constructors.items():
            field_config = constructor["updateScript"]["params"]["fieldConfig"]
            fields = field_config["fields"] if field_config is not None else None
            expandable += fields is not None
            for seed in (1, 7, 42, 2026, 99999):
                for size in (0, 1, 2, 3, 4):
                    with self.subTest(industry=filename, seed=seed, size=size):
                        original, modified = self.generate_pair(filename, constructor, seed, size)
                        before = original["subconstructions"][1]
                        after = modified["subconstructions"][1]
                        if fields is not None:
                            self.assertEqual(after["industry"]["maxLevel"], len(fields))
                        else:
                            self.assertEqual(after["industry"]["maxLevel"], before["industry"]["maxLevel"])
                        self.assertEqual(after["industry"]["productionLevel"], before["industry"]["productionLevel"])
                        self.assertTrue(self.env.equal(after["rules"], before["rules"]))
                        self.assertTrue(self.env.equal(after["stocks"], before["stocks"]))
                        cases += 1
        print(f"Validated {cases} generation cases across {len(self.constructors)} industries ({expandable} with expansion fields).")

    def test_existing_module_count_controls_production_after_completion(self):
        cases = 0
        for filename, constructor in self.constructors.items():
            field_config = constructor["updateScript"]["params"]["fieldConfig"]
            fields = field_config["fields"] if field_config is not None else None
            if fields is None:
                continue
            for module_count in (1, len(fields) // 2, len(fields)):
                for seed, size, input_enabled in ((7, 1, 2), (42, 2, 1), (2026, 4, 2)):
                    with self.subTest(industry=filename, modules=module_count, seed=seed):
                        original, modified = self.generate_pair(
                            filename, constructor, seed, size, inputEnabled=input_enabled
                        )
                        self.env.complete(original, module_count)
                        self.env.complete(modified, module_count)
                        before = original["subconstructions"][1]
                        after = modified["subconstructions"][1]
                        self.assertEqual(after["industry"]["maxLevel"], len(fields))
                        self.assertEqual(after["industry"]["productionLevel"], module_count)
                        self.assertEqual(after["industry"]["productionLevel"], before["industry"]["productionLevel"])
                        self.assertTrue(self.env.equal(after["rules"], before["rules"]))
                        self.assertTrue(self.env.equal(after["stocks"], before["stocks"]))
                        cases += 1
        print(f"Validated {cases} completed constructions at initial, partial, and full expansion.")

    def test_tidy_layout_preserves_full_potential_and_current_production(self):
        cases = 0
        for filename in sorted(self.redirected):
            constructor = self.constructors[filename]
            field_config = constructor.updateScript.params.fieldConfig
            count = len(field_config.fields)
            for module_count in (1, count // 2, count):
                for seed, size in ((1, 0), (42, 1), (2026, 2)):
                    with self.subTest(industry=filename, modules=module_count, seed=seed, size=size):
                        modules = self.lua.table_from({slot: self.lua.table() for slot in range(1, module_count + 1)})
                        params = self.lua.table_from({
                            "modules": modules, "xinTidyFields": True, "xinTidyLayout": "all",
                            "xinTidyFieldOrder": self.layout.makeOrder(modules, count),
                        })
                        planned, reason, _available = self.layout.plan(field_config, params)
                        self.assertIsNone(reason)
                        active_slots = self.lua.table_from({slot: True for slot in range(1, module_count + 1)})
                        original, modified = self.generate_pair(
                            filename, constructor, seed, size, modules=modules, xinTidyFields=True,
                            xinTidyLayout="all", xinTidyFieldOrder=params.xinTidyFieldOrder,
                            xinTidyFieldLayout=planned, xinTidyFieldSlots=active_slots,
                        )
                        self.assertEqual(len(modified.slots), module_count)
                        self.env.complete(original, module_count)
                        self.env.complete(modified, module_count)
                        before, after = original.subconstructions[1], modified.subconstructions[1]
                        self.assertEqual(after.industry.maxLevel, count)
                        self.assertEqual(after.industry.productionLevel, module_count)
                        self.assertTrue(self.env.equal(after.rules, before.rules))
                        self.assertTrue(self.env.equal(after.stocks, before.stocks))
                        cases += 1
        print(f"Validated {cases} tidied constructions across the five redirected industry scripts.")

    def test_potential_wrapper_preserves_all_update_return_values(self):
        self.lua.execute("""
            local originalResult = {subconstructions = {{industry = {maxLevel = 1, productionLevel = 2}}}}
            local script = modifiers.loadScript('xin_tidy_fields_1::/tidy_fields/generated/farm.script.lua', {
                updateFn = function() return originalResult, nil, 'extra', 19 end,
            })
            local result = table.pack(script.updateFn({fieldConfig = {fields = {{}, {}, {}, {}}}}, {}))
            assert(result.n == 4 and result[1] == originalResult and result[2] == nil)
            assert(result[3] == 'extra' and result[4] == 19)
            assert(result[1].subconstructions[1].industry.maxLevel == 4)
            assert(result[1].subconstructions[1].industry.productionLevel == 2)
        """)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, default=GAME_DIR)
    args, remaining = parser.parse_known_args()
    GAME_DIR = args.game_dir
    unittest.main(argv=[sys.argv[0], *remaining])
