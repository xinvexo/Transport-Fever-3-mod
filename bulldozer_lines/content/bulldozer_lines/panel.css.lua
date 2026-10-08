local ssu = require "::/gui/main/stylesheetutil.lua"
local colorUtil = require "::/gui/main/color_util.tl"

function data()
  local result = {}
  local a = ssu.makeAdder(result)
  local prefix = "#xin.bulldozer.lines "
  local colors = api.gui.genericRep.get(api.gui.genericRep.find("::/gui/main/default_colors.gres")).data
  local transparency = api.gui.genericRep.get(api.gui.genericRep.find("::/gui/main/transparency.gres")).data

  -- Keep the native line manager's upper card dimensions, assets and spacing.
  a(prefix .. "BoxLayout!bl-content", {
    minSize = { 500, -1 }, maxSize = { 500, -1 }, padding = { 0, 8, 8, 8 },
  })
  a(prefix .. "TextInputField", { size = { 312, -1 }, margin = { 12, 0, 4, 4 } })
  a(prefix .. "Component!bl-card", {
    size = { -1, 240 }, padding = { 1, 1, 1, 1 }, margin = { 0, 0, 6, 0 },
    backgroundImage1 = {
      fileName = "::/gui/entity_window/design/card_surface.tga",
      horizontal = { 0, 6, 26, 32 }, vertical = { 0, 6, 26, 32 },
    },
    borderImage = {
      fileName = "::/gui/entity_window/design/card_contour.tga",
      horizontal = { 0, 6, 26, 32 }, vertical = { 0, 6, 26, 32 },
    },
    backgroundColor1 = colors.BaseMedium, borderColor = colors.BaseVeryLight,
  })
  a(prefix .. "FloatingLayout!bl-header", { size = { -1, 32 }, gravity = { -1, 0.5 } })
  a(prefix .. "BoxLayout!bl-filters ToggleButton", {
    margin = { 1, 1, 1, 1 }, padding = { 6, 6, 6, 6 },
  })
  a(prefix .. "BoxLayout!bl-filters ImageView", { size = { 18, 18 } })
  a(prefix .. "List!bl-list", {
    size = { -1, 206 }, minSize = { -1, 120 }, maxSize = { -1, 206 },
    padding = { 0, 0, 0, 0 }, gravity = { -1, -1 },
  })
  a(prefix .. "Button!bl-row", {
    size = { 490, -1 }, padding = { 0, 0, 0, 0 }, margin = { 0, 0, 0, 0 },
    gravity = { 0, 0.5 }, backgroundColor1 = colors.Invisible, borderColor = colors.Invisible,
  })
  a(prefix .. "Button!bl-row Button::Layout", { gravity = { -1, -1 } })
  a(prefix .. "Button!bl-row Button::Layout > *", { innerSpacing = { 0, 0 } })
  a(prefix .. "Button!bl-row Button::Layout > BoxLayout", { gravity = { -1, 0.5 } })
  a(prefix .. "Button!bl-row!selected", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.High),
  })
  a(prefix .. "Button!bl-row:hover", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.VeryHigh),
  })
  a(prefix .. "Button!bl-row!selected:hover", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.Medium),
  })
  a(prefix .. "Button!bl-name", {
    padding = { 1, 2, 1, 2 }, margin = { 1, 1, 1, 1 }, gravity = { 0, -1 },
    backgroundColor1 = colors.Invisible, borderColor = colors.Invisible,
  })
  a(prefix .. "Button!bl-name TextView", { margin = { 0, 0, 0, 0 }, padding = { 0, 1, 0, 1 } })
  a(prefix .. "R::LocateButton Button", {
    size = { 20, 20 }, padding = { 0, 0, 0, 0 }, margin = { 1, 1, 1, 1 },
    gravity = { 1, 0.5 },
  })
  a(prefix .. "R::LocateButton ImageView", { gravity = { 0.5, 0.5 } })
  log.message("[Bulldozer Lines] Native-style upper line card stylesheet loaded.")
  return result
end
