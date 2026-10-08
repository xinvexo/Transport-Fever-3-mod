local rows = ug_require "xin_station_rows_1::/station_rows/rows.lua"
local table_util = ug_require "::/scripts/table_util.tl"
local proposal = {}

local STATION = "::/stations/rail/modular_station/modular_station.con"

function proposal.isSupported(construction)
  return construction ~= nil and construction.fileName == STATION
end

local function moduleName(module)
  return module and module.name
end

local function selectedModule(moduleResName)
  if moduleResName == nil then return nil, nil end
  local moduleId = api.res.moduleRep.find(moduleResName)
  if moduleId < 0 then return nil, nil end
  local module = api.res.moduleRep.get(moduleId)
  return module.type, {
    name = moduleResName,
    variant = 0,
    metadata = module.metadata,
    updateScript = {
      fileName = module.updateScript.fileName,
      params = module.updateScript.params,
    },
  }
end

local function hasCandidate(construction, slotId, moduleType)
  for _, slot in ipairs(construction.slots) do
    if slot.id == slotId and (moduleType == nil or slot.type == moduleType) then return true end
  end
  return false
end

function proposal.remaining(beforeModules, afterModules, selectedModuleName)
  local added, removed = {}, {}
  for id, before in pairs(beforeModules) do
    local after = afterModules[id]
    if after == nil then
      removed[#removed + 1] = id
    elseif moduleName(before) ~= moduleName(after) then
      return nil
    end
  end
  for id in pairs(afterModules) do
    if beforeModules[id] == nil then added[#added + 1] = id end
  end

  local slotId
  if selectedModuleName ~= nil then
    if #added ~= 1 or #removed ~= 0 then return nil end
    slotId = added[1]
    if moduleName(afterModules[slotId]) ~= selectedModuleName
      or not rows.canAdd(beforeModules, slotId) then return nil end
  else
    if #added ~= 0 or #removed == 0 then return nil end
    for _, id in ipairs(removed) do
      if not rows.isRowSlot(id) then return nil end
      if id < 10000000 then
        if slotId then return nil end
        slotId = id
      end
    end
    if slotId then
      for _, id in ipairs(removed) do
        -- Slot families differ by multiples of 100,000; the remainder identifies (i, j).
        if id ~= slotId and (id < 10000000 or id % 100000 ~= slotId % 100000) then
          return nil
        end
      end
    elseif #removed == 1 then
      slotId = removed[1]
    else
      return nil
    end
  end

  local params = { modules = table_util.copy(beforeModules) }
  rows.apply(params, {
    added = selectedModuleName ~= nil,
    slotId = slotId,
    module = selectedModuleName and { name = selectedModuleName } or nil,
  })

  local steps = {}
  if selectedModuleName ~= nil then
    for id, module in pairs(params.modules) do
      if afterModules[id] == nil then
        steps[#steps + 1] = { slotId = id, moduleResName = module.name }
      end
    end
  else
    for id in pairs(beforeModules) do
      if params.modules[id] == nil and afterModules[id] ~= nil then
        steps[#steps + 1] = { slotId = id }
      end
    end
  end

  table.sort(steps, function(first, second)
    if selectedModuleName ~= nil then
      local firstDistance, secondDistance = math.abs(first.slotId - slotId), math.abs(second.slotId - slotId)
      if firstDistance ~= secondDistance then return firstDistance < secondDistance end
    else
      -- Roof and addon families are above 10,000,000; remove them before platforms.
      local firstAttachment, secondAttachment = first.slotId >= 10000000, second.slotId >= 10000000
      if firstAttachment ~= secondAttachment then return firstAttachment end
      local firstPosition, secondPosition = (first.slotId + 500) % 1000, (second.slotId + 500) % 1000
      if firstPosition ~= secondPosition then return firstPosition < secondPosition end
    end
    return first.slotId < second.slotId
  end)
  return { steps = steps }
end

function proposal.makeStep(entity, step)
  if not api.engine.entityExists(entity) then return nil, "Station no longer exists." end
  local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
  if not proposal.isSupported(construction) then return nil, "Unsupported station." end
  if not rows.isRowSlot(step.slotId) then return nil, "Unsupported module slot." end

  local modules = construction.params.modules or {}
  local old = modules[step.slotId]
  if step.moduleResName and not rows.canAdd(modules, step.slotId) then return nil end
  if moduleName(old) == step.moduleResName then return nil end

  local moduleType, selected = selectedModule(step.moduleResName)
  if step.moduleResName ~= nil and not selected then return nil, "Module is unavailable." end
  if not hasCandidate(construction, step.slotId, moduleType) then return nil, "Module slot is unavailable." end

  local params = table_util.copy(construction.params)
  params.modules = params.modules or {}
  params.modules[step.slotId] = selected
  local candidate = api.engine.util.proposal.createProposalReplaceConstruction(entity, params)
  if not candidate then return nil, "Could not create module proposal." end
  return candidate
end

return proposal
