-- Native, read-only differential checks of an already prepared preview.
-- No commands are sent. One bounded check is performed per GUI update.
local M = {}
local designs = require "xin_interchange_pack_1::/interchanges/design_candidates.lua"
local jobs, seen, skipped = {}, {}, {}
local running = false
local matrixQueued = false
local function emit(s) log.message("[Interchange Replay r15] " .. s) end
local function status(data)
  local state = data.errorState or {}
  local messages = {}
  for _,value in ipairs(state.messages or {}) do messages[#messages+1] = tostring(value) end
  table.sort(messages)
  return tostring(state.critical) .. ":" .. table.concat(messages," | ")
end
local function failed(data)
  return data.errorState and (data.errorState.critical or #(data.errorState.messages or {}) > 0)
end
local function position(p)
  return string.format("(%.4f,%.4f,%.4f)",p.x,p.y,p.z)
end
local function fingerprint(proposal)
  local result = { tostring(#proposal.toAdd) }
  for _,node in ipairs(proposal.proposal.addedNodes) do
    result[#result+1] = tostring(node.entity) .. position(node.comp.position)
  end
  for _,edge in ipairs(proposal.proposal.addedSegments) do
    local s = edge.comp
    result[#result+1] = tostring(edge.entity) .. ":" .. s.node0 .. ":" .. s.node1
      .. ":" .. tostring(s.type) .. ":" .. tostring(s.roadTemplate)
      .. position(s.tangent0) .. position(s.tangent1)
  end
  for _,config in ipairs(proposal.proposal.nodeConfigsToAdd) do
    result[#result+1] = "config:" .. config.entity .. ":" .. tostring(config.comp.userModifiedLaneConnections)
    for _,connection in ipairs(config.comp.laneConnections or {}) do
      result[#result+1] = connection.segment0 .. ":" .. connection.lane0 .. ">" .. connection.segment1 .. ":" .. connection.lane1
    end
  end
  return table.concat(result,";")
end
local function check(proposal)
  local context = api.type.Context.new()
  context.player = api.engine.util.getPlayer()
  -- The shipped runtime requires SimpleProposal (its Teal declaration is stale).
  local first,second = api.engine.util.proposal.makeProposalData(proposal,context)
  local function field(value,key)
    if value == nil then return nil end
    local ok,result = pcall(function() return value[key] end)
    if ok then return result end
  end
  local candidates = {[1]=first,[2]=second,[3]=field(first,1),[4]=field(first,2)}
  local data,prepared
  for i=1,4 do
    if field(candidates[i],"errorState") then data=candidates[i] end
    if field(candidates[i],"proposal") and field(candidates[i],"toAdd") then prepared=candidates[i] end
  end
  if data then return data,prepared end
  error("makeProposalData returned no ProposalData: " .. type(first) .. "/" .. type(second))
end
local function construction(job,plan)
  local proposal = api.type.SimpleProposal.new()
  local additions = {}
  for _,item in ipairs(job.original.toAdd) do
    local entity = api.type.SimpleProposal.ConstructionEntity.new()
    entity.fileName,entity.transf,entity.playerEntity = item.fileName,item.transf,item.playerEntity
    entity.params = item.construction.params
    if plan then
      local params = {}
      for k,v in pairs(item.construction.params) do params[k]=v end
      params.size,params.lanes,params.roadType,params.bridge = 1,plan.lanes,plan.roadType,1
      params.cloverLayout,params.loopSide,params.crossApproach,params.crossLanes = 1,1,1,1
      for i=1,4 do params["leafEnabled"..i],params["rampEnabled"..i]=2,2 end
      params._ipProbe = plan.probe
      entity.params,entity.fileName = params,"xin_interchange_pack_1::/interchanges/"..plan.kind..".con"
    end
    additions[#additions+1] = entity
  end
  proposal.constructionsToAdd = additions
  return proposal
end
local function scheduleMatrix(job)
  if matrixQueued or not tostring(job.original.toAdd[1].fileName):find("xin_interchange_pack_1::/",1,true) then return end
  matrixQueued = true
  local plans = {}
  for roadType=1,2 do for lanes=1,2 do
    for _,kind in ipairs({"cloverleaf","turbine","stack","trumpet","directional"}) do
      for probe=0,#designs.options(kind) do
        plans[#plans+1]={kind=kind,probe=probe,lanes=lanes,roadType=roadType}
      end
    end
  end end
  jobs[#jobs+1]={key="MATRIX",original=job.original,fingerprint=job.fingerprint,
    stage="matrix",plans=plans,index=1}
  emit("MATRIX QUEUED; cases="..#plans.."; no commands will be submitted")
end
local function subset(job, first, last, selection)
  -- A new Proposal deliberately has no construction metadata, removals, or
  -- saved terrain grid. Copy only the selected street edges and their nodes.
  local proposal = api.type.SimpleProposal.new()
  local segments,nodes,configs,used,kept = {},{},{},{},{}
  local source = job.original:clone()
  for index,edge in ipairs(source.proposal.addedSegments) do
    if (selection and selection[index]) or (not selection and index >= first and index <= last) then
      segments[#segments+1] = edge
      kept[edge.entity] = true
      used[edge.comp.node0],used[edge.comp.node1] = true,true
    end
  end
  for _,node in ipairs(source.proposal.addedNodes) do
    if used[node.entity] then nodes[#nodes+1] = node end
  end
  for _,config in ipairs(source.proposal.nodeConfigsToAdd) do
    if used[config.entity] then
      local connections = {}
      for _,connection in ipairs(config.comp.laneConnections or {}) do
        if kept[connection.segment0] and kept[connection.segment1] then
          connections[#connections+1] = connection
        end
      end
      config.comp.laneConnections = connections
      configs[#configs+1] = config
    end
  end
  proposal.streetProposal.edgesToAdd,proposal.streetProposal.nodesToAdd = segments,nodes
  proposal.streetProposal.nodeConfigsToAdd = configs
  assert(#proposal.streetProposal.edgesToAdd == #segments,"segment setter did not persist")
  assert(#proposal.streetProposal.nodesToAdd == #nodes,"node setter did not persist")
  assert(#proposal.streetProposal.nodeConfigsToAdd == #configs,"node-config setter did not persist")
  return proposal
end
local function report(job,label,data)
  emit(job.key .. "; case=" .. label .. "; result=" .. status(data))
end
local function detail(job,index)
  local edge = job.original.proposal.addedSegments[index]
  local s = edge.comp
  emit(job.key .. "; EDGE index=" .. index .. "; entity=" .. edge.entity
    .. "; type=" .. tostring(s.type) .. "; template=" .. tostring(s.roadTemplate)
    .. "; nodes=" .. s.node0 .. "," .. s.node1
    .. "; p0=" .. position(s.position0) .. "; p1=" .. position(s.position1)
    .. "; t0=" .. position(s.tangent0) .. "; t1=" .. position(s.tangent1))
  job.detailedNodes = job.detailedNodes or {}
  for _,node in ipairs({s.node0,s.node1}) do
    if not job.detailedNodes[node] then
      job.detailedNodes[node] = true
      for _,config in ipairs(job.original.proposal.nodeConfigsToAdd) do
        if config.entity == node then
          local links = {}
          for _,c in ipairs(config.comp.laneConnections or {}) do
            links[#links+1] = c.segment0 .. ":" .. c.lane0 .. ">" .. c.segment1 .. ":" .. c.lane1
              .. ":road=" .. tostring(c.withRoad)
          end
          emit(job.key .. "; NODE " .. node .. "; modified=" .. tostring(config.comp.userModifiedLaneConnections)
            .. "; links=" .. table.concat(links,","))
        end
      end
      for _,neighbor in ipairs(job.original.proposal.addedSegments) do
        local base = neighbor.comp
        if base.node0 == node or base.node1 == node then
          local lanes = {}
          for i,lane in ipairs(base.laneConfigs or {}) do
            local modes = {}
            for _,mode in ipairs(lane.transportModes or {}) do modes[#modes+1]=tostring(mode) end
            lanes[#lanes+1] = (i-1) .. ":" .. tostring(lane.forward) .. ":" .. table.concat(modes,"+")
          end
          emit(job.key .. "; NEIGHBOR " .. neighbor.entity .. "; node=" .. node
            .. "; atStart=" .. tostring(base.node0==node) .. "; template=" .. tostring(base.roadTemplate)
            .. "; lanes=" .. table.concat(lanes,","))
        end
      end
    end
  end
end

function M.enqueue(key,proposal,data)
  if running or seen[key] or #jobs >= 12 then return end
  local util = api.engine and api.engine.util
  if not (util and util.proposal and util.proposal.makeProposalData) then
    seen[key] = true
    emit("UNAVAILABLE makeProposalData; " .. key)
    return
  end
  local street = proposal.proposal
  for _,collision in ipairs((data.collisionInfo or {}).collisionEntities or {}) do
    if collision.entity>0 then
      if not skipped[key..":external"] then
        skipped[key..":external"]=true
        emit("SKIP external collision; "..key)
      end
      return
    end
  end
  local newNodes = {}
  for _,node in ipairs(street.addedNodes) do newNodes[node.entity] = true end
  local editsExistingConfig = false
  for _,config in ipairs(street.nodeConfigsToAdd) do
    if not newNodes[config.entity] then editsExistingConfig = true end
  end
  -- Differential results on an empty-site preview must not include replacement
  -- streets or third-party constructions such as an industry being removed.
  if #proposal.toAdd ~= 1 or #street.removedSegments > 0
    or #street.removedNodes > 0 or #street.edgeObjectsToAdd > 0
    or editsExistingConfig or #street.nodeConfigsToRemove > 0 then
    if not skipped[key] then
      skipped[key] = true
      emit("SKIP existing-road edits; " .. key .. "; constructions=" .. #proposal.toAdd
        .. "; removedSegments=" .. #street.removedSegments .. "; removedNodes=" .. #street.removedNodes
        .. "; edgeObjects=" .. #street.edgeObjectsToAdd .. "; configs=" .. #street.nodeConfigsToAdd
        .. "/" .. #street.nodeConfigsToRemove)
    end
    return
  end
  local ok,copy = pcall(function() return proposal:clone() end)
  if not ok then seen[key]=true; emit("CLONE FAILED " .. tostring(copy)); return end
  seen[key] = true
  jobs[#jobs+1] = {key=key,original=copy,originalStatus=status(data),stage="full",
    count=#copy.proposal.addedSegments,fingerprint=fingerprint(copy)}
  emit("QUEUED " .. key .. "; segments=" .. #copy.proposal.addedSegments)
end

function M.step()
  if running or #jobs == 0 then return end
  running = true
  local job = table.remove(jobs,1)
  local ok,error = pcall(function()
    if job.stage == "full" then
      local result = check(construction(job))
      report(job,"full-replay",result)
      if status(result) ~= job.originalStatus then
        emit(job.key .. "; REPLAY MISMATCH; original=" .. job.originalStatus)
        job.stage = nil
      else
        scheduleMatrix(job)
        job.stage = failed(result) and "empty" or nil
      end
    elseif job.stage == "matrix" then
      local plan = job.plans[job.index]
      local checked,result,prepared = pcall(check,construction(job,plan))
      local label = "MATRIX kind="..plan.kind.."; roadType="..plan.roadType.."; lanes="..plan.lanes
        .."; probe="..plan.probe.."; name="..(designs.get(plan.kind,plan.probe).name or "legacy-port-control")
      if checked then
      local collisionIds = {}
      for _,collision in ipairs((result.collisionInfo or {}).collisionEntities or {}) do
        collisionIds[#collisionIds+1]=tostring(collision.entity)
      end
      local laneGrade,worstLane = 0,nil
      local lanesOK,laneError = pcall(function()
      for entity,network in pairs(result.entity2tn or {}) do
        for _,edge in ipairs(network.edges or {}) do
          for i=0,16 do
            local tangent = edge.geometry:calcPos(i/16)[2]
            local horizontal = math.sqrt(tangent.x*tangent.x+tangent.y*tangent.y)
            if horizontal>1e-8 and math.abs(tangent.z)/horizontal>laneGrade then
              laneGrade,worstLane=math.abs(tangent.z)/horizontal,entity
            end
          end
        end
      end
      end)
      emit(label.."; result="..status(result).."; collisions="..table.concat(collisionIds,",")
        .."; laneMaxGrade="..string.format("%.5f",laneGrade).."; worstLane="..tostring(worstLane)
        ..(lanesOK and "" or "; laneReadError="..tostring(laneError)))
      if prepared and plan.probe==0 and plan.roadType==1 and plan.lanes==1 and failed(result) then
        local selected = {}
        for _,id in ipairs(collisionIds) do selected[tonumber(id)]=true end
        if worstLane then selected[worstLane]=true end
        for index,edge in ipairs(prepared.proposal.addedSegments or {}) do
          if selected[edge.entity] then
            local s=edge.comp
            emit(label.."; EDGE index="..index.."; entity="..edge.entity.."; type="..tostring(s.type)
              .."; template="..tostring(s.roadTemplate).."; p0="..position(s.position0).."; p1="..position(s.position1)
              .."; t0="..position(s.tangent0).."; t1="..position(s.tangent1))
          end
        end
      end
      else emit(label.."; CHECK FAILED "..tostring(result)) end
      job.index = job.index+1
      if job.index>#job.plans then job.stage=nil end
    elseif job.stage == "empty" then
      local result = check(subset(job,1,0))
      report(job,"empty-positive-control",result)
      job.stage = not failed(result) and "roads" or nil
    elseif job.stage == "roads" then
      local result = check(subset(job,1,job.count))
      report(job,"roads-without-construction-or-terrain",result)
      local collided = {}
      for _,collision in ipairs((result.collisionInfo or {}).collisionEntities or {}) do collided[collision.entity]=true end
      for index,edge in ipairs(job.original.proposal.addedSegments) do
        if collided[edge.entity] then detail(job,index) end
      end
      if failed(result) then job.stage = "automatic-nodes"
      else
        job.stage = nil
        emit(job.key .. "; rebuilt streets pass; failure is specific to construction preparation")
      end
    elseif job.stage == "automatic-nodes" then
      local proposal = subset(job,1,job.count)
      proposal.streetProposal.nodeConfigsToAdd = {}
      local result = check(proposal)
      report(job,"roads-with-automatic-node-configs",result)
      job.stage,job.index = "single",1
    elseif job.stage == "single" then
      local result = check(subset(job,job.index,job.index))
      if failed(result) then
        report(job,"single-" .. job.index,result)
        detail(job,job.index)
        job.singleFailures = (job.singleFailures or 0)+1
      end
      job.index = job.index+1
      if job.index > job.count then
        emit(job.key .. "; singleFailures=" .. (job.singleFailures or 0))
        job.stage,job.index = "prefix",2
      end
    elseif job.stage == "prefix" then
      local result = check(subset(job,1,job.index))
      if result.errorState.critical then
        report(job,"first-failing-prefix-" .. job.index,result)
        detail(job,job.index)
        job.stage,job.target,job.index = "pairs",job.index,1
      else
        job.index = job.index+1
        if job.index > job.count then job.stage = nil end
      end
    elseif job.stage == "pairs" then
      local selected = {[job.index]=true,[job.target]=true}
      local result = check(subset(job,1,0,selected))
      if result.errorState.critical then
        report(job,"pair-" .. job.index .. "+" .. job.target,result)
        detail(job,job.index)
        job.pairFailures = (job.pairFailures or 0)+1
      end
      job.index = job.index+1
      if job.index >= job.target then
        emit(job.key .. "; pairFailures=" .. (job.pairFailures or 0))
        local target = job.original.proposal.addedSegments[job.target].comp
        local neighbors = {}
        for index,edge in ipairs(job.original.proposal.addedSegments) do
          local s = edge.comp
          if index < job.target and (s.node0==target.node0 or s.node1==target.node0
            or s.node0==target.node1 or s.node1==target.node1) then neighbors[#neighbors+1]=index end
        end
        job.triples = {}
        for i=1,#neighbors do for j=i+1,#neighbors do
          job.triples[#job.triples+1]={neighbors[i],neighbors[j]}
        end end
        job.stage,job.index = #job.triples>0 and "triples" or nil,1
      end
    elseif job.stage == "triples" then
      local pair = job.triples[job.index]
      local result = check(subset(job,1,0,{[pair[1]]=true,[pair[2]]=true,[job.target]=true}))
      report(job,"junction-triple-" .. pair[1] .. "+" .. pair[2] .. "+" .. job.target,result)
      if result.errorState.critical then detail(job,pair[1]); detail(job,pair[2]) end
      job.index = job.index+1
      if job.index > #job.triples then job.stage=nil end
    end
    assert(fingerprint(job.original)==job.fingerprint,"replay mutated the original preview")
  end)
  running = false
  if not ok then emit(job.key .. "; CHECK FAILED " .. tostring(error)); job.stage=nil end
  if job.stage then jobs[#jobs+1] = job else emit("DONE " .. job.key) end
end

return M
