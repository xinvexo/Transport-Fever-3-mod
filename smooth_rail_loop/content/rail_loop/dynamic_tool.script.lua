local react = require "::/gui/main/react.lua"
local builtin = require "::/gui/main/builtin.lua"
local proposalUtil = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_proposal.lua"
local enum = api.type["enum"]
local constructionUtil = ug_require "::/gui/construction/construction_react_util.tl"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local toolbarApi

local function nativeValues(params)
  -- CustomAction.getCurrentParams reads the separate Default-param cache.
  -- Toolbar controls have their own API; use the API received by onChangeFn.
  return toolbarApi and toolbarApi.getCurrentParams() or params.getCurrentParams() or {}
end

local function currentOptions(params, state)
  local values = nativeValues(params)
  return {extension = state and state.extension or 0, elevation = values.height or 0,
    direction = state and state.direction or 1, bend = values.bend or 0,
    bridgeType = values.bridgeType, tunnelType = values.tunnelType,
    trackTemplate = params.definition.resName, snapping = values.disableSnapping ~= 2,
    underground = values.undergroundMode == 1}
end
local function optionKey(o)
  return table.concat({o.extension,o.elevation,o.direction,o.bend,
    o.bridgeType or -1,o.tunnelType or -1,o.trackTemplate or "",tostring(o.underground)}, ":")
end
local function errorMessage(err) return tostring(err):gsub("^.-:%d+: ", "") end

-- ActionFn must create ActionDescriptor directly in its own recipe context.
-- RegisterRecipe around this function triggers a native fatal assertion.
local function Tool(params)
  local state = react.useRef({points = {}, serial = 0, busy = false,
    message = "① 点击第一条轨道上的连接点"})
  local tick = react.useState(0)
  local s = state:get()
  if not s.loggedEntry then
    s.loggedEntry = true
    log.message("[Rail Loop] Tool entered: "..params.definition.resName)
  end
  local function refresh() if not state:hasExpired() then tick:set(tick:old()+1) end end
  local function invalidate()
    s.serial = s.serial+1;s.ready = false;s.proposal = nil;s.price = nil;s.info = nil
  end
  local function reset()
    if s.busy then return end
    invalidate();s.points = {};s.extension = 0;s.direction = 1;s.pendingShape = nil;s.message = "① 点击第一条轨道上的连接点";refresh()
  end
  local function recompute()
    invalidate()
    local opts = currentOptions(params,s)
    s.optionKey = optionKey(opts)
    if #s.points == 2 then
      local ok,proposal,info = pcall(proposalUtil.make,s.points[1],s.points[2],opts)
      if ok then s.proposal = proposal;s.info = info;s.message = "正在检查施工预览……"
      else s.message = errorMessage(proposal);log.message("[Rail Loop] Preview failed: "..s.message) end
    end
    refresh()
  end
  local build
  local function pick(entity,indices,details)
    if s.busy then return true end
    if #s.points == 2 then if s.ready then build() end;return true end
    local ok,point = pcall(proposalUtil.pick,entity,details,s.mouse,currentOptions(params,s).snapping)
    if not ok then s.message = errorMessage(point);log.message("[Rail Loop] Pick failed: "..s.message);refresh();return true end
    if #s.points == 1 and point.entity == s.points[1].entity then
      s.message = "请选择另一条轨道上的连接点";refresh();return true
    end
    s.points[#s.points+1] = point
    log.message("[Rail Loop] Point "..#s.points..": entity="..entity)
    if #s.points == 2 then recompute()
    else s.message = "② 点击另一条轨道上的连接点";refresh() end
    return true
  end
  build = function()
    if s.busy or not s.ready or not s.proposal then return end
    if optionKey(currentOptions(params,s))~=s.optionKey then recompute();return end
    if not proposalUtil.current(s.points[1]) or not proposalUtil.current(s.points[2]) then recompute();return end
    local balance = api.engine.util.finance.getPlayersBalance(api.engine.util.getPlayer())
    if balance and s.price and s.price>balance then s.message = "资金不足";refresh();return end
    local context = api.type.Context.new()
    context.player = api.engine.util.getPlayer()
    local refunds = api.gui.construction.getRefundableEntities()
    if refunds then context.refundableEntities = refunds end
    s.busy = true;s.ready = false;s.message = "正在建造……";refresh()
    local ok,err = pcall(function()
      api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(s.proposal,context,false,true),function(data,success)
        if success then
          local valid = {}
          for _,entry in ipairs(data.resultEntities or {}) do
            if api.engine.entityExists(entry[1]) then valid[#valid+1] = entry[1] end
          end
          api.gui.construction.updateRefundableEntities(valid,data.proposal.proposal)
        end
        if state:hasExpired() then return end
        s.busy = false
        if success then reset();s.message = "已建造。可以继续选择下一组连接点。"
        else invalidate();s.message = "施工未成功，请调整长度或重新选点后重试。" end
        refresh()
      end)
    end)
    if not ok then s.busy = false;s.message = errorMessage(err);refresh() end
  end
  react.onStep(function()
    if s.busy then return end
    if #s.points>0 then
      for _,p in ipairs(s.points) do
        if not proposalUtil.current(p) then reset();s.message = "轨道已改变，请重新选点。";refresh();return end
      end
    end
    s.frame = (s.frame or 0)+1
    if s.pendingShape and s.frame%8==0 then
      s.extension,s.direction = s.pendingShape[1],s.pendingShape[2]
      s.pendingShape = nil
    end
    if optionKey(currentOptions(params,s))~=s.optionKey then recompute() end
  end)
  local children = {
    builtin.Selector{
      filter = proposalUtil.isTrack,
      onProcessMouseEvent = function(event)
        s.mouse = {x=event.x,y=event.y}
        if #s.points==2 and not s.busy and api.gui.mouse.hasTerrainPosition() then
          local p = api.gui.mouse.getTerrainPosition()
          local a,b = s.points[1],s.points[2]
          local n = math.sqrt(a.t[1]^2+a.t[2]^2)
          local distance = ((p.x-(a.p[1]+b.p[1])/2)*a.t[1]+(p.y-(a.p[2]+b.p[2])/2)*a.t[2])/n
          -- Mouse movement controls length, as in native laying; no extra slider.
          local extension = math.min(800,math.floor(math.max(0,math.abs(distance)-180)/5)*5)
          local direction = distance<0 and 2 or 1
          if extension~=(s.extension or 0) or direction~=(s.direction or 1) then
            s.pendingShape = {extension,direction};s.ready = false
          end
        end
        -- Empty terrain is not a selectable track entity. Handle confirmation
        -- here too so extending the loop does not require clicking a rail again.
        if not event.handled and event.type==api.gui.mouse.Event.Type.Clicked then
          if event.button==0 and #s.points==2 then build();return true end
          if event.button==2 and #s.points>0 then reset();return true end
        end
        return false
      end,
      onSelect = pick,
      onSelectSecondary = function() reset();return true end,
      selectionColor = api.type.Vec4f.new(0.1,0.9,0.8,0.4),
      selectionOutlineColor = api.type.Vec4f.new(0.1,0.9,0.8,0.8),
      selectionOutlineColor1 = api.type.Vec4f.new(0.1,0.9,0.8,1),
    },
  }
  if s.proposal then
    local serial = s.serial
    children[#children+1] = builtin.ProposalViewer{
      simpleProposal = s.proposal,
      entityForRefundableContext = api.engine.util.getPlayer(),
      proposalId = "xin-dynamic-loop:"..tostring(s)..":"..serial,
      onCreateProposalData = function(data)
        if state:hasExpired() or s.serial~=serial or s.busy then return end
        s.price = data.costs
        local errors = data.errorState
        s.ready = not s.pendingShape and not errors.critical and #errors.messages==0
        s.message = s.ready and "移动鼠标调整长度；用原高度、弯曲和桥隧选项调整，单击确认。" or table.concat(errors.messages,"\n")
        if not s.ready and s.message=="" then s.message = "当前位置无法施工，请调整长度或方向。" end
        refresh()
      end,
    }
  end
  local message = s.message
  if s.info then message = message..string.format("\n长度 %.0f m",s.info.length) end
  children[#children+1] = builtin.ActionTooltip{
    recipe = constructionUtil.SimpleTooltipRecipe,
    param = {message = {message=message,bad=s.proposal~=nil and not s.ready,good=s.ready or false},cost=s.price},
  }
  local layer = api.type.LayerConfig.new()
  layer.undergroundMode = currentOptions(params,s).underground
  children[#children+1] = builtin.LayerConfig{config=layer}
  react.useInputAction("IA_APPLY",react.iaHandler(build,function() return s.ready and not s.busy end,"建造回环"))
  react.useInputAction("IA_ABORT",react.iaHandler(reset,function() return #s.points>0 and not s.busy end,"重新选点"))
  -- Reuse the native parameter APIs and step functions for native shortcuts.
  local function step(key,direction)
    local menuApi = toolbarApi
    local p = menuApi and menuApi.getParamByKey(key)
    if p and p.param.stepValueFn then
      local precise = api.gui.inputAction.modifierOnlyActionIsActive("IA_PRECISION_MODE")
      menuApi.changeParam(p.index,p.param.stepValueFn(p.value,direction,precise))
    end
  end
  for _,binding in ipairs({{"constructRaise","height",1},{"constructLower","height",-1},
      {"constructOpt1","bend",1},{"constructOpt2","bend",-1},{"IA_CHANGE_BUILD_MODE","mode",1},
      {"IA_UNDERGOUND_MODE_TOGGLE","undergroundMode",1}}) do
    local key,dir = binding[2],binding[3]
    react.useInputAction(binding[1],react.iaHandler(function() step(key,dir) end))
  end
  return builtin.ActionDescriptor{
    tool = "construction-menu-tracks",terrainCirclePolicy = "Never",
    highlightedEntities = #s.points>0 and {s.points[1].entity,s.points[2] and s.points[2].entity or s.points[1].entity} or {},
    onBack = function() if #s.points>0 then reset() else params.abort() end end,
    children = children,
  }
end

local Register = react.RegisterRecipe("XinNativeRailLoopMode",function(params)
  local bound = react.useRef(nil)
  local function sync()
    local enabled = params.isActive and nativeValues(params).mode==3
    local previous = bound:get()
    if previous and previous.enabled==enabled and previous.definition==params.definition then return end
    bound:set({enabled=enabled,definition=params.definition})
    log.message("[Rail Loop] Mode binding: "..params.definition.resName.." enabled="..tostring(enabled).." mode="..tostring(nativeValues(params).mode))
    if enabled then
      params.setActionFn(function() return Tool(params) end,"xin-native-rail-loop:"..params.definition.resName)
    else params.setActionFn(nil) end
  end
  react.onStep(sync)
  sync()
end)

local nativeDefinitions = constructionUtil.getTrackDefinitions
constructionUtil.getTrackDefinitions = function(...)
  local definitions = nativeDefinitions(...)
  for _,definition in ipairs(definitions) do
    -- Preserve another mod's custom interaction if one is already installed.
    if not definition.customAction then
      for _,p in ipairs(definition.params or {}) do
        local key = p.key
        local oldChange = p.onChangeFn
        p.onChangeFn = function(value,menuApi,oldValue)
          -- One native Toolbar instance follows the active track definition.
          -- Its values persist when the user switches rail types.
          toolbarApi = menuApi
          if key=="mode" then log.message("[Rail Loop] Toolbar mode="..tostring(value)) end
          if oldChange then oldChange(value,menuApi,oldValue) end
        end
        if key=="mode" then
          p.values[#p.values+1] = "xin_smooth_rail_loop_1::/rail_loop/loop.tga"
          p.tooltips[#p.tooltips+1] = "两点回环：选择两条轨道，移动鼠标定长度"
          p.stepValueFn = function(value,direction) return ((value-1+direction)%3)+1 end
        elseif p.checkEnabledFn then
          local oldCheck = p.checkEnabledFn
          p.checkEnabledFn = function(values)
            if values.mode~=3 then return oldCheck(values) end
            if key=="terrainMode" or key=="trackAlignToTerrain" then return "Disabled" end
            -- A return loop must preserve both endpoint heights. Fixed incline
            -- cannot replace its rise-and-fall profile; use the existing height.
            local native = {};for k,v in pairs(values) do native[k]=v end
            native.mode=1;native.terrainMode=1
            return oldCheck(native)
          end
        end
      end
      definition.customAction = {recipe=Register}
    end
  end
  return definitions
end

local entry = react.RegisterPluginRecipe(entryPoint.ModEntryPointExtension,
  "XinNativeRailLoopEntry",function() return nil end)
log.message("[Rail Loop] Native track mode installed (revision 3.2).")
function data() return {entry=entry} end
