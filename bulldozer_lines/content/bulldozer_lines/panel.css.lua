local ssu = require "::/gui/main/stylesheetutil.lua"
local colorUtil = require "::/gui/main/color_util.tl"

function data()
  local result = {}
  local a = ssu.makeAdder(result)
  local prefix = "#xin.bulldozer.lines "
  local colors = api.gui.genericRep.get(api.gui.genericRep.find("::/gui/main/default_colors.gres")).data
  local transparency = api.gui.genericRep.get(api.gui.genericRep.find("::/gui/main/transparency.gres")).data

  -- Keep the native line manager's upper card dimensions, assets and spacing.
  -- Match classes on both native components and recipe-backed R::Component.
  a(prefix .. "!bl-content", {
    minSize = { 500, -1 }, maxSize = { 500, -1 }, padding = { 0, 8, 8, 8 },
  })
  a(prefix .. "TextInputField", { size = { 312, -1 }, margin = { 12, 0, 4, 4 } })
  a(prefix .. "!bl-card", {
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
  a(prefix .. "!bl-header", { size = { -1, 32 }, gravity = { -1, 0.5 } })
  a(prefix .. "BoxLayout!bl-filters ToggleButton", {
    margin = { 1, 1, 1, 1 }, padding = { 6, 6, 6, 6 },
  })
  a(prefix .. "BoxLayout!bl-filters ImageView", { size = { 18, 18 } })
  a(prefix .. "!bl-list", {
    size = { -1, 198 }, minSize = { 0, 120 }, maxSize = { -1, 198 },
    padding = { 0, 0, 0, 0 }, gravity = { -1, -1 },
  })
  -- Keep the table mounted across empty searches, while folding its geometry.
  a(prefix .. "!bl-list!empty", { visibility = "none" })
  a(prefix .. "Table::Header", { visibility = "none" })
  a(prefix .. "Table::Header TextView", { margin = { 0, 0, 0, 0 } })
  a(prefix .. "Button!bl-row", {
    size = { -1, 24 }, minSize = { 0, 24 },
    padding = { 0, 0, 0, 0 }, margin = { 0, 0, 0, 0 },
    gravity = { -1, 0.5 }, backgroundColor = colors.Invisible,
    backgroundColor1 = colors.Invisible, borderColor = colors.Invisible,
  })
  a(prefix .. "Button!bl-row Button::Layout", { gravity = { -1, -1 } })
  a(prefix .. "!bl-row-layout", { innerSpacing = { 0, 0 }, gravity = { -1, 0.5 } })
  a(prefix .. "Button!bl-row!alternate", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.VeryHigh * 0.5),
  })
  a(prefix .. "Button!bl-row!selected", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.High),
  })
  a(prefix .. "Button!bl-row:hover", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.VeryHigh),
  })
  a(prefix .. "Button!bl-row!selected:hover", {
    backgroundColor = colorUtil.withTransparencyRaw(colors.NeutralLight, transparency.Medium),
  })
  a(prefix .. "!bl-check", {
    size = { 24, 24 }, minSize = { 24, 24 }, maxSize = { 24, 24 },
    padding = { 0, 0, 0, 0 }, margin = { 0, 0, 0, 0 }, gravity = { 0, 0.5 },
  })
  a(prefix .. "!bl-color", {
    size = { 24, 24 }, minSize = { 24, 24 }, maxSize = { 24, 24 }, gravity = { 0.5, 0.5 },
  })
  a(prefix .. "TextView!bl-name", {
    minSize = { 0, -1 }, maxSize = { 412, -1 },
    padding = { 0, 4, 0, 4 }, margin = { 0, 0, 0, 0 },
    gravity = { -1, 0.5 }, textAlignment = { 0, 0.5 },
  })
  a(prefix .. "!bl-locate", {
    size = { 28, 24 }, minSize = { 28, 24 }, maxSize = { 28, 24 }, gravity = { 1, 0.5 },
  })
  a(prefix .. "R::LocateButton Button", {
    size = { 20, 20 }, padding = { 0, 0, 0, 0 }, margin = { 1, 1, 1, 1 },
    gravity = { 1, 0.5 },
  })
  a(prefix .. "R::LocateButton ImageView", { gravity = { 0.5, 0.5 } })
  a(prefix .. "!bl-empty", {
    size = { -1, 198 }, gravity = { -1, -1 }, textAlignment = { 0.5, 0.5 },
    padding = { 8, 8, 8, 8 }, margin = { 0, 0, 0, 0 },
  })
  log.message("[Bulldozer Lines] Native-style upper line card stylesheet loaded.")
  return result
end
