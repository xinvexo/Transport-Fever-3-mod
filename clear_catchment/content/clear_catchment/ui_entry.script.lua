local construction = ug_require "::/gui/construction/construction_react_util.tl"
local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local appearance = ug_require "xin_clear_catchment_1::/clear_catchment/appearance.lua"

local layers = setmetatable({}, { __mode = "k" })
local reported = {}
local function reportOnce(key, stage, layer, preferred)
  if reported[key] then return end
  reported[key] = true
  local config = layer and layer.catchmentAreaRenderableConfig
  local settings = config and config.displaySettings
  log.message(string.format(
    "[Clear Catchment] %s %s: preferred=%s visible=%s alpha=%s passive=%s width=%s person=%s cargo=%s fill=%s",
    key, stage, tostring(preferred), tostring(config and config.isVisible),
    tostring(settings and settings.borderAlpha), tostring(settings and settings.borderAlphaPassive),
    tostring(settings and settings.borderWidth), tostring(config and config.person), tostring(config and config.cargo),
    tostring(settings and settings.innerAlpha)
  ))
end

local nativeGetActionParams = construction.getActionParams
construction.getActionParams = function(definition, ...)
  -- Run the game's and other mods' layer configuration before changing colors.
  local original = nativeGetActionParams(definition, ...)
  local entity = select(5, ...)
  local result = appearance.apply(definition, original, entity)
  if result ~= original then
    local action = definition.action
    layers[result.layerConfig] = action
    reportOnce(action .. "/input", "native", original.layerConfig, false)
    reportOnce(action .. "/output", "configured", result.layerConfig, false)
  end
  return result
end

local nativeMergeLayerConfig = construction.mergeLayerConfig
construction.mergeLayerConfig = function(fromConstruction, preferred)
  local result = nativeMergeLayerConfig(fromConstruction, preferred)
  local action = fromConstruction and layers[fromConstruction]
  if action then
    -- A selected data layer replaces the construction layer after getActionParams.
    -- Keep the existing-station overlay in the final layer selected by the game.
    result = appearance.mergeLayer(fromConstruction, result)
    reportOnce(action .. "/merged/" .. tostring(preferred ~= nil), "final", result, preferred ~= nil)
  end
  return result
end

local entry = react.RegisterPluginRecipe(
  entryPoint.ModEntryPointExtension, "XinClearCatchmentEntry", function() return nil end
)
log.message("[Clear Catchment] Deeper existing-station colors and translucent fill loaded (revision 4, colorScale=0.65, fillAlpha=0.30).")

function data()
  return { entry = entry }
end
