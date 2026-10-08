-- One bounded acceptance run: a matching preview control, then six types x
-- two lane counts. Failed cases among the five known regressions can try up
-- to three repair presets (28 native calls maximum, including the control).
-- Pauses while the cursor moves and stops after all 12 targets are resolved.
-- Never submits commands, builds roads, or replays individual street segments.
local kinds={"cloverleaf","diamond","trumpet","directional","turbine","stack"}
local latest,positionKey,job
local idle,cooldown,finished,busy,active=0,0,false,false,false
local function emit(s) log.message("[Interchange Acceptance r17] "..s) end
local function copyParams(params)
  local result={}
  for key,value in pairs(params or {}) do result[key]=value end
  return result
end
local function status(data)
  local state,messages=data.errorState or {},{}
  for _,message in ipairs(state.messages or {}) do messages[#messages+1]=tostring(message) end
  table.sort(messages)
  return tostring(state.critical)..":"..table.concat(messages," | ")
end
local function makeProposal(anchor,kind,lanes,variant)
  local proposal=api.type.SimpleProposal.new()
  local entity=api.type.SimpleProposal.ConstructionEntity.new()
  entity.fileName=kind and ("xin_interchange_pack_1::/interchanges/"..kind..".con") or anchor.entity.fileName
  entity.transf,entity.playerEntity=anchor.entity.transf,anchor.entity.playerEntity
  local params=copyParams(anchor.entity.params)
  if kind then
    params.lanes,params.size,params.roadType,params.bridge=lanes,1,1,1
    params.cloverLayout,params.crossApproach,params.crossLanes,params.loopSide=1,1,1,1
    params._ipProbe=nil
    params._ipAcceptVariant=variant or 0
    for i=1,4 do params["leafEnabled"..i],params["rampEnabled"..i]=2,2 end
  end
  entity.params=params
  proposal.constructionsToAdd={entity}
  return proposal
end
local function check(proposal)
  local context=api.type.Context.new()
  context.player=api.engine.util.getPlayer()
  local first,second=api.engine.util.proposal.makeProposalData(proposal,context)
  local function field(value,key)
    if value==nil then return nil end
    local ok,result=pcall(function() return value[key] end)
    if ok then return result end
  end
  local values={[1]=first,[2]=second,[3]=field(first,1),[4]=field(first,2)}
  for i=1,4 do if field(values[i],"errorState") then return values[i] end end
  error("no native ProposalData returned")
end
local function capture(name,param)
  if finished or busy or name~="builder.proposalCreate" then return end
  local proposal,result=param and param[1],param and param[2]
  if not proposal or not result or #(proposal.toAdd or {})~=1 then idle,active=0,false; return end
  local item=proposal.toAdd[1]
  local file=tostring(item.fileName)
  if not file:find("xin_interchange_pack_1::/interchanges/",1,true) then idle,active=0,false; return end
  local street=proposal.proposal or {}
  local first=(street.addedNodes or {})[1]
  if not first or #(street.removedSegments or {})>0 or #(street.removedNodes or {})>0 then
    idle,active=0,false
    return
  end
  for _,collision in ipairs((result.collisionInfo or {}).collisionEntities or {}) do
    if collision.entity>0 then idle,active=0,false; return end
  end
  local p=first.comp.position
  local key=file..":"..string.format("%.2f,%.2f,%.2f",p.x,p.y,p.z)..":"..#(street.addedSegments or {})
  if key~=positionKey or not active then positionKey,idle=key,0 end
  active=true
  if job then return end -- Keep the original test location once acceptance starts.
  local entity=api.type.SimpleProposal.ConstructionEntity.new()
  entity.fileName,entity.transf,entity.playerEntity=item.fileName,item.transf,item.playerEntity
  entity.params=copyParams(item.construction.params)
  latest={entity=entity,expected=status(result),positionKey=key}
end

function data()
  return {
    update=function(_,state)
      if not state:hasEventSubscriptions() then state:subscribeToEvent("builder.proposalCreate") end
    end,
    guiHandleEvent=function(_,_,_,_,_,name,param)
      local ok,failure=pcall(capture,name,param)
      if not ok then finished=true; emit("CAPTURE ERROR "..tostring(failure)) end
      return {}
    end,
    guiUpdate=function()
      if finished or busy or not latest or not active then return end
      idle=idle+1
      if idle<120 then return end
      if cooldown>0 then cooldown=cooldown-1; return end
      job=job or {anchor=latest,index=0,variant=0,passed=0,defaults=0,overrides={}}
      local kind,lanes
      if job.index>0 then kind=kinds[math.floor((job.index-1)/2)+1]; lanes=(job.index-1)%2+1 end
      busy=true
      local ok,result=pcall(function() return check(makeProposal(job.anchor,kind,lanes,job.variant)) end)
      busy=false
      cooldown=15
      if job.index==0 then
        if not ok or status(result)~=job.anchor.expected then
          finished=true
          emit("CONTROL MISMATCH; result="..(ok and status(result) or tostring(result)).."; expected="..job.anchor.expected)
          return
        end
        emit("START; cases=12; read-only; native calls stop after completion; anchor="..job.anchor.positionKey)
      else
        local passed=ok and status(result)=="false:"
        local external,internal=0,0
        if ok then
          for _,collision in ipairs((result.collisionInfo or {}).collisionEntities or {}) do
            if collision.entity>0 then external=external+1 else internal=internal+1 end
          end
        end
        local record="kind="..kind.."; lanes="..lanes.."; variant="..job.variant.."; verdict="..(passed and "PASS" or "FAIL")
          .."; result="..(ok and status(result) or tostring(result)).."; externalCollisions="..external.."; internalCollisions="..internal
        emit("TRY "..record)
        local hasAlternatives=kind=="stack" or kind=="turbine" or (kind=="trumpet" and lanes==2)
        if not passed and external==0 and hasAlternatives and job.variant<3 then
          job.variant=job.variant+1
          return
        end
        emit("CASE "..record)
        if passed then
          job.passed=job.passed+1
          if job.variant==0 then job.defaults=job.defaults+1
          else job.overrides[#job.overrides+1]=kind..":"..lanes.."="..job.variant end
        end
      end
      job.index=job.index+1
      job.variant=0
      if job.index>12 then
        finished=true
        emit("DONE; resolved="..job.passed.."/12; defaults="..job.defaults.."/12; stopped=true; overrides="..table.concat(job.overrides,","))
      end
    end,
  }
end
