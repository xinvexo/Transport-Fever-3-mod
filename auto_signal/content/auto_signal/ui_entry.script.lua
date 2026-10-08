local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local constructionUtil = ug_require "::/gui/construction/construction_react_util.tl"
local scriptParamUtil = ug_require "::/gui/main/script_param_util.tl"
local spacingWidget = ug_require "xin_auto_signal_1::/auto_signal/spacing_widget.lua"

local spacingFormatters = setmetatable({}, { __mode = "k" })
local getDefinitions = constructionUtil.getConstructionDefinitions
constructionUtil.getConstructionDefinitions = function(...)
   local definitions = getDefinitions(...)
   for _, definition in ipairs(definitions) do
      local enabled, spacing
      for _, param in ipairs(definition.params or {}) do
         if param.key == "asEnabled" then enabled = true end
         if param.key == "asMinimumSpacing" then spacing = param end
      end
      if enabled and spacing and type(spacing.formatValueFn) == "function"
         and not spacingFormatters[spacing.formatValueFn] then
         -- Native controls can share formatters (Lua 5.2 also caches closures).
         -- Tag a private wrapper so unrelated controls keep the native builder.
         local source = { format = spacing.formatValueFn }
         spacing.formatValueFn = function(...) return source.format(...) end
         spacingFormatters[spacing.formatValueFn] = true
      end
   end
   return definitions
end

-- ConstructionParam passes the formatter through to the control but omits its key.
local buildSimple = scriptParamUtil.buildScriptParamCompSimple
scriptParamUtil.buildScriptParamCompSimple = function(param)
   if spacingFormatters[param.scriptParam.formatValueFn] then
      return spacingWidget.build(param)
   end
   return buildSimple(param)
end

local entry = react.RegisterPluginRecipe(
   entryPoint.ModEntryPointExtension, "XinAutoSignalUiEntry", function() return nil end
)

function data()
   return { entry = entry }
end
