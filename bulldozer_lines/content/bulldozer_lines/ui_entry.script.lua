local builtin = ug_require "::/gui/main/builtin.lua"
local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local globals = ug_require "::/gui/main/game_react_globals.tl"
local engine = ug_require "::/gui/main/engine_react_util.tl"
local lineUI = ug_require "::/gui/line_vehicle_mgmt/line_react_util.tl"
local lines = ug_require "xin_bulldozer_lines_1::/bulldozer_lines/lines.lua"
local construction = ug_require "::/gui/construction/construction_react_util.tl"
local buildingColors = ug_require "xin_bulldozer_lines_1::/bulldozer_lines/building_colors.lua"

local buildingColorsFailed = false
local nativeGetActionParams = construction.getActionParams
construction.getActionParams = function(definition, ...)
  local original = nativeGetActionParams(definition, ...)
  if buildingColorsFailed or not definition or definition.action ~= "ACTION_BULLDOZER" then return original end
  local ok, result = pcall(buildingColors.apply, definition, original)
  if ok then return result end
  -- This hook is shared by every construction tool. A failed visual enhancement
  -- must leave the native action usable and must not fail again every render.
  buildingColorsFailed = true
  log.message("[Bulldozer Lines] Building colors disabled until reload: " .. tostring(result))
  return original
end

local currentSession
local resetWindowPosition = true
local refreshEvent = "xin.bulldozer.lines.changed"
local collectingAction

local function isBulldozerActive()
  local stack = globals.getDefaultToolStackApi()
  local tool, variant
  if stack then tool, variant = stack.getActiveTool() end
  return tool ~= nil and tool.name == "Construction" and variant == "bulldozer"
end

-- DataTable only passes userParam to NEW cells. Keep state handles in it;
-- selection, filtering and renaming must also update cells already on screen.
local LineRow = react.RegisterRecipe("XinBulldozerLineRow", function(params)
  local user, entity = params.userParam, params.rowKey
  local selected = react.useDependentState(user.selected, function(_, selection) return selection[entity] == true end)
  local row = react.useDependentState(user.rows, function(_, values) return values[entity] end)
  if not row:old() or not api.engine.entityExists(entity) then return builtin.Component{} end

  local function setChecked(value)
    if not user.isCurrent() or user.selected:hasExpired() or not api.engine.entityExists(entity) then return end
    user.selected:transform(function(previous)
      return lines.setChecked(previous, entity, value)
    end)
  end
  local function toggleLine()
    if not user.isCurrent() or user.selected:hasExpired() then return end
    setChecked(not user.selected:old()[entity])
  end
  local name, index = row:old().name, row:old().index
  return builtin.Button{
    meta = { class = "bl-row" .. (index % 2 == 0 and ", alternate" or "")
      .. (selected:old() and ", selected" or "") },
    onClick = toggleLine,
    content = builtin.TableLayout{
      meta = { class = "bl-row-layout" },
      columnWeights = { 0, 0, 1, 0 },
      rows = { builtin.Row{ cells = {
        builtin.CheckBox{
          meta = { class = "bl-check", localKey = "line-check-" .. tostring(entity) },
          value = selected:old() and 1 or 0,
          onValueChange = function(value) setChecked(value == 1) end,
        },
        lineUI.ColorWidget{ meta = { class = "bl-color" }, entity = entity },
        builtin.TextView{
          meta = { class = "bl-name, font-scale-body" },
          text = name, tooltipWhenClipped = name,
        },
        lineUI.LocateButton{
          meta = { class = "bl-locate" }, entity = entity, tooltip = _("Locate Line"),
          iconPathOverride = "::/gui/line_vehicle_mgmt/icons/symbol_locate_20.tga",
        },
      } } },
    },
  }
end)

local LineWindow
LineWindow = react.RegisterWrapperRecipe("XinBulldozerLineWindow", builtin.Window, function(params)
  local selected = react.useMirrorState(params.selected)
  local all = react.useMirrorState(params.lines)
  local filters = react.useMirrorState(params.filters)
  local search = react.useState("")
  local rowData = react.useRef({})
  react.onMount(function()
    if resetWindowPosition then
      api.gui.byId.resetMovedWindowPosition("xin.bulldozer.lines")
      resetWindowPosition = false
    end
  end)

  local function filterChanged(key, value)
    if not params.isCurrent() or params.filters:hasExpired() then return end
    params.filters:transform(function(previous)
      local nextFilters = lines.setFilter(previous, key, value == 1)
      if nextFilters ~= previous then
        -- Recompute once at the filter event, so the table and map can share
        -- the snapshot immediately, without waiting for the camera refresh.
        params.lines:set(lines.read(nextFilters, params.lines:old()))
      end
      return nextFilters
    end)
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
    meta = { class = "bl-check", localKey = "select-all", enabled = #shown > 0, tooltip = _("Select displayed lines") },
    value = lines.selectionValue(shown, selected:old()),
    triStateSupport = false,
    onValueChange = function()
      if not params.isCurrent() or params.selected:hasExpired() then return end
      params.selected:transform(function(previous) return lines.toggleAll(shown, previous) end)
    end,
  }
  local rowKeys = {}
  for index, line in ipairs(shown) do
    rowKeys[index] = line.entity
  end
  local nextRows = lines.rows(shown, rowData:get())
  if nextRows ~= rowData:get() then rowData:set(nextRows) end
  local function setSearch(value)
    if params.isCurrent() and not search:hasExpired() and search:old() ~= value then search:set(value) end
  end

  return builtin.Window{
    id = "xin.bulldozer.lines",
    title = _("Lines while bulldozing"),
    -- Native Window positions are fractions of the viewport, not pixels.
    initialX = params.initialX or 0.018, initialY = params.initialY or 0.18,
    compact = true, movable = true, closable = true,
    autoFocusOnBecomingVisible = false,
    autoVisibilityOnFocusChange = false,
    onClose = params.onClose,
    content = builtin.Component{
      meta = { class = "bl-content" },
      layout = builtin.BoxLayout{
        orientation = builtin.type.Orientation.Vertical,
        children = {
          builtin.TextInputField{
            placeholderText = _("Search..."),
            value = search:old(),
            onTyping = setSearch, onValueChange = setSearch,
            onCancel = function() setSearch("") end,
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
                builtin.DataTable{
                  meta = { localKey = "line-table", class = "bl-list" .. (#rowKeys == 0 and ", empty" or "") },
                  disableSortKey = true,
                  columns = { builtin.ColumnDesc{ name = _("Name"), recipe = LineRow, weight = 1.0 } },
                  rowKeys = rowKeys,
                  userParam = { selected = params.selected, rows = rowData, isCurrent = params.isCurrent },
                  scrollPolicyHorizontal = builtin.type.ScrollBarPolicy.AlwaysOff,
                  scrollPolicyVertical = builtin.type.ScrollBarPolicy.AsNeededButAlwaysReserveSpace,
                },
                #rowKeys == 0 and builtin.TextView{
                  meta = { class = "bl-empty" }, text = _("No matching lines"),
                } or nil,
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
  local visualizations = {}
  for _, line in ipairs(lines.select(session.lines:old(), session.selected:old(), session.filters:old())) do
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

-- Construction initially renders the default selector, then its bulldozer.
-- Hooks added inside ActionDescriptor would reuse the selector's useRef(-1)
-- slot. Reserve ONE stable state before the native ActionFn on every render.
-- All native configuration nodes still belong to the original ActionFn.
local nativeActionFn = builtin.ActionFn
builtin.ActionFn = function(...)
  local args = table.pack(...)
  local params = args[args.n]
  local updated = {}
  for key, value in pairs(params) do updated[key] = value end
  updated.fn = function()
    local revision = react.useState(0)
    local owner = { bulldozer = false }
    react.onEvent(refreshEvent, function()
      if owner.bulldozer and not revision:hasExpired() and isBulldozerActive() then
        revision:transform(function(value) return value + 1 end)
      end
    end)
    local previous = collectingAction
    collectingAction = owner
    local result = params.fn and params.fn() or nil
    collectingAction = previous
    return result
  end
  args[args.n] = updated
  return nativeActionFn(table.unpack(args, 1, args.n))
end

local nativeActionDescriptor = builtin.ActionDescriptor
builtin.ActionDescriptor = function(...)
  -- Keep optional recipe style/ref arguments and all original action children.
  local args = table.pack(...)
  local params = args[args.n]
  local session = currentSession
  if collectingAction and type(params) == "table" and params.tool == "construction-menu-bulldozer" then
    collectingAction.bulldozer = true
  end
  if type(params) == "table" and params.tool == "construction-menu-bulldozer"
    and session and session.active and not session.closed
    and not session.selected:hasExpired() and not session.lines:hasExpired()
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
    local sessionRef = react.useRef({ active = false, closed = false, windowOpen = false })
    local session = sessionRef:get()
    -- Retain the existing native snapshot timer for camera-dependent filters,
    -- but do no line-system work at all while the bulldozer is inactive.
    local all = engine.useStepStateTimer(function(previous)
      if session.active and not session.closed then return lines.read(filters:old(), previous) end
      return previous and #previous == 0 and previous or {}
    end, 0.5, function(a, b) return a == b end)
    session.selected, session.lines, session.filters = selected, all, filters
    currentSession = session

    local function closeWindow()
      local windows = globals.getDefaultWindowApi()
      local wasOpen = session.windowOpen
      session.windowOpen = false
      session.windowToken = nil
      if windows and wasOpen then windows.removeAllWindows(LineWindow) end
    end
    local function syncWindow()
      if currentSession ~= session then return end
      local active = isBulldozerActive()
      if active ~= session.active then
        session.active = active
        session.closed = false
        if active then
          session.lastRefresh = nil
          selected:set({})
          all:set(lines.read(filters:old()))
        else closeWindow() end
      end
      if active and not session.closed and not session.windowOpen then
        local windows = globals.getDefaultWindowApi()
        if windows then
          local token = {}
          session.windowToken, session.windowOpen = token, true
          local function isCurrent()
            return currentSession == session and session.windowToken == token and session.windowOpen
          end
          windows.addSingletonWindow(LineWindow, {
            initialX = 0.018, initialY = 0.18,
            selected = selected, lines = all, filters = filters,
            isCurrent = isCurrent,
            onClose = function()
              if not isCurrent() then return end
              session.closed = true
              closeWindow()
              if isBulldozerActive() then
                react.fireEvent(nil, "closeConstructionWindow")
              end
            end,
          })
        end
      end
    end
    react.onMount(syncWindow)
    react.onEvent("constructionMenuActive", function(_, event)
      if currentSession ~= session then return end
      if event and not event.active then
        session.active, session.closed = false, false
        closeWindow()
      else syncWindow() end
    end)
    -- State changes (including the existing camera snapshot) redraw the action
    -- through its fixed hook, never by adding hooks to a conditional descriptor.
    if session.active and not session.closed then
      local last = session.lastRefresh
      if not last or last.selected ~= selected:old() or last.lines ~= all:old() or last.filters ~= filters:old() then
        session.lastRefresh = { selected = selected:old(), lines = all:old(), filters = filters:old() }
        react.fireEvent(nil, refreshEvent)
      end
    end
    react.onUnmount(function()
      if currentSession ~= session then return end
      currentSession = nil
      closeWindow()
      react.fireEvent(nil, refreshEvent)
    end)
    return nil
  end
)
log.message("[Bulldozer Lines] Native name sorting and dependent table rows loaded (revision 10).")

function data()
  return { entry = entry }
end
