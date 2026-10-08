local M = {}

M.types = {
  cloverleaf = { name = "Cloverleaf interchange", icon = "cloverleaf_interchange", order = 6100,
    text = "All four loops are enabled by default. Shared arcs use one native two-way road with one lane each way, connected to one-way ramps. Right turns remain when a loop is disabled." },
  diamond = { name = "Diamond interchange", icon = "diamond_interchange", order = 6200,
    text = "Connects an east-west highway to a north-south two-way road. Each of the four ramps can be disabled. Cross-road endpoints remain elevated." },
  trumpet = { name = "Trumpet interchange", icon = "trumpet_interchange", order = 6300,
    text = "Connects an east-west highway to a two-lane branch on the south, with one loop ramp. Use the game's rotation controls to change the branch direction." },
  directional = { name = "Directional T interchange", icon = "t_interchange", order = 6400,
    text = "Connects an east-west mainline to a southern branch. Every turn has a separate ramp; the two left turns cross at different levels." },
  turbine = { name = "Turbine interchange", icon = "cloverleaf_interchange", order = 6500,
    text = "A full four-way interchange with four left-turn ramps sweeping around the center. Its larger footprint suits highway junctions." },
  stack = { name = "Four-level stack interchange", icon = "t_interchange", order = 6600,
    text = "Two mainline levels and two left-turn ramp levels provide all twelve through and turning movements." },
}

local function option(key, name, values, default)
  return { key = key, name = name, values = values, defaultIndex = default or 1,
    displayMode = "Horizontal" }
end

local function points(params, prefix)
  for i = 1, 4 do
    params[#params + 1] = {
      key = prefix .. "Enabled" .. i, name = tostring(i),
      values = { _("Off"), _("Keep") }, defaultIndex = 2,
      uiType = "CheckBox", displayMode = "Compact", group = "interchangePoints", hideLabel = true,
    }
  end
end

function M.definition(kind)
  local spec = assert(M.types[kind], "Unknown interchange")
  local params = {
    option("lanes", _("Lanes"), { "2", "3" }),
  }
  if kind == "cloverleaf" then
    points(params, "leaf")
  elseif kind == "diamond" then
    points(params, "ramp")
  end
  return {
    description = { name = _(spec.name), description = _(spec.text),
      icon = kind .. ".tga",
      previewIcon = kind .. "_preview.tga" },
    availability = { yearFrom = 1940, yearTo = 0 },
    menuCategory = { categories = { { category = "xin_interchange_pack", order = spec.order } } },
    heightAdjustable = true,
    configureLayerScript = {
      fileName = "::/gui/construction/construction_desc_layers.script@configureDefaultLayerFn",
      params = { heightmapContours = true },
    },
    configureHudIconsScript = {
      fileName = "::/gui/construction/construction_desc_hud_icons.script@configureStreetConstructionHudIconsFn",
    },
    soundConfig = { builderAudioRes = "::/gui/construction/sound/buildoze_construction_large.builder_audio" },
    params = params,
    updateScript = { fileName = "interchange.script@updateFn", params = { kind = kind } },
  }
end

return M
