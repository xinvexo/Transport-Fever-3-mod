local builtin = ug_require "::/gui/main/builtin.lua"
local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local globals = ug_require "::/gui/main/game_react_globals.tl"
local engine = ug_require "::/gui/main/engine_react_util.tl"
local lineUI = ug_require "::/gui/line_vehicle_mgmt/line_react_util.tl"
local lines = ug_require "xin_bulldozer_lines_1::/bulldozer_lines/lines.lua"
local construction = ug_require "::/gui/construction/construction_react_util.tl"
local buildingColors = ug_require "xin_bulldozer_lines_1::/bulldozer_lines/building_colors.lua"

local nativeGetActionParams = construction.getActionParams
construction.getActionParams = function(definition, ...)
  return buildingColors.apply(definition, nativeGetActionParams(definition, ...))
end

local currentSession
local resetWindowPosition = true
local LineWindow
LineWindow = react.RegisterWrapperRecipe("XinBulldozerLineWindow", builtin.Window, function(params)
  local selected = react.useMirrorState(params.selected)
  local all = react.useMirrorState(params.lines)
  local filters = react.useMirrorState(params.filters)
  local search = react.useState("")
  react.onMount(function()
    if resetWindowPosition then
      api.gui.byId.resetMovedWindowPosition("xin.bulldozer.lines")
      resetWindowPosition = false
    end
  end)

  local function filterChanged(key, value)
    if params.filters:hasExpired() then return end
    params.filters:transform(function(previous) return lines.setFilter(previous, key, value == 1) end)
  end
  local buttons = {}
  for __, category in ipairs(lines.categories) do
    local key = category.key
    buttons[#buttons + 1] = builtin.ToggleButton{
      meta = { localKey = key, tooltip = _(category.tooltip) },
      value = filters:old().carriers[key] and 1 or 0,
      content = builtin.ImageView{ path = category.icon, scaling = builtin.type.ImageViewScaling.AutoFit },
      onValueChange = function(value) filterChanged(key, value) end,
    }
  end
  buttons[#buttons + 1] = builtin.ToggleButton{
    meta = { localKey = "onlyVisible", tooltip = _("Show only visible lines") },
    value = filters:old().onlyVisible and 1 or 0,
    content = builtin.ImageView{
      path = "::/gui/statistics/icons/symbol_eye_18.tga", scaling = builtin.type.ImageViewScaling.AutoFit,
    },
    onValueChange = function(value) filterChanged("onlyVisible", value) end,
  }
  local shown = lines.search(lines.filter(all:old(), filters:old()), search:old())
  local allCheckbox = builtin.CheckBox{
    meta = { localKey = "select-all", enabled = #shown > 0, tooltip = _("Select displayed lines") },
    value = lines.selectionValue(shown, selected:old()),
    triStateSupport = false,
    onValueChange = function()
      if params.selected:hasExpired() then return end
      params.selected:transform(function(previous) return lines.toggleAll(shown, previous) end)
    end,
  }
  local rows = {}
  for __, line in ipairs(shown) do
    if api.engine.entityExists(line.entity) then
      local entity = line.entity
      local function toggleLine()
        if params.selected:hasExpired() then return end
        params.selected:transform(function(previous)
          return lines.setChecked(previous, entity, not previous[entity])
        end)
      end
      rows[#rows + 1] = builtin.Button{
        meta = {
          localKey = tostring(entity),
          class = "bl-row" .. (selected:old()[entity] and ", selected" or ""),
        },
        onClick = toggleLine,
        content = builtin.BoxLayout{
          orientation = builtin.type.Orientation.Horizontal,
          children = {
            builtin.CheckBox{
              meta = { localKey = "line-check-" .. tostring(entity) },
              value = selected:old()[entity] and 1 or 0,
              onValueChange = function(value)
                if params.selected:hasExpired() then return end
                params.selected:transform(function(previous)
                  return lines.setChecked(previous, entity, value == 1)
                end)
              end,
            },
            lineUI.ColorWidget{ entity = entity },
            builtin.Button{
              meta = { class = "bl-name" },
              content = builtin.TextView{ meta = { class = "font-scale-body" }, text = line.name },
              onClick = toggleLine,
            },
            lineUI.LocateButton{
              entity = entity, tooltip = _("Locate Line"),
              iconPathOverride = "::/gui/line_vehicle_mgmt/icons/symbol_locate_20.tga",
            },
          },
        },
      }
    end
  end
  if #rows == 0 then rows[1] = builtin.TextView{ text = _("No matching lines") } end

  return builtin.Window{
    id = "xin.bulldozer.lines",
    title = _("Lines while bulldozing"),
    -- Native Window positions are fractions of the viewport, not pixels.
    initialX = params.initialX or 0.018, initialY = params.initialY or 0.18,
    compact = true, movable = true, closable = true,
    autoFocusOnBecomingVisible = false,
    autoVisibilityOnFocusChange = false,
    onClose = params.onClose,
    content = builtin.BoxLayout{
      meta = { class = "bl-content" },
      orientation = builtin.type.Orientation.Vertical,
      children = {
        builtin.TextInputField{
          placeholderText = _("Search..."),
          value = search:old(),
          onTyping = function(value) search:set(value) end,
          onValueChange = function(value) search:set(value) end,
          onCancel = function() search:set("") end,
          maxLength = 100,
        },
        builtin.Component{
          meta = { class = "bl-card" },
          layout = builtin.BoxLayout{
            orientation = builtin.type.Orientation.Vertical,
            children = {
              builtin.FloatingLayout{
                meta = { class = "bl-header" },
                children = {
                  builtin.FloatingLayoutChild{ h = 0, v = 0.5, item = allCheckbox },
                  builtin.FloatingLayoutChild{
                    h = 0.5, v = 0.5,
                    item = builtin.BoxLayout{
                      meta = { class = "bl-filters" },
                      orientation = builtin.type.Orientation.Horizontal, children = buttons,
                    },
                  },
                },
              },
              builtin.List{
                meta = { class = "bl-list" },
                children = rows,
                orientation = builtin.type.Orientation.Vertical,
                behavior = builtin.type.ListBehavior.Default,
                selectionIndex = -1,
                deselectAllowed = true, cycle = false,
                horizontalScrollBarPolicy = builtin.type.ScrollBarPolicy.AsNeeded,
                verticalScrollBarPolicy = builtin.type.ScrollBarPolicy.AsNeeded,
              },
            },
          },
        },
      },
    },
  }
end)

-- This is an ordinary Lua helper, not a recipe. The native action collector
-- requires native configuration nodes created in the current ActionFn render.
local function makeLineViewer(session)
  local selected = react.useMirrorState(session.selected)
  local all = react.useMirrorState(session.lines)
  local filters = react.useMirrorState(session.filters)
  local visualizations = {}
  for _, line in ipairs(lines.select(all:old(), selected:old(), filters:old())) do
    local visual = builtin.type.LineVisualization.new()
    visual.entity = line.entity
    visual.transparency = 1.0
    visualizations[#visualizations + 1] = visual
  end
  -- The native viewer interprets an empty list as "all lines".
  if #visualizations == 0 then return nil end
  return builtin.LineViewer{
    selectable = false,
    showLines = visualizations,
    hiddenLinesTransparent = false,
    showTerminals = false,
    fadingMinHeight = 0.0,
    fadingDeltaHeight = 0.0,
  }
end

local nativeActionDescriptor = builtin.ActionDescriptor
builtin.ActionDescriptor = function(...)
  -- Keep optional recipe style/ref arguments and all original action children.
  local args = table.pack(...)
  local params = args[args.n]
  local session = currentSession
  if type(params) == "table" and params.tool == "construction-menu-bulldozer"
    and session and not session.selected:hasExpired() and not session.lines:hasExpired()
    and not session.filters:hasExpired() then
    local updated, children = {}, {}
    for key, value in pairs(params) do updated[key] = value end
    for key, value in pairs(params.children or {}) do children[key] = value end
    local viewer = makeLineViewer(session)
    if viewer then children[#children + 1] = viewer end
    updated.children = children
    args[args.n] = updated
  end
  return nativeActionDescriptor(table.unpack(args, 1, args.n))
end

local entry = react.RegisterPluginRecipe(
  entryPoint.ModEntryPointExtension, "XinBulldozerLinesEntry", function()
    local selected = react.useState({})
    local filters = react.useState({ carriers = {}, onlyVisible = false })
    local all = engine.useStepStateTimer(function() return lines.read(filters:old()) end, 0.5)
    local sessionRef = react.useRef({
      selected = selected, lines = all, filters = filters, active = false, closed = false, windowOpen = false,
    })
    local session = sessionRef:get()
    currentSession = session

    local function closeWindow()
      local windows = globals.getDefaultWindowApi()
      if windows and session.windowOpen then windows.removeAllWindows(LineWindow) end
      session.windowOpen = false
    end
    react.onStep(function()
      if currentSession ~= session then return end
      local stack = globals.getDefaultToolStackApi()
      local tool, variant
      if stack then tool, variant = stack.getActiveTool() end
      local active = tool ~= nil and tool.name == "Construction" and variant == "bulldozer"
      if active ~= session.active then
        session.active = active
        session.closed = false
        if active then selected:set({}) else closeWindow() end
      end
      if active and not session.closed and not session.windowOpen then
        local windows = globals.getDefaultWindowApi()
        if windows then
          windows.addSingletonWindow(LineWindow, {
            initialX = 0.018, initialY = 0.18,
            selected = selected, lines = all, filters = filters,
            onClose = function()
              if currentSession ~= session then return end
              session.closed = true
              closeWindow()
              local stackApi = globals.getDefaultToolStackApi()
              local activeTool, activeVariant
              if stackApi then activeTool, activeVariant = stackApi.getActiveTool() end
              if activeTool and activeTool.name == "Construction" and activeVariant == "bulldozer" then
                api.gui.fireReactEvent("closeConstructionWindow")
              end
            end,
          })
          session.windowOpen = true
        end
      end
    end)
    react.onUnmount(function()
      if currentSession ~= session then return end
      closeWindow()
      currentSession = nil
    end)
    return nil
  end
)
log.message("[Bulldozer Lines] Native-style line list and linked bulldozer close loaded (revision 7).")

function data()
  return { entry = entry }
end
