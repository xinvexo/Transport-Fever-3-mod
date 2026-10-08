local paramUtil = require "::/scripts/construction/param_util.tl"
local bridgeChoices = require "xin_smooth_rail_loop_1::/rail_loop/bridge_choices.lua"
local M = {}

local variants = {
  raised = {
    name = "高架回环", order = 6100,
    icon = "raised_loop.tga", preview = "raised_loop_preview.tga",
    description = "紧凑回环，中部抬升 16 米，沿实际地形自动使用地面轨道、桥梁或隧道。分岔口附带双线主轨短接轨段。",
  },
  lowered = {
    name = "地下回环", order = 6200,
    icon = "lowered_loop.tga", preview = "lowered_loop_preview.tga",
    description = "紧凑回环，中部下沉 12 米，沿实际地形自动使用地面轨道、桥梁或隧道。分岔口附带双线主轨短接轨段。",
  },
}

function M.definition(kind)
  local variant = assert(variants[kind], "Unknown rail loop prefab")
  local params = {
    paramUtil.makeTrackTypeDefaultParam(),
    paramUtil.makeTrackTypeHighSpeedParam(),
    paramUtil.makeTrackCatenaryParam(),
  }
  bridgeChoices.addParams(params)
  return {
    description = {
      name = variant.name, description = variant.description,
      icon = variant.icon, previewIcon = variant.preview,
    },
    availability = { yearFrom = 0, yearTo = 0 },
    menuCategory = { categories = { { category = "rail_constructions", order = variant.order } } },
    heightAdjustable = true,
    undergroundView = kind == "lowered",
    configureLayerScript = {
      fileName = "::/gui/construction/construction_desc_layers.script@configureDefaultLayerFn",
      params = { heightmapContours = true },
    },
    configureHudIconsScript = {
      fileName = "::/gui/construction/construction_desc_hud_icons.script@configureTrackConstructionHudIconsFn",
    },
    soundConfig = { builderAudioRes = "::/gui/construction/sound/buildoze_track.builder_audio" },
    params = params,
    updateScript = { fileName = "prefab_loop.script@updateFn", params = { kind = kind } },
  }
end

return M
