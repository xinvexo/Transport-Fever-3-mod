local react = require "::/gui/main/react.lua"
local builtin = require "::/gui/main/builtin.lua"
local proposalUtil = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_proposal.lua"
local geometry = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_geometry.lua"
local previewUtil = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_preview.lua"
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
    o.bridgeType or -1,o.tunnelType or -1,o.trackTemplate or "",tostring(o.underground),tostring(o.snapping)}, ":")
end
local function errorMessage(err) return tostring(err):gsub("^.-:%d+: ", "") end
local function pointKey(point)
  return point and (point.entity..":"..point.revision..string.format(":%.6f",point.u)) or "none"
end

-- ActionFn must create ActionDescriptor directly in its own recipe context.
-- RegisterRecipe around this function triggers a native fatal assertion.
local function Tool(params)
  local state = react.useRef({points = {}, serial = 0, busy = false,
    message = "① 点击第一条轨道上的连接点"})
  local tick = react.useState(0)
  local s = state:get()
  local function active() return not state:hasExpired() and not s.closed end
  local function planPoints()
    local a,b=s.points[1],s.points[2] or s.hover
    if a and b and a.entity~=b.entity then return a,b end
  end
  local function planKey()
    local a,b=planPoints()
    if a then return #s.points..":"..pointKey(a)..":"..pointKey(b)..":"..optionKey(currentOptions(params,s)) end
  end
  if not s.loggedEntry then
    s.loggedEntry = true
    log.message("[Rail Loop] Tool entered: "..params.definition.resName)
  end
  local function refresh() if active() then tick:set(tick:old()+1) end end
  local function invalidate(keepOutline)
    s.serial = s.serial+1;s.ready = false;s.proposal = nil;s.price = nil;s.info = nil
    if not keepOutline then s.segments = nil;s.renderEdges = nil end
    s.renderStatus = nil;s.renderError = nil;s.planKey = nil;s.planDirty = false
    s.previewChecked = false;s.previewValid = false;s.failed = false;s.previewMessage = nil;s.previewCost = nil
  end
  local function reset()
    if not active() or s.busy then return end
    invalidate();s.points = {};s.hover = nil;s.hoverReason = nil
    s.fixedMarkerKey=nil;s.fixedMarkerEdges=nil
    s.extension = 0;s.direction = 1;s.pendingShape = nil;s.message = "① 点击第一条轨道上的连接点";refresh()
  end
  local function back()
    if not active() or s.busy then return end
    if #s.points==2 then
      invalidate();s.points[2]=nil;s.hover=nil;s.hoverReason=nil
      s.extension=0;s.direction=1;s.pendingShape=nil;s.message="② 移到另一条轨道，预览后单击固定终点";refresh();return
    end
    if #s.points==1 then reset();return end
    s.closed = true;invalidate()
    -- abort() alone leaves the mouse toolbar in mode 3 and rebinds this tool.
    local menuApi = toolbarApi
    local mode = menuApi and menuApi.getParamByKey("mode")
    if mode then menuApi.changeParam(mode.index,1) end
    params.setActionFn(nil)
    if not mode then params.abort() end
  end
  local function showPreviewResult()
    local valid=s.previewValid and not s.pendingShape and not s.planDirty
    s.ready = valid and #s.points==2 or false
    s.price = valid and s.previewCost or nil
    s.message = (s.pendingShape or s.planDirty) and "正在更新施工预览……" or
      (valid and (#s.points==1 and "单击固定终点；右键或 Esc 重选起点。" or
        "移动鼠标调整长度；用原高度、弯曲和桥隧选项调整，单击建造。") or s.previewMessage or "正在检查施工预览……")
  end
  local function recompute()
    invalidate()
    local opts = currentOptions(params,s)
    s.planKey = planKey()
    local a,b=planPoints()
    if a then
      local ok,segments,info = pcall(geometry.generate,a,b,opts)
      if ok then
        s.segments = segments;s.info = info
        local made,proposal = pcall(proposalUtil.make,a,b,opts,segments,info)
        if made then s.proposal = proposal;s.message = "正在检查施工预览……"
        else s.failed = true;s.message = errorMessage(proposal) end
      else s.failed = true;s.message = errorMessage(segments) end
      if s.failed then
        s.previewMessage = s.message
        log.message("[Rail Loop] Preview failed: "..s.message)
      end
    else
      s.message=#s.points==1 and "② 移到另一条轨道，预览后单击固定终点" or "① 点击第一条轨道上的连接点"
    end
    refresh()
  end
  local function setHover(point)
    local reason=point and proposalUtil.pickProblem(point,s.points[1])
    local changed=pointKey(s.hover)~=pointKey(point) or reason~=s.hoverReason
    s.hover=point;s.hoverReason=reason;s.hoverSnapping=currentOptions(params,s).snapping
    if not changed then return end
    if #s.points==1 then
      if planPoints() then
        local hadOutline=s.segments~=nil
        invalidate(true);s.planDirty=true;s.message="正在更新施工预览……"
        if not hadOutline then recompute() end
      else recompute() end
    else s.message="① 点击第一条轨道上的连接点" end
    refresh()
  end
  local function hover(entity,indices,details)
    if not active() or s.busy or #s.points==2 then return end
    if not proposalUtil.isTrack(entity) then setHover(nil);return end
    local ok,point=pcall(proposalUtil.pick,entity,details,s.mouse,currentOptions(params,s).snapping)
    setHover(ok and point or nil)
  end
  local build
  local function acceptPoint(point)
    if not point or not proposalUtil.current(point) then return end
    local reason=proposalUtil.pickProblem(point,s.points[1])
    if reason then s.message=reason;s.hoverReason=reason;refresh();return end
    s.points[#s.points+1]=point;s.hover=nil;s.hoverReason=nil;s.pendingShape=nil
    log.message(string.format("[Rail Loop] Point %d: entity=%d u=%.6f position=(%.3f,%.3f,%.3f) tangent=(%.3f,%.3f,%.3f) snapped=%s nativeHit=%s",
      #s.points,point.entity,point.u,point.p[1],point.p[2],point.p[3],point.t[1],point.t[2],point.t[3],
      tostring(point.snapped),tostring(point.nativeSnap)))
    recompute()
  end
  local function pick(entity,indices,details)
    if not active() or s.busy then return true end
    if #s.points == 2 then if s.ready then build() end;return true end
    local ok,point = pcall(proposalUtil.pick,entity,details,s.mouse,currentOptions(params,s).snapping)
    if not ok then s.message = errorMessage(point);log.message("[Rail Loop] Pick failed: "..s.message);refresh();return true end
    if proposalUtil.pickProblem(point,s.points[1]) then setHover(point)
    else acceptPoint(point) end
    return true
  end
  build = function()
    if not active() or s.busy or #s.points~=2 or s.pendingShape or s.planDirty or not s.ready or not s.proposal then return end
    if planKey()~=s.planKey then recompute();return end
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
        if not active() then return end
        s.busy = false
        if success then reset();s.message = "已建造。可以继续选择下一组连接点。"
        else invalidate();s.message = "施工未成功，请调整长度或重新选点后重试。" end
        refresh()
      end)
    end)
    if not ok then s.busy = false;s.message = errorMessage(err);refresh() end
  end
  react.onStep(function()
    if not active() or s.busy then return end
    if s.points[1] and not proposalUtil.current(s.points[1]) then
      reset();s.message="起点轨道已改变，请重新选点。";refresh();return
    end
    if s.points[2] and not proposalUtil.current(s.points[2]) then
      back();s.message="终点轨道已改变，请重新选择终点。";refresh();return
    end
    local snapping=currentOptions(params,s).snapping
    if s.hover then
      if not proposalUtil.current(s.hover) then setHover(nil)
      elseif snapping~=s.hoverSnapping then setHover(proposalUtil.resnap(s.hover,snapping)) end
    end
    s.frame = (s.frame or 0)+1
    if s.pendingShape and s.frame%4==0 then
      s.extension,s.direction = s.pendingShape[1],s.pendingShape[2]
      s.pendingShape = nil
    end
    if planKey()~=s.planKey and (not s.planDirty or s.frame%4==0) then recompute() end
  end)
  local children = {
    builtin.Selector{
      filter = proposalUtil.isTrack,
      onHover = hover,
      onProcessMouseEvent = function(event)
        if not active() or event.handled then return false end
        if type(event.x)=="number" and type(event.y)=="number" then
          s.mouse = {x=event.x,y=event.y}
          -- The native hover event supplies precise network hits. Keep a
          -- candidate moving along the same rail between hover notifications.
          if #s.points<2 and s.hover and event.type~=api.gui.mouse.Event.Type.Clicked then
            local ok,point=pcall(proposalUtil.pick,s.hover.entity,nil,s.mouse,currentOptions(params,s).snapping)
            if ok then
              local screen=api.gui.camera.world2Screen(api.type.Vec3f.new(point.p[1],point.p[2],point.p[3]))
              if (screen.x-event.x)^2+(screen.y-event.y)^2>100 then point=nil end
            end
            setHover(ok and point or nil)
          end
        end
        if #s.points==2 and not s.busy and api.gui.mouse.hasTerrainPosition() then
          local p = api.gui.mouse.getTerrainPosition()
          local a,b = s.points[1],s.points[2]
          local n = math.sqrt(a.t[1]^2+a.t[2]^2)
          local distance = ((p.x-(a.p[1]+b.p[1])/2)*a.t[1]+(p.y-(a.p[2]+b.p[2])/2)*a.t[2])/n
          -- Mouse movement controls length, as in native laying; no extra slider.
          local extension = math.min(800,math.floor(math.max(0,math.abs(distance)-180)/5)*5)
          local direction = distance<0 and 2 or 1
          if extension~=(s.extension or 0) or direction~=(s.direction or 1) then
            s.pendingShape = {extension,direction};showPreviewResult();refresh()
          elseif s.pendingShape then
            s.pendingShape = nil;showPreviewResult();refresh()
          end
        end
        -- Empty terrain is not a selectable track entity. Handle confirmation
        -- here too so extending the loop does not require clicking a rail again.
        if not event.handled and event.type==api.gui.mouse.Event.Type.Clicked then
          if event.button==0 and #s.points==2 then build();return true end
          if event.button==2 then back();return true end
        end
        return false
      end,
      onSelect = pick,
      onSelectSecondary = function() back();return true end,
      selectionColor = api.type.Vec4f.new(0,0,0,0),
      selectionOutlineColor = api.type.Vec4f.new(0,0,0,0),
      selectionOutlineColor1 = api.type.Vec4f.new(0,0,0,0),
    },
  }
  local viewer
  if s.proposal then
    local serial = s.serial
    viewer = {
      simpleProposal = s.proposal,
      entityForRefundableContext = api.engine.util.getPlayer(),
      proposalId = "xin-dynamic-loop:"..tostring(s)..":"..serial,
      onCreateProposalData = function(data,preparedProposal)
        if not active() or s.serial~=serial or s.busy or planKey()~=s.planKey then return end
        local errors = data.errorState
        s.previewChecked = true;s.previewCost = data.costs
        s.previewValid = not errors.critical and #errors.messages==0
        s.previewMessage = table.concat(errors.messages,"\n")
        if not s.previewValid then
          if s.previewMessage=="" then s.previewMessage = "游戏拒绝了施工方案，请调整长度、高度或连接点。" end
          for _,hit in ipairs(s.info.mainCrossings or {}) do
            if math.abs(hit.clearance)<5 then
              s.previewMessage = s.previewMessage.."\n回环穿过保留的主线且高差不足，请用原高度控件抬升或降低，或改从轨道端点接出。"
              break
            end
          end
          if s.loggedPreviewSerial~=serial then
            s.loggedPreviewSerial = serial
            local collisionIds={}
            for _,hit in ipairs(data.collisionInfo and data.collisionInfo.collisionEntities or {}) do
              if #collisionIds<8 then collisionIds[#collisionIds+1]=tostring(hit.entity) end
            end
            local crossingInfo={}
            for _,hit in ipairs(s.info.mainCrossings or {}) do
              crossingInfo[#crossingInfo+1]=string.format("track%d@%.1f,%.1f dz=%.2f",hit.track,hit.position[1],hit.position[2],hit.clearance)
            end
            local street=s.proposal.streetProposal
            local prepared=preparedProposal and preparedProposal.proposal
            log.message(string.format("[Rail Loop] Engine preview rejected: serial=%d critical=%s cost=%s messages=[%s] warnings=[%s] infos=[%s] collisions=[%s] nodes=%d edges=%d removed=%d preparedEdges=%s options=%s crossings=[%s]",
              serial,tostring(errors.critical),tostring(data.costs),table.concat(errors.messages," | "),
              table.concat(errors.warnings or {}," | "),table.concat(errors.infos or {}," | "),table.concat(collisionIds,","),
              #street.nodesToAdd,#street.edgesToAdd,#street.edgesToRemove,
              prepared and tostring(#prepared.addedSegments) or "none",optionKey(currentOptions(params,s)),table.concat(crossingInfo,"; ")))
          end
        end
        showPreviewResult()
        refresh()
      end,
    }
  end
  if s.segments then
    local status=(s.failed or (s.previewChecked and not s.previewValid)) and "blocked" or
      (s.previewValid and not s.planDirty and not s.pendingShape and "ready" or "pending")
    if s.renderStatus~=status then
      local color=status=="blocked" and api.type.Vec4f.new(1,0.2,0.15,0.9) or
        (status=="ready" and api.type.Vec4f.new(0.15,0.9,0.55,0.85) or api.type.Vec4f.new(0.2,0.7,1,0.85))
      local ok,edges,diagnostics=pcall(previewUtil.make,s.segments,color)
      s.renderEdges=ok and edges or nil;s.renderStatus=status
      s.renderError=not ok
      if not ok then log.message("[Rail Loop] Rail outline failed: "..errorMessage(edges))
      elseif s.loggedOutlineSerial~=s.serial then
        s.loggedOutlineSerial=s.serial
        log.message(string.format("[Rail Loop] Rail outline verified: serial=%d edges=%d first=(%.3f,%.3f,%.3f) last=(%.3f,%.3f,%.3f) sampleError=%.6f",
          s.serial,#edges,diagnostics.first.x,diagnostics.first.y,diagnostics.first.z,
          diagnostics.last.x,diagnostics.last.y,diagnostics.last.z,diagnostics.maxError))
      end
    end
  end
  -- Native CollectActionConfig permits exactly one ProposalViewer per action.
  -- Merge the active control point into the construction viewer; other fixed
  -- points are tiny markers in the existing edge-render batch.
  local activePoint=s.hover or s.points[#s.points]
  if activePoint then
    local isHover=s.hover~=nil
    local ok,control=pcall(previewUtil.controlPoint,activePoint,isHover,isHover and s.hoverReason~=nil)
    if ok then
      viewer=viewer or {proposalId="xin-loop-point:"..tostring(s)}
      viewer.controlPointInfo=control
    elseif not s.loggedMarkerError then
      s.loggedMarkerError=true;log.message("[Rail Loop] Point marker failed: "..errorMessage(control))
    end
  end
  if viewer then children[#children+1]=builtin.ProposalViewer(viewer) end
  local renderEdges={}
  for _,edge in ipairs(s.renderEdges or {}) do renderEdges[#renderEdges+1]=edge end
  for _,point in ipairs(s.points) do
    if point~=activePoint then
      local key=pointKey(point)
      if key~=s.fixedMarkerKey then
        local ok,edges=pcall(previewUtil.fixedPoint,point)
        s.fixedMarkerKey=key;s.fixedMarkerEdges=ok and edges or nil
        if not ok then log.message("[Rail Loop] Fixed point marker failed: "..errorMessage(edges)) end
      end
      for _,edge in ipairs(s.fixedMarkerEdges or {}) do renderEdges[#renderEdges+1]=edge end
    end
  end
  if #renderEdges>0 then children[#children+1]=builtin.EdgeRenderable{edges=renderEdges,ignoreDepth=true} end
  local message = s.message
  if s.hoverReason then message=s.hoverReason
  end
  if s.renderError then message=message.."\n轨迹预览未能显示，错误已记录。" end
  if s.info then message = message..string.format("\n长度 %.0f m",s.info.length) end
  children[#children+1] = builtin.ActionTooltip{
    recipe = constructionUtil.SimpleTooltipRecipe,
    param = {message = {message=message,bad=s.hoverReason~=nil or s.failed or
      (s.previewChecked and not s.previewValid and not s.pendingShape and not s.planDirty),
      good=s.previewValid and not s.planDirty and not s.pendingShape or false},cost=s.price},
  }
  local layer = api.type.LayerConfig.new()
  layer.undergroundMode = currentOptions(params,s).underground
  children[#children+1] = builtin.LayerConfig{config=layer}
  react.useInputAction("IA_APPLY",react.iaHandler(function()
    if not active() or s.busy then return end
    if #s.points<2 then acceptPoint(s.hover) else build() end
  end,function()
    if not active() or s.busy then return false end
    if #s.points<2 then return s.hover~=nil and s.hoverReason==nil end
    return s.ready and not s.pendingShape and not s.planDirty and planKey()==s.planKey
  end,#s.points==0 and "固定起点" or (#s.points==1 and "固定终点" or "建造回环")))
  local function backState()
    local states=api.gui.inputAction.InputActionState
    if not active() then return states.Disabled end
    return s.busy and states.Inactive or states.Enabled
  end
  react.useInputAction("IA_ABORT",react.iaHandler(back,backState,"取消回环"))
  -- Native construction uses this action to capture Escape before menu-back.
  react.useInputAction("IA_CLOSE_TOPMOST_WINDOW",react.iaHandler(back,backState,"取消回环"))
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
    highlightedEntities = {},
    onBack = back,
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
log.message("[Rail Loop] Native track mode installed (revision 7).")
function data() return {entry=entry} end
