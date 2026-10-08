local react = ug_require "::/gui/main/react.lua"
local builtin = ug_require "::/gui/main/builtin.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local constructionUtil = ug_require "::/gui/construction/construction_react_util.tl"
local paramUtil = ug_require "::/scripts/construction/param_util.tl"
local bridgeChoices = ug_require "xin_smooth_rail_loop_1::/rail_loop/bridge_choices.lua"
local geometry = ug_require "xin_smooth_rail_loop_1::/rail_loop/prefab_geometry.lua"
local terrainPlan = ug_require "xin_smooth_rail_loop_1::/rail_loop/terrain_plan.lua"
local placement = ug_require "xin_smooth_rail_loop_1::/rail_loop/placement.lua"
local designPreview = ug_require "xin_smooth_rail_loop_1::/rail_loop/preview.lua"
local proposalDiagnostics = ug_require "xin_smooth_rail_loop_1::/rail_loop/proposal_diagnostics.lua"

local own = {
  ["xin_smooth_rail_loop_1::/rail_loop/raised_loop.con"] = "raised",
  ["xin_smooth_rail_loop_1::/rail_loop/lowered_loop.con"] = "lowered",
}
local nextProposalId = 0
local diagnosed = {}

local Tooltip = react.RegisterRecipe("XinRailLoopTooltip", function(params)
  return builtin.BoxLayout {
    children = { builtin.TextView { text = params.text, meta = { class = "font-scale-body" } } },
  }
end)

-- The native construction menu owns this recipe and its action binding.
-- State stays here; actionFn creates fresh nodes under one native descriptor.
local Menu = react.RegisterRecipe("XinRailLoopMenu", function(params)
  local props = react.useRef(params)
  props:set(params)
  local holder = react.useRef({ active = false })
  local model = holder:get()
  local preview = react.useState(nil)
  local overlay = react.useState(nil)
  local message = react.useState(nil)
  local fileName = params.definition.resName
  local networks = react.useRef({}):get()

  if params.isActive and (not model.active or model.fileName ~= fileName) then
    if model.session then model.session:close() end
    model.session = placement.session()
    model.fileName, model.active = fileName, true
  elseif not params.isActive and model.active then
    model.session:close()
    model.active = false
  end
  local session = model.session

  local function alive()
    return not props:hasExpired() and model.active and model.session == session
      and session ~= nil and session.live and props:get().isActive
  end
  local function setMessage(text)
    if alive() then
      local previous = message:old()
      if not previous or previous.owner ~= session or previous.text ~= text then
        message:set({ owner = session, text = text })
      end
    end
  end
  local function pose()
    if not alive() or not api.gui.mouse.hasTerrainPosition() then return nil end
    local position = api.gui.mouse.getTerrainPosition()
    local xy = api.type.Vec2f.new(position.x, position.y)
    if not api.engine.terrain.isValidCoordinate(xy) then return nil end
    local values = props:get().getCurrentParams() or {}
    local baseHeight = api.engine.terrain.getHeightAt(xy)
    local matrix = terrainPlan.pose(position.x, position.y,
      baseHeight + (tonumber(values.height) or 0), -math.rad(tonumber(values.rotation) or 0))
    local key = { fileName }
    for i = 1, 16 do key[#key + 1] = string.format("%.4f", matrix[i]) end
    local keys = {}
    for k in pairs(values) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do key[#key + 1] = k .. "=" .. tostring(values[k]) end
    return table.concat(key, ";"), matrix, values
  end
  local function sample(matrix)
    local kind = own[fileName]
    networks[kind] = networks[kind] or geometry.network(kind)
    return terrainPlan.sample(networks[kind], matrix, function(x, y)
      local xy = api.type.Vec2f.new(x, y)
      assert(api.engine.terrain.isValidCoordinate(xy), "Outside map")
      return api.engine.terrain.getHeightAt(xy)
    end)
  end
  local function makeProposal(values, matrix, plan)
    local trackTypes = paramUtil.getRailTrackTypes(values.catenary == 2)
    local index = math.max(1, math.min(#trackTypes, math.floor(tonumber(values.trackType) or 1)))
    local segments = terrainPlan.joinShortEdges(terrainPlan.apply(networks[own[fileName]], plan))
    local trackName = values.streetTemplate or trackTypes[index]
    local bridgeName = bridgeChoices.resource(values.bridgeTypeModern or values.bridgeType)
    return placement.makeProposal(api, segments, matrix, trackName, bridgeName),
      { segments=segments, matrix=matrix, trackName=trackName, bridgeName=bridgeName }
  end

  react.onStep(function()
    if not alive() or session.busy then return end
    if session.diagnostics then
      local ok, more, line = pcall(session.diagnostics, api)
      if ok and line then log.message(line) end
      if not ok then log.warning("[Rail Loop] diagnostic: " .. tostring(more)) end
      if not ok or not more then session.diagnostics = nil end
    end
    local key, matrix, values = pose()
    if not key then
      if session.key then session:replace(nil, nil); preview:set(nil); setMessage("") end
      return
    end
    if key == session.key then return end
    session:replace(key, nil)
    networks[own[fileName]] = networks[own[fileName]] or geometry.network(own[fileName])
    local drawn, design, edges = pcall(function()
      local curves = designPreview.geometry(api, networks[own[fileName]], matrix)
      return curves, designPreview.edges(api, builtin, curves)
    end)
    if drawn then
      overlay:set({ owner=session, revision=session.revision, edges=edges, source=design })
      if not session.designLogged then
        session.designLogged = true
        log.message("[Rail Loop] independent preview curves=" .. #edges)
      end
    else
      if not session.designWarning then
        session.designWarning = true
        log.warning("[Rail Loop] independent preview: " .. tostring(design))
      end
      design = nil
    end
    local sampled, plan = pcall(sample, matrix)
    local planningError
    if not sampled then
      planningError = tostring(plan):match("(地形变化过急[^\n]*)") or "无法读取该位置的地形，当前仅显示预览"
      if session.lastPlanningError ~= planningError then
        log.warning("[Rail Loop] terrain planning: " .. tostring(plan))
      end
      session.lastPlanningError = planningError
      local network = networks[own[fileName]]
      if not network then
        preview:set(nil)
        setMessage("无法生成回环轨道")
        return
      end
      plan = terrainPlan.previewPlan(network)
    else
      session.lastPlanningError = nil
    end
    session.terrainPlan = plan
    local ok, proposal, inputs = pcall(makeProposal, values, matrix, plan)
    if not ok then
      preview:set(nil)
      setMessage("无法创建施工预览，请调整放置位置")
      log.warning("[Rail Loop] proposal creation: " .. tostring(proposal))
      return
    end
    session.proposal = proposal
    nextProposalId = nextProposalId + 1
    preview:set({ owner = session, simple = proposal, revision = session.revision,
      id = "xin-rail-loop:" .. nextProposalId, planningError = planningError, design=design, inputs=inputs })
    setMessage(planningError or "")
    if not session.plannedLogged then
      session.plannedLogged = true
      log.message(string.format("[Rail Loop] direct rail proposal: %s; nodes=%d; tracks=%d; position=%.2f,%.2f,%.2f; previewOnly=%s",
        own[fileName], #proposal.streetProposal.nodesToAdd, #proposal.streetProposal.edgesToAdd,
        matrix[13], matrix[14], matrix[15], tostring(planningError ~= nil)))
    end
  end)

  local function apply()
    if not alive() or session.busy or not session.allowed then return false end
    local key, matrix = pose()
    if not key or key ~= session.key then return false end
    local sampled, latest = pcall(sample, matrix)
    if not sampled or not terrainPlan.equal(session.terrainPlan, latest) then
      session:replace(nil, nil)
      preview:set(nil)
      setMessage("地形已变化，正在更新预览")
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
      api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(prepared, context, false, true), function(result, success)
        if success and result.resultEntities then
          local entities = {}
          for _, entity in ipairs(result.resultEntities) do entities[#entities + 1] = entity[1] end
          api.gui.construction.updateRefundableEntities(entities, result.proposal.proposal)
        end
        if not alive() then return end
        session.busy = false
        session:replace(nil, nil)
        preview:set(nil)
        setMessage(success and "" or "无法建造，请调整放置位置")
      end)
    end)
    if not ok then
      session.busy, session.allowed = false, false
      setMessage("无法建造，请调整放置位置")
      log.warning("[Rail Loop] " .. tostring(errorMessage))
    end
    return true
  end

  local function abort()
    if not alive() then return end
    local callback = props:get().abort
    session:close()
    model.active = false
    callback()
  end
  react.onUnmount(function()
    model.active = false
    if model.session then model.session:close() end
  end)

  if params.isActive then
    react.setForceFocusable(true)
    react.setRestrictMouseFocus(true)
    react.useInputAction("IA_APPLY", react.iaHandler(apply, function()
      return alive() and not session.busy and session.allowed
    end))
    params.setActionFn(function()
      -- The native tool stack may invoke an old closure while changing tools.
      -- Never read expired menu state or carry old child node identities across.
      if not alive() then return builtin.ActionDescriptor { children = {} } end
      local children = {
        builtin.Selector {
          filter = function() return false end,
          onProcessMouseEvent = function(event)
            if event.type == api.gui.mouse.Event.Type.Clicked and event.button == 0 then return apply() end
            return false
          end,
        },
      }
      local candidate = preview:old()
      if candidate and candidate.owner == session then
        if not session.viewerLogged then
          session.viewerLogged = true
          log.message("[Rail Loop] proposal viewer attached")
        end
        children[#children + 1] = builtin.ProposalViewer {
          simpleProposal = candidate.simple,
          proposalId = candidate.id,
          entityForRefundableContext = api.engine.util.getPlayer(),
          onCreateProposalData = function(data, prepared)
            if not alive() or candidate.revision ~= session.revision then return end
            local errors = {}
            if candidate.planningError then errors[#errors + 1] = candidate.planningError end
            for _, value in ipairs(data.errorState.messages or {}) do errors[#errors + 1] = tostring(value) end
            local ok, issue, stats = pcall(placement.checkPrepared, prepared)
            if not ok then issue = "无法检查施工预览" end
            if issue then errors[#errors + 1] = issue end
            local balance = api.engine.util.finance.getPlayersBalance(api.engine.util.getPlayer())
            if balance and data.costs > balance then errors[#errors + 1] = _("Not Enough Money") end
            local allowed = not data.errorState.critical and #errors == 0
            if session:validated(candidate.revision, prepared, allowed) then
              local summary = tostring(allowed) .. "; " .. table.concat(errors, " | ")
              if session.overlayRevision ~= candidate.revision or session.overlaySummary ~= summary then
                session.overlayRevision, session.overlaySummary = candidate.revision, summary
                local drawn, edges, renderStats = pcall(placement.previewEdges, api, builtin, data, prepared, allowed)
                if drawn and #edges > 0 then
                  -- Keep the ProposalData alive while its geometry is rendered.
                  overlay:set({ owner = session, revision = candidate.revision, edges = edges, source = data })
                  if not session.overlayLogged then
                    session.overlayLogged = true
                    log.message(string.format("[Rail Loop] track overlay edges=%d; networks=%d; matched=%d; filtered=%d",
                      #edges, renderStats.networks, renderStats.matched, renderStats.short))
                  end
                elseif not drawn and not session.overlayWarning then
                  session.overlayWarning = true
                  log.warning("[Rail Loop] track overlay: " .. tostring(edges))
                end
                if (not drawn or #edges == 0) and candidate.design then
                  local ok, fallback = pcall(designPreview.edges, api, builtin, candidate.design, allowed)
                  if ok then
                    overlay:set({ owner=session, revision=candidate.revision, edges=fallback, source=candidate.design })
                  else
                    log.warning("[Rail Loop] preview recolor: " .. tostring(fallback))
                  end
                end
                if data.errorState.critical and not diagnosed[fileName] then
                  diagnosed[fileName] = true
                  local input = candidate.inputs
                  session.diagnostics = proposalDiagnostics.queue(placement, input.segments, input.matrix, input.trackName, input.bridgeName)
                end
              end
              if session.lastCheckSummary ~= summary then
                session.lastCheckSummary = summary
                log.message("[Rail Loop] proposal checked: allowed=" .. summary)
              end
              if not allowed and (session.detailsLogged or 0) < 3 then
                session.detailsLogged = (session.detailsLogged or 0) + 1
                local collisions = {}
                for _, item in ipairs(data.collisionInfo and data.collisionInfo.collisionEntities or {}) do
                  collisions[#collisions + 1] = tostring(item.entity)
                end
                local details = string.format("[Rail Loop] native check: critical=%s; tracks=%s; maxGrade=%s; nodes=%s; duplicateNodes=%s; collisions=%s",
                  tostring(data.errorState.critical), tostring(stats and stats.count),
                  tostring(stats and stats.maxGrade), tostring(stats and stats.nodes),
                  tostring(stats and stats.duplicateNodes), table.concat(collisions, ","))
                for _, name in ipairs({ "warnings", "infos" }) do
                  local values = {}
                  for _, value in ipairs(data.errorState[name] or {}) do values[#values + 1] = tostring(value) end
                  details = details .. "; " .. name .. "=" .. table.concat(values, " | ")
                end
                if stats and stats.worst then
                  local e = stats.worst.comp
                  details = details .. string.format("; worst=%s; p0=%.5f,%.5f,%.5f; p1=%.5f,%.5f,%.5f; t0=%.5f,%.5f,%.5f; t1=%.5f,%.5f,%.5f",
                    tostring(stats.worst.entity), e.position0.x,e.position0.y,e.position0.z,
                    e.position1.x,e.position1.y,e.position1.z,e.tangent0.x,e.tangent0.y,e.tangent0.z,
                    e.tangent1.x,e.tangent1.y,e.tangent1.z)
                end
                log.message(details)
              end
              errors[#errors + 1] = _("Cost:") .. " " .. api.util.formatMoney(data.costs)
              setMessage(table.concat(errors, "\n"))
            end
          end,
        }
      end
      local trackOverlay = overlay:old()
      if trackOverlay and trackOverlay.owner == session and trackOverlay.revision == session.revision and #trackOverlay.edges > 0 then
        children[#children + 1] = builtin.EdgeRenderable { edges = trackOverlay.edges, ignoreDepth = true }
      end
      local tooltip = message:old()
      if tooltip and tooltip.owner == session and tooltip.text ~= "" then
        children[#children + 1] = builtin.ActionTooltip { recipe = Tooltip, param = { text = tooltip.text } }
      end
      local current = props:get()
      local values = current.getCurrentParams() or {}
      local preferred = current.gameCtx.preferredLayerConfig:get()
      if preferred then
        children[#children + 1] = builtin.LayerConfig { config = preferred }
      elseif values.undergroundMode == 1 then
        local config = api.type.LayerConfig.new()
        config.undergroundMode = true
        children[#children + 1] = builtin.LayerConfig { config = config }
      end
      return builtin.ActionDescriptor {
        tool = "construction-menu-rail_constructions", onBack = abort, children = children,
      }
    end, "XinRailLoopPlacement/" .. tostring(params.definition))
  end
  return builtin.BoxLayout { children = {} }
end)

-- Decorate only our two menu items. Native action factories and renderer
-- ownership remain unchanged; the menu owns setActionFn/unbinding/identities.
local getDefinitions = constructionUtil.getConstructionDefinitions
constructionUtil.getConstructionDefinitions = function(...)
  local definitions = getDefinitions(...)
  for _, definition in ipairs(definitions) do
    if own[definition.resName] then definition.customAction = { recipe = Menu } end
  end
  return definitions
end

local entry = react.RegisterPluginRecipe(entryPoint.ModEntryPointExtension, "XinRailLoopTerrainEntry", function() return nil end)
function data() return { entry = entry } end
