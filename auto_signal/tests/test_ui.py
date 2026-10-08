import json
import unittest
from pathlib import Path

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class SignalUiTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.translations = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
        self.set_language("en")
        self.modifier = None

        def add_modifier(name, callback):
            self.assertEqual(name, "loadConstruction")
            self.modifier = callback

        self.lua.globals().addModifier = add_modifier
        self.load_script("content/mod.script.lua").runFn()
        self.ui = self.load_script("content/auto_signal/ui.script.lua")

    def set_language(self, language):
        localized = self.translations.get(language, {})
        english = self.translations["en"]
        self.lua.globals()["_"] = lambda text: localized.get(
            text, english.get(text, text)
        )

    def load_script(self, path):
        self.lua.execute((ROOT / path).read_text(encoding="utf-8"))
        return self.lua.globals().data()

    def signal_params(self, resource="base::/infrastructure/signal/signal_path_a.con"):
        original = self.lua.table_from({"key": "oneWay", "defaultIndex": 2})
        construction = self.lua.table_from(
            {"params": self.lua.table_from([original])}
        )
        result = self.modifier(resource, construction)
        return result.params

    def test_native_signal_parameters_and_spacing_values(self):
        for variant in ("a", "c"):
            params = self.signal_params(
                f"base::/infrastructure/signal/signal_path_{variant}.con"
            )
            self.assertEqual(len(params), 3)
            self.assertEqual(params[1].key, "oneWay")
            self.assertEqual(params[1].defaultIndex, 2)
            enabled, spacing = params[2], params[3]
            self.assertEqual(enabled.key, "asEnabled")
            self.assertEqual(enabled["values"][1], "Off")
            self.assertEqual(enabled["values"][2], "On")
            self.assertEqual(enabled.defaultIndex, 2)
            self.assertEqual(spacing.key, "asMinimumSpacing")
            self.assertEqual(spacing.uiType, "Slider")
            self.assertEqual(spacing.numbers[spacing.defaultIndex], 300)
            self.assertEqual(len(spacing.numbers), 1951)
            for index in range(1, 1952):
                self.assertEqual(spacing.numbers[index], index + 49)

    def test_other_constructions_keep_their_parameters(self):
        params = self.signal_params("base::/infrastructure/station/train_station.con")
        self.assertEqual(len(params), 1)
        self.assertEqual(params[1].key, "oneWay")

    def test_visibility_toggle_keeps_selected_spacing(self):
        params = self.lua.table_from({"asEnabled": 2, "asMinimumSpacing": 450})
        self.assertEqual(self.ui.spacingVisibility(None, params), "Enabled")
        params.asEnabled = 1
        self.assertEqual(self.ui.spacingVisibility(None, params), "InputActionOnly")
        params.asEnabled = 2
        self.assertEqual(self.ui.spacingVisibility(None, params), "Enabled")
        self.assertEqual(params.asMinimumSpacing, 450)

    def test_spacing_format_and_steps_use_meters(self):
        self.assertEqual(self.ui.formatMinimumSpacing(None, 300), "300 m")
        self.assertEqual(self.ui.stepMinimumSpacing(None, 300, 1), 350)
        self.assertEqual(self.ui.stepMinimumSpacing(None, 300, -1), 250)
        self.assertEqual(self.ui.stepMinimumSpacing(None, 50, -1), 50)
        self.assertEqual(self.ui.stepMinimumSpacing(None, 2000, 1), 2000)

    def test_localized_labels_and_units(self):
        for language, label, unit in (
            ("en", "Auto placement", "300 m"),
            ("zh_CN", "自动布置", "300 米"),
            ("unsupported", "Auto placement", "300 m"),
        ):
            self.set_language(language)
            self.assertEqual(self.signal_params()[2].name, label)
            self.assertEqual(self.ui.formatMinimumSpacing(None, 300), unit)


if __name__ == "__main__":
    unittest.main()
