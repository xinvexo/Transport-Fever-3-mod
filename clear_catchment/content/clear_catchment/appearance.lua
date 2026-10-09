local target = ug_require "xin_clear_catchment_1::/clear_catchment/target.lua"
local appearance = {}

local COLOR_SCALE = 0.65
local INNER_ALPHA = 0.80
local function deepen(color)
  -- Scale all channels equally: green stays green, blue stays blue, gray stays gray.
  return api.type.Vec3f.new(color.x * COLOR_SCALE, color.y * COLOR_SCALE, color.z * COLOR_SCALE)
end

function appearance.applyLayer(source)
  if not source then return source end
  -- This deliberately enables a separate native overlay for existing stations.
  -- The construction preview continues to be rendered by the game's builder.
  local layer = api.type.LayerConfig.new(source)
  local settings = api.type.LayerConfig.CatchmentAreaDisplaySettings.new(
    layer.catchmentAreaRenderableConfig.displaySettings
  )
  settings.personBaseColor = deepen(settings.personBaseColor)
  settings.cargoBaseColor = deepen(settings.cargoBaseColor)
  settings.inactiveColor = deepen(settings.inactiveColor)
  settings.unreachableColor = deepen(settings.unreachableColor)
  settings.borderAlpha = 1.0
  settings.borderAlphaPassive = 1.0
  -- A translucent fill makes the area readable even when its border fades.
  -- Keep the independent building painter and positioning beams untouched/off.
  settings.innerAlpha = INNER_ALPHA
  settings.buildingAlpha = 0.0
  settings.godrayAlpha = 0.0
  settings.godrayAlphaPassive = 0.0

  -- A fresh config keeps the native unrestricted carrier selection instead of
  -- inheriting a data layer's entity/carrier restriction.
  local catchment = api.type.LayerConfig.CatchmentAreaRenderableConfig.new()
  catchment.isVisible = true
  catchment.entity = -1
  catchment.person = true
  catchment.cargo = true
  catchment.maintenance = false
  catchment.noise = false
  catchment.pollution = false
  catchment.addGodrays = false
  catchment.displaySettings = settings
  layer.catchmentAreaRenderableConfig = catchment
  return layer
end

function appearance.apply(definition, result, entity)
  if not result or not result.layerConfig or not target.isStation(definition, entity) then return result end
  local updated = {}
  for key, value in pairs(result) do updated[key] = value end
  updated.layerConfig = appearance.applyLayer(result.layerConfig)
  return updated
end

function appearance.mergeLayer(fromConstruction, merged)
  if not merged or merged == fromConstruction then return merged end
  local layer = api.type.LayerConfig.new(merged)
  -- Preserve the chosen data layer's other settings, but retain our construction
  -- overlay's deeper palette and native width instead of adopting that layer's palette.
  layer.catchmentAreaRenderableConfig = api.type.LayerConfig.CatchmentAreaRenderableConfig.new(
    fromConstruction.catchmentAreaRenderableConfig
  )
  return layer
end

return appearance
