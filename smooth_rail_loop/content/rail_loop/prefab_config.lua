local paramUtil = require "::/scripts/construction/param_util.tl"
local M = {}

local variants = {
  raised = {
    name = "高架回环", order = 6100,
    icon = "::/gui/construction/build_control/infrastructure_bridge_32.tga",
    description = "中部抬升 8 米的铁路掉头回环，两端保持放置高度。先在空地放置，再连接双线主轨。",
  },
  lowered = {
    name = "地下回环", order = 6200,
    icon = "::/gui/construction/build_control/infrastructure_tunnel_32.tga",
    description = "中部下沉 12 米的铁路掉头回环，两端保持放置高度。先在空地放置，再连接双线主轨。",
  },
}

function M.definition(kind)
  local variant = assert(variants[kind], "Unknown rail loop prefab")
  return {
    description = {
      name = variant.name, description = variant.description,
      icon = variant.icon, previewIcon = "loop_preview.tga",
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
    params = {
      paramUtil.makeTrackTypeDefaultParam(),
      paramUtil.makeTrackTypeHighSpeedParam(),
      paramUtil.makeTrackCatenaryParam(),
    },
    updateScript = { fileName = "prefab_loop.script@updateFn", params = { kind = kind } },
  }
end

return M
