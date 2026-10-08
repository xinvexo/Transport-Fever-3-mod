local react = ug_require "::/gui/main/react.lua"
local builtin = ug_require "::/gui/main/builtin.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local constructionUtil = ug_require "::/gui/construction/construction_react_util.tl"
local geometry = ug_require "xin_smooth_rail_loop_1::/rail_loop/prefab_geometry.lua"
local terrainPlan = ug_require "xin_smooth_rail_loop_1::/rail_loop/terrain_plan.lua"
local placement = ug_require "xin_smooth_rail_loop_1::/rail_loop/placement.lua"

local own = {
  ["xin_smooth_rail_loop_1::/rail_loop/raised_loop.con"] = "raised",
  ["xin_smooth_rail_loop_1::/rail_loop/lowered_loop.con"] = "lowered",
}
local controllers = {}
local mapped = setmetatable({}, { __mode = "k" })
local actionRoots, activeSessions = {}, {}
local nextId = 0

-- Keep the native item lifecycle/abort callback, without binding a replacement
-- ActionFn. The normal menu still supplies its parameter refs and key handlers.
local Lifecycle = react.RegisterRecipe("XinRailLoopLifecycle", function(params)
  if params.isActive then controllers[params.definition.resName] = params end
  react.onUnmount(function()
    if controllers[params.definition.resName] == params then controllers[params.definition.resName] = nil end
  end)
  return builtin.Component{}
end)

local Tooltip = react.RegisterRecipe("XinRailLoopTooltip", function(params)
  return builtin.TextView { text = params.text, meta = { class = "font-scale-body" } }
end)

local Action = react.RegisterRecipe("XinRailLoopTerrainPlacement", function(params)
  local inputs = react.useRef(params)
  inputs:set(params)
  local session = react.useRef(placement.session()):get()
  local preview = react.useState(nil)
  local message = react.useState("")
  local network = react.useRef({}):get()
  activeSessions[params.fileName] = session

  local function pose()
    if not api.gui.mouse.hasTerrainPosition() then return nil end
    local current = inputs:get()
    local position = api.gui.mouse.getTerrainPosition()
    local builder = current.native.constructionBuilder
    local xy = api.type.Vec2f.new(position.x, position.y)
    if not api.engine.terrain.isValidCoordinate(xy) then return nil end
    local baseHeight = api.engine.terrain.getHeightAt(xy)
    local matrix = terrainPlan.pose(position.x, position.y, baseHeight + (builder.height or 0), builder.rotation or 0)
    local values = builder.params or {}
    local key = { current.fileName }
    for i = 1, 16 do key[#key + 1] = string.format("%.4f", matrix[i]) end
    local keys = {}
    for k in pairs(values) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do key[#key + 1] = k .. "=" .. tostring(values[k]) end
    return table.concat(key, ";"), matrix, values, current
  end

  local function clear()
    if session.key then session:replace(nil, nil); preview:set(nil); message:set("") end
  end

  local function sample(current, matrix)
    local kind = own[current.fileName]
    network[kind] = network[kind] or geometry.network(kind)
    return terrainPlan.sample(network[kind], matrix, function(x, y)
      local xy = api.type.Vec2f.new(x, y)
      assert(api.engine.terrain.isValidCoordinate(xy), "Outside map")
      return api.engine.terrain.getHeightAt(xy)
    end)
  end

  react.onStep(function()
    if not session.live or session.busy then return end
    local key, matrix, values, current = pose()
    if not key then clear(); return end
    if key == session.key then return end
    session:replace(key, nil)
    local ok, proposal = pcall(function()
      local plan = sample(current, matrix)
      session.terrainPlan = plan
      return placement.makeProposal(api, current.fileName, values, matrix, plan)
    end)
    if not ok then
      preview:set(nil)
      local detail = tostring(proposal):match("(地形变化过急[^\n]*)")
      message:set(detail or "无法生成回环预览，请调整放置位置")
      log.warning("[Rail Loop] " .. tostring(proposal))
      return
    end
    session.proposal = proposal
    nextId = nextId + 1
    preview:set({ simple = proposal, revision = session.revision, id = "xin-rail-loop:" .. nextId })
    message:set("")
  end)

  local function apply()
    local key, matrix, _, current = pose()
    if not session.live or session.busy or not session.allowed or key ~= session.key then return false end
    local sampled, latest = pcall(sample, current, matrix)
    if not sampled or not terrainPlan.equal(session.terrainPlan, latest) then
      session:replace(nil, nil)
      preview:set(nil)
      message:set("地形已变化，正在更新预览")
      return true
    end
    local prepared = session:take(key)
    if not prepared then return false end
    local context = api.type.Context.new()
    context.player = api.engine.util.getPlayer()
    context.extendProposalRedoPillars = true
    local refundables = api.gui.construction.getRefundableEntities()
    if refundables then context.refundableEntities = refundables end
    local ok, errorMessage = pcall(function()
      local command = api.cmd.makeWorldBuildProposalCmd(prepared, context, false, true)
      api.cmd.sendCommand(command, function(result, success)
        if success and result.resultEntities then
          local entities = {}
          for _, entity in ipairs(result.resultEntities) do entities[#entities + 1] = entity[1] end
          api.gui.construction.updateRefundableEntities(entities, result.proposal.proposal)
        end
        if not session.live then return end
        session.busy = false
        session:replace(nil, nil)
        preview:set(nil)
        message:set(success and "" or "无法建造，请调整放置位置")
      end)
    end)
    if not ok then
      session.busy = false
      session.allowed = false
      message:set("无法建造，请调整放置位置")
      log.warning("[Rail Loop] " .. tostring(errorMessage))
    end
    return true
  end

  react.onUnmount(function()
    session:close()
    if activeSessions[params.fileName] == session then activeSessions[params.fileName] = nil end
  end)
  local native = params.native
  local inputActions = {}
  for key, value in pairs(native.inputActions or {}) do inputActions[key] = value end
  inputActions.IA_APPLY = "build"
  local children = {
    builtin.SimpleInputActions {
      inputActions = inputActions,
      inputActionsHandler = function(id)
        if id == "IA_APPLY" then apply()
        elseif inputs:get().native.inputActionsHandler then inputs:get().native.inputActionsHandler(id) end
      end,
    },
    builtin.Selector {
      filter = function() return false end, stopOnMenuBack = true,
      onProcessMouseEvent = function(event)
        if event.type == api.gui.mouse.Event.Type.Clicked and event.button == 0 then return apply() end
        return false
      end,
    },
  }
  local candidate = preview:old()
  if candidate then
    children[#children + 1] = builtin.ProposalViewer {
      simpleProposal = candidate.simple,
      proposalId = candidate.id,
      entityForRefundableContext = api.engine.util.getPlayer(),
      onCreateProposalData = function(data, prepared)
        if not session.live or candidate.revision ~= session.revision then return end
        local errors = {}
        for _, value in ipairs(data.errorState.messages or {}) do errors[#errors + 1] = tostring(value) end
        local ok, issue = pcall(placement.checkPrepared, prepared)
        if not ok then issue = "无法检查施工预览" end
        if issue then errors[#errors + 1] = issue end
        local balance = api.engine.util.finance.getPlayersBalance(api.engine.util.getPlayer())
        if balance and data.costs > balance then errors[#errors + 1] = _("Not Enough Money") end
        local allowed = not data.errorState.critical and #errors == 0
        if session:validated(candidate.revision, prepared, allowed) then
          errors[#errors + 1] = _("Cost:") .. " " .. api.util.formatMoney(data.costs)
          message:set(table.concat(errors, "\n"))
        end
      end,
    }
  end
  if message:old() ~= "" then
    children[#children + 1] = builtin.ActionTooltip { recipe = Tooltip, param = { text = message:old() } }
  end
  return builtin.FloatingLayout { children = children }
end)

local getDefinitions = constructionUtil.getConstructionDefinitions
constructionUtil.getConstructionDefinitions = function(...)
  local definitions = getDefinitions(...)
  for _, definition in ipairs(definitions) do
    if own[definition.resName] then definition.customAction = { recipe = Lifecycle } end
  end
  return definitions
end

local getActionParams = constructionUtil.getActionParams
constructionUtil.getActionParams = function(definition, ...)
  local result = getActionParams(definition, ...)
  if definition and own[definition.resName] and result.constructionActionParams.constructionBuilder then
    mapped[result.constructionActionParams] = definition.resName
  end
  return result
end

local nativeAction = builtin.ConstructionAction
builtin.ConstructionAction = function(params)
  local fileName = mapped[params]
  if fileName then
    local node = Action { native = params, fileName = fileName }
    actionRoots[node] = fileName
    return node
  end
  return nativeAction(params)
end

-- Add cancellation to the existing outer descriptor instead of nesting a
-- second one. Only a direct child created above is eligible for this hook.
local nativeDescriptor = builtin.ActionDescriptor
builtin.ActionDescriptor = function(params)
  if type(params) == "table" then
    for _, child in ipairs(params.children or {}) do
      local fileName = actionRoots[child]
      if fileName then
        actionRoots[child] = nil
        local previousBack = params.onBack
        params.onBack = function()
          local session = activeSessions[fileName]
          if session then session:close() end
          local controller = controllers[fileName]
          if controller then controller.abort() elseif previousBack then previousBack() end
        end
        break
      end
    end
  end
  return nativeDescriptor(params)
end

local entry = react.RegisterPluginRecipe(entryPoint.ModEntryPointExtension, "XinRailLoopTerrainEntry", function() return nil end)
function data() return { entry = entry } end
