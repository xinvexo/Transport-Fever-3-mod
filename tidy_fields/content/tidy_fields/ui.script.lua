local builtin = ug_require "::/gui/main/builtin.lua"
local react = ug_require "::/gui/main/react.lua"
local industry_eow = ug_require "::/gui/entity_window/industry/industry_eow.script.tl"
local proposals = ug_require "xin_tidy_fields_1::/tidy_fields/proposal.lua"
local ui = {}
local PANEL_WIDTH = 360

local directions = {
  { value = "front", label = "Front" },
  { value = "back", label = "Back" },
  { value = "left", label = "Left" },
  { value = "right", label = "Right" },
}

local function sizeStyle(width, height)
  local style = api.gui.StyleSheet.new()
  style.size = api.type.Vec2f.new(width, height)
  return style
end

local function spacer(height)
  return builtin.Component{ meta = { styleSheet = sizeStyle(0, height) } }
end

local function directionStyle(index)
  local style = sizeStyle(PANEL_WIDTH / #directions, 36)
  style.padding = api.type.Vec4f.new(0, 0, 0, 0)
  local horizontal = index == 1 and { 0, 9, 21, 21 }
    or index == #directions and { 9, 9, 21, 30 } or { 9, 9, 21, 21 }
  local edge = index == 1 and "left" or index == #directions and "right" or "middle"
  local background = api.gui.NinePatch.new()
  background.fileName = "::/gui/builtin/button/default_surface.tga"
  background.horizontal = horizontal
  background.vertical = { 0, 9, 21, 30 }
  style.backgroundImage1 = background
  local border = api.gui.NinePatch.new()
  border.fileName = "::/gui/builtin/button/default_contour_" .. edge .. ".tga"
  border.horizontal = horizontal
  border.vertical = { 0, 9, 21, 30 }
  style.borderImage = border
  return style
end

local function selectedDirections(mode)
  local result = {}
  for _, direction in ipairs(directions) do
    result[direction.value] = mode == "all" or mode:find(direction.value, 1, true) ~= nil
  end
  return result
end

local function layoutMode(selected)
  local parts = {}
  for _, side in ipairs({ "left", "right", "front", "back" }) do
    if selected[side] then parts[#parts + 1] = side end
  end
  return #parts == 4 and "all" or table.concat(parts, "_")
end

function ui.isSupported(params)
  return params.ownershipState ~= "Foreign" and proposals.getTarget(params.entityId) ~= nil
end

ui.TidyFieldsPlugin = react.RegisterPluginRecipe(
  industry_eow.IndustryEowExtensionPoint, "XinTidyFieldsPlugin", function(params)
    local status = react.useState({ busy = false, message = "" })
    local entity, construction = proposals.getTarget(params.entityId)
    local selected = react.useState(selectedDirections(construction and construction.params.xinTidyLayout or "all"))
    if not entity then return nil end

    local function onClick()
      local mode = layoutMode(selected:old())
      if status:old().busy or mode == "" then return end
      status:set({ busy = true, message = "" })
      local ok, candidate, context, reason = pcall(proposals.make, entity, mode)
      if not ok then
        log.warning("[Tidy Fields] Could not prepare layout: " .. tostring(candidate))
        status:set({ busy = false, message = _("Could not prepare a plot layout.") })
        return
      end
      if not candidate then
        status:set({ busy = false, message = reason })
        return
      end
      local submitted, failure = pcall(function()
        api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(candidate, context, false, true), function(command, success)
          if status:hasExpired() then return end
          local message = success and _("Plots tidied.") or proposals.describeFailure(command and command.resultProposalData)
          if not success then log.warning("[Tidy Fields] Build failed: " .. message) end
          status:set({ busy = false, message = message })
        end)
      end)
      if not submitted then
        log.warning("[Tidy Fields] Could not submit layout: " .. tostring(failure))
        if not status:hasExpired() then
          status:set({ busy = false, message = _("Could not prepare a plot layout.") })
        end
      end
    end

    local controls = {}
    for index, direction in ipairs(directions) do
      controls[#controls + 1] = builtin.ToggleButton{
        meta = {
          styleSheet = directionStyle(index),
          enabled = not status:old().busy,
          tooltip = _("Click to select or deselect. Multiple directions can be selected."),
          tag = "industryWindow.tidyFields." .. direction.value,
        },
        value = selected:old()[direction.value] and 1 or 0,
        content = builtin.TextView{
          meta = { class = "font-scale-body" },
          text = _(direction.label),
        },
        onValueChange = function(value)
          local nextSelection = {}
          for side, active in pairs(selected:old()) do nextSelection[side] = active end
          nextSelection[direction.value] = value == 1
          selected:set(nextSelection)
        end,
      }
    end

    local sectionStyle = api.gui.StyleSheet.new()
    sectionStyle.padding = api.type.Vec4f.new(8, 8, 8, 8)
    local actionStyle = sizeStyle(PANEL_WIDTH, 40)
    actionStyle.padding = api.type.Vec4f.new(0, 0, 0, 0)

    return builtin.BoxLayout{
      meta = { styleSheet = sectionStyle },
      orientation = builtin.type.Orientation.Vertical,
      children = {
        builtin.BoxLayout{
          meta = { styleSheet = sizeStyle(PANEL_WIDTH, -1) },
          orientation = builtin.type.Orientation.Horizontal,
          children = {
            builtin.TextView{ meta = { class = "font-scale-headline" }, text = _("Plot layout") },
            builtin.Component{ meta = { class = "horizontal-spacer" } },
            builtin.TextView{ meta = { class = "font-scale-annotation" }, text = _("Choose directions") },
          },
        },
        spacer(8),
        builtin.BoxLayout{
          meta = {
            tooltip = _("Front is across the entrance road; back is beyond the rear. Both can extend sideways. Left and right are seen from inside looking out through the entrance. The entrance road stays clear."),
          },
          orientation = builtin.type.Orientation.Horizontal,
          children = controls,
        },
        spacer(12),
        builtin.Button{
          meta = {
            class = "primary",
            styleSheet = actionStyle,
            enabled = not status:old().busy and layoutMode(selected:old()) ~= "",
            tooltip = _("Select at least one direction, then tidy the plots. Tidy again after the industry expands."),
            tag = "industryWindow.tidyFields",
          },
          content = builtin.TextView{
            meta = { class = "font-scale-body" },
            text = status:old().busy and _("Tidying…") or _("Tidy fields"),
          },
          onClick = onClick,
        },
        status:old().message ~= "" and spacer(8) or nil,
        status:old().message ~= "" and builtin.Component{
          meta = { class = "info-hint-comp", styleSheet = sizeStyle(PANEL_WIDTH, -1) },
          layout = builtin.BoxLayout{
            child = builtin.TextView{
              meta = {
                class = "font-scale-body, info-hint-text",
                styleSheet = sizeStyle(PANEL_WIDTH - 16, -1),
                tag = "industryWindow.tidyFields.result",
              },
              text = status:old().message,
            },
          },
        } or nil,
      },
    }
  end
)

function data()
  return ui
end

return ui
