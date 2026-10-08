-- Read-only engine diagnostics. Never submit a proposal or change game state.
local roads = require "xin_interchange_pack_1::/interchanges/roads.lua"
local replay = require "xin_interchange_pack_1::/interchanges/replay_check.lua"
local deployment = require "xin_interchange_pack_1::/interchanges/diagnostic_config.lua"
local previewCases = {}
local snapshots, snapshotCount = {}, 0
local revision = 15
local replayRevision = 15
local physicalRoot = deployment.directory
if debug and debug.getinfo then
  local source = debug.getinfo(1,"S").source:gsub("^@",""):gsub("\\","/")
  if source:sub(1,1)=="/" or source:match("^%a:/") then
    physicalRoot = physicalRoot or source:match("^(.*)/diagnostics%.script%.lua$")
  end
end
local function write(message) log.message("[Interchange Check r" .. revision .. "] " .. message) end
local function list(values)
  local result = {}
  for _, value in ipairs(values or {}) do result[#result+1] = tostring(value) end
  return table.concat(result," | ")
end

local function refreshReplay()
  if not physicalRoot and not resolveutil then return end
  local root = "xin_interchange_pack_1::/interchanges/"
  local function read(name)
    local loader = deployment.loader or loadfile
    if physicalRoot and loader then return loader(physicalRoot .. "/" .. name,"t") end
    return resolveutil.loadfile(resolveutil.resolve(root .. name,""))
  end
  local readVersion = assert(read("replay_version.lua"))
  local version = readVersion()
  if version == replayRevision then return end
  local readChecker = assert(read("replay_check.lua"))
  local updated = readChecker()
  assert(type(updated.enqueue)=="function" and type(updated.step)=="function","invalid replay module")
  replay,replayRevision = updated,version
  write("REPLAY RELOADED " .. tostring(version))
  for key,snapshot in pairs(snapshots) do replay.enqueue(key,snapshot.proposal,snapshot.result) end
end

local function limits()
  local seen = {}
  for roadType = 1, 2 do
    for lanes = 1, 2 do
      for crossLanes = 1, 2 do
        local profile = roads.select({roadType=roadType,lanes=lanes,crossLanes=crossLanes})
        for _, role in ipairs({"main","ramp","cross","shared"}) do
          local name = profile[role]
          if not seen[name] then
            seen[name] = true
            local index = api.res.streetTemplateRep.find(name)
            local resource = api.res.streetTemplateRep.get(index)
            local fields = { name }
            for _, field in ipairs({"maxSlope","maxSlopeShape","maxSlopeBuild","minCurveRadius",
              "minCurveRadiusBuild","embankmentSlopeLow","embankmentSlopeHigh"}) do
              fields[#fields+1] = field .. "=" .. tostring(resource[field])
            end
            write("LIMIT " .. table.concat(fields,"; "))
          end
        end
      end
    end
  end
end

local function preview(name, param)
  if name ~= "builder.proposalCreate" then return end
  local proposal, result = param and param[1], param and param[2]
  if not proposal or not result then return end
  local names, params, ours = {}, {}, false
  for _, item in ipairs(proposal.toAdd or {}) do
    local file = tostring(item.fileName)
    names[#names+1] = file
    if file:find("xin_interchange_pack_1::",1,true) then
      ours = true
      for key,value in pairs(item.construction and item.construction.params or {}) do
        if type(value) == "number" or type(value) == "string" then params[#params+1] = key .. "=" .. tostring(value) end
      end
    end
  end
  local state = result.errorState or {}
  if not ours and not state.critical then return end
  table.sort(params)
  local caseKey = table.concat(names,",") .. ";" .. table.concat(params,",") .. ";"
    .. tostring(state.critical) .. ";" .. list(state.messages) .. ";" .. list(state.warnings)
  if previewCases[caseKey] then return end
  previewCases[caseKey] = true
  local street = proposal.proposal or {}
  local duplicates, positions = {}, {}
  for _, node in ipairs(street.addedNodes or {}) do
    local p = node.comp.position
    local key = string.format("%.5f,%.5f,%.5f",p.x,p.y,p.z)
    if positions[key] then duplicates[#duplicates+1] = tostring(positions[key]) .. "/" .. node.entity .. "@" .. key end
    positions[key] = node.entity
  end
  local collision = result.collisionInfo or {}
  local collided = {}
  for _, item in ipairs(collision.collisionEntities or {}) do collided[#collided+1] = item.entity end
  local maximumGrade, worstSegment = 0, ""
  for _, item in ipairs(street.addedSegments or {}) do
    local s = item.comp
    local p,q,t,v = s.position0,s.position1,s.tangent0,s.tangent1
    if p and q and t and v then
      for i = 0, 64 do
        local u = i/64
        local a,b,c,d = 6*u*u-6*u,3*u*u-4*u+1,-6*u*u+6*u,3*u*u-2*u
        local x,y,z = a*p.x+b*t.x+c*q.x+d*v.x,a*p.y+b*t.y+c*q.y+d*v.y,a*p.z+b*t.z+c*q.z+d*v.z
        local xy = math.sqrt(x*x+y*y)
        local grade = xy > 1e-8 and math.abs(z)/xy or 0
        if grade > maximumGrade then
          maximumGrade = grade
          worstSegment = tostring(item.entity) .. ":" .. tostring(s.roadTemplate)
        end
      end
    end
  end
  local laneGrade, worstLane = 0, ""
  local laneOK,laneError = pcall(function()
    for entity,network in pairs(result.entity2tn or {}) do
      for index,edge in ipairs(network.edges or {}) do
        for i = 0,32 do
          local point = edge.geometry:calcPos(i/32)
          local tangent = point[2]
          local horizontal = math.sqrt(tangent.x*tangent.x+tangent.y*tangent.y)
          local grade = horizontal > 1e-8 and math.abs(tangent.z)/horizontal or 0
          if grade > laneGrade then laneGrade,worstLane = grade,tostring(entity) .. ":" .. index end
        end
      end
    end
  end)
  local message = "PREVIEW " .. (#names>0 and table.concat(names,",") or "<unattributed>")
    .. "; " .. table.concat(params,",") .. "; critical=" .. tostring(state.critical)
    .. "; errors=" .. list(state.messages) .. "; warnings=" .. list(state.warnings)
    .. "; infos=" .. list(state.infos) .. "; collisions=" .. list(collided)
    .. "; duplicateNodes=" .. list(duplicates)
    .. "; preparedMaxGrade=" .. string.format("%.5f",maximumGrade) .. "; worstSegment=" .. worstSegment
    .. "; laneMaxGrade=" .. string.format("%.5f",laneGrade) .. "; worstLane=" .. worstLane
  if not laneOK then message = message .. "; laneReadError=" .. tostring(laneError) end
  write(message)
  if ours and #names == 1 then
    local key = names[1] .. "; " .. table.concat(params,",")
    if not snapshots[key] and snapshotCount < 12 then
      local ok,snapshot = pcall(function() return proposal:clone() end)
      if ok then
        local messages = {}
        for _,value in ipairs(state.messages or {}) do messages[#messages+1]=value end
        snapshots[key] = {proposal=snapshot,result={errorState={critical=state.critical,messages=messages}}}
        snapshotCount = snapshotCount+1
      end
    end
    replay.enqueue(key,proposal,result)
  end
end

function data()
  return {
    update = function(_,state)
      if not state:hasEventSubscriptions() then state:subscribeToEvent("builder.proposalCreate") end
    end,
    guiUpdate = function(_, _, guiState)
      local refreshed,refreshError = pcall(refreshReplay)
      if not refreshed then write("REPLAY RELOAD FAILED " .. tostring(refreshError)) end
      replay.step()
      local state = guiState:get() or {}
      if state.diagnosticRevision == revision then return end
      write("REPLAY LOADER directory=" .. tostring(physicalRoot) .. "; loader=" .. type(deployment.loader or loadfile)
        .. "; resourceLoader=" .. type(resolveutil))
      local ok, error = pcall(limits)
      if not ok then write("LIMIT READ FAILED " .. tostring(error)) end
      state.diagnosticRevision = revision
      guiState:set(state)
    end,
    guiHandleEvent = function(_, _, _, _, _, name, param)
      local ok, error = pcall(preview,name,param)
      if not ok then write("PREVIEW READ FAILED " .. tostring(error)) end
      return {}
    end,
  }
end
