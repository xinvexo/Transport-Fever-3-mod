local colorUtil = ug_require "::/gui/main/color_util.tl"
local layerUtil = ug_require "::/gui/layers/layer_react_util.tl"

local buildingColors = {}

function buildingColors.apply(definition, result)
  if not definition or definition.action ~= "ACTION_BULLDOZER"
    or not result or not result.layerConfig then return result end

  local districtColors = api.gui.genericRep.get(
    api.gui.genericRep.find("::/game_mechanics/towns/district_colors.gres")
  ).data
  local types = api.type.LayerConfig
  local cargoColor = types.ColorPassFn.CargoColor.new()
  local function range(colors)
    return types.ColorPassFn.BaseRangeColor.new({
      colorUtil.toVec4(colors.min), colorUtil.toVec4(colors.max),
    }, true)
  end
  cargoColor.residential = range(districtColors.Residential)
  cargoColor.commercial = range(districtColors.Commercial)
  cargoColor.industrial = range(districtColors.Industrial)
  cargoColor.includePassengers = true
  cargoColor.numBuildingLevels = 1

  local layer = types.new(result.layerConfig)
  local colorPass
  if layer.colorPassFn then
    -- Preserve the native underground background and other entity painters.
    colorPass = types.ColorPassFn.new(layer.colorPassFn)
  else
    local layerColors = api.gui.genericRep.get(
      api.gui.genericRep.find("::/gui/layers/layer_colors.gres")
    ).data
    colorPass = types.ColorPassFn.new()
    colorPass.fallbackColor = layerUtil.createDefaultFallbackColor(
      layerColors.Construction.Fallback.Surface, layerColors.Construction.Fallback.Details
    )
    -- Match station placement: tint the buildings without whitening the terrain.
    layer.colorPassFnForBuildingRenderableOnly = true
  end
  colorPass.townBuildingPainter = cargoColor
  layer.colorPassFn = colorPass

  local buildings = types.BuildingRenderableConfig.new(layer.buildingRenderableConfig)
  buildings.isVisible = true
  buildings.includeTownBuildingMainModel = true
  layer.buildingRenderableConfig = buildings

  local updated = {}
  for key, value in pairs(result) do updated[key] = value end
  updated.layerConfig = layer
  return updated
end

return buildingColors
