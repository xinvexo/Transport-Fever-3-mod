local paramUtil = require "::/scripts/construction/param_util.tl"

local radii = { 160, 200, 240, 320, 400, 500 }
local spacings = { 5, 6, 8, 10, 12 }
local elevations = { -32, -24, -16, 0, 8, 12, 16, 24 }
local grades = { 0.02, 0.03, 0.04 }

local function option(key, name, values, defaultIndex)
  return {
    key = key, name = name, values = values, defaultIndex = defaultIndex,
    displayMode = "Horizontal", uiType = "Slider",
  }
end

function data()
  return {
    description = {
      name = "双线掉头回环",
      description = "上行进入、下行返回。回环升降：0=地面，正值=高架，负值=隧道。两端保持基准高度，坡道自动延长。先在平坦空地预览，再连接主线；请自行设置行车方向信号。",
      icon = "loop.tga",
      previewIcon = "loop_preview.tga",
    },
    availability = { yearFrom = 1900, yearTo = 0 },
    -- Retained for existing saves; the new prefabs have separate resources.
    menuCategory = { categories = {} },
    heightAdjustable = true,
    configureLayerScript = {
      fileName = "::/gui/construction/construction_desc_layers.script@configureDefaultLayerFn",
      params = { heightmapContours = true },
    },
    soundConfig = {
      builderAudioRes = "::/gui/construction/sound/buildoze_track.builder_audio",
    },
    params = {
      option("loopRadius", "回环半径", { "160 m", "200 m", "240 m", "320 m", "400 m", "500 m" }, 3),
      option("trackSpacing", "双线间距", { "5 m", "6 m", "8 m", "10 m", "12 m" }, 1),
      option("loopElevation", "回环升降", { "隧道 −32 m", "隧道 −24 m", "隧道 −16 m", "地面 0 m", "高架 +8 m", "高架 +12 m", "高架 +16 m", "高架 +24 m" }, 4),
      option("loopGrade", "最大坡度", { "20‰", "30‰", "40‰" }, 2),
      paramUtil.makeTrackTypeDefaultParam(),
      paramUtil.makeTrackTypeHighSpeedParam(),
      paramUtil.makeTrackCatenaryParam(),
    },
    updateScript = {
      fileName = "loop.script@updateFn",
      params = { radii = radii, spacings = spacings, elevations = elevations, grades = grades },
    },
  }
end
