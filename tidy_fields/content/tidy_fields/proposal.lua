local table_util = ug_require "::/scripts/table_util.tl"
local layout = ug_require "xin_tidy_fields_1::/tidy_fields/layout.lua"
local proposal = {}

proposal.layouts = {
  { value = "left", label = "左边" },
  { value = "right", label = "右边" },
  { value = "front", label = "前边" },
  { value = "back", label = "后边" },
  { value = "left_right", label = "左右" },
  { value = "left_front", label = "左前" },
  { value = "left_back", label = "左后" },
  { value = "right_front", label = "右前" },
  { value = "right_back", label = "右后" },
  { value = "front_back", label = "前后" },
  { value = "left_right_front", label = "左、右、前" },
  { value = "left_right_back", label = "左、右、后" },
  { value = "left_front_back", label = "左、前、后" },
  { value = "right_front_back", label = "右、前、后" },
  { value = "all", label = "全部" },
}

local supported = {
  ["::/industries/farm/farm.con"] = true,
  ["::/industries/livestock_farm/livestock_farm.con"] = true,
  ["::/industries/cotton_farm/cotton_farm.con"] = true,
  ["::/industries/rubber_farm/rubber_farm.con"] = true,
  ["::/industries/forest/forest.con"] = true,
}

function proposal.describeFailure(data)
  local errors = data and data.errorState
  if errors and errors.messages and errors.messages[1] then
    return string.format(_("Could not tidy: %s"), errors.messages[1])
  end
  return _("The game rejected construction. See the game log for details.")
end

local function pointOnLand(x, y, transform)
  local world = transform:transformPosition(api.type.Vec3f.new(x, y, 0))
  local point = api.type.Vec2f.new(world.x, world.y)
  return api.engine.terrain.isValidCoordinate(point) and not api.engine.terrain.isOnWater(point)
end

local function isLand(field, transform)
  local x, y = field.pos[1], field.pos[2]
  local halfX, halfY = field.size[1] / 2, field.size[2] / 2
  if not pointOnLand(x, y, transform) then return false end
  local nx, ny = math.ceil(field.size[1] / 10), math.ceil(field.size[2] / 10)
  for i = 0, nx do
    for j = 0, ny do
      if not pointOnLand(x - halfX + field.size[1] * i / nx, y - halfY + field.size[2] * j / ny, transform) then
        return false
      end
    end
  end
  return true
end

local function isConnected(first, second, transform)
  local dx, dy = second[1] - first[1], second[2] - first[2]
  local steps = math.max(1, math.ceil(math.sqrt(dx * dx + dy * dy) / 4))
  for i = 0, steps do
    if not pointOnLand(first[1] + dx * i / steps, first[2] + dy * i / steps, transform) then
      return false
    end
  end
  return true
end

function proposal.isSupported(construction)
  return construction ~= nil and supported[construction.fileName] == true
end

function proposal.getTarget(industry)
  if not api.engine.entityExists(industry) then return nil end
  local entity = api.engine.system.streetConnectorSystem.getConstructionEntityForSubconstruction(industry)
  if not entity or entity < 0 or not api.engine.entityExists(entity) then return nil end
  local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
  if not proposal.isSupported(construction) then return nil end
  return entity, construction
end

function proposal.make(entity, mode)
  mode = mode or "all"
  local valid = false
  for _, option in ipairs(proposal.layouts) do
    if option.value == mode then valid = true; break end
  end
  if not valid then return nil, nil, _("Select a plot layout.") end
  if not api.engine.entityExists(entity) then return nil, nil, _("The industry no longer exists.") end
  local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
  if not proposal.isSupported(construction) then return nil, nil, _("This industry does not support plot rearrangement.") end
  local owner = api.engine.getComponent(entity, api.type.ComponentType.PLAYER_OWNED)
  if owner and owner.player ~= api.engine.util.getPlayer() then
    return nil, nil, _("Cannot tidy another company's industry.")
  end

  local desc = api.res.constructionRep.get(api.res.constructionRep.find(construction.fileName))
  local config = desc.updateScript.params.fieldConfig
  local params = table_util.copy(construction.params)
  params.upgrade = true
  params.xinTidyFields = true
  params.xinTidyLayout = mode
  params.xinTidyFieldOrder = layout.makeOrder(params.modules or {}, #config.fields)
  local fields, reason, availableSlots = layout.plan(config, params, function(field)
    return isLand(field, construction.transf)
  end, function(first, second)
    return isConnected(first, second, construction.transf)
  end)
  if not fields then return nil, nil, _(reason) end
  params.xinTidyFieldLayout = fields
  params.xinTidyFieldSlots = availableSlots
  local candidate = api.engine.util.proposal.createProposalReplaceConstruction(entity, params)
  if not candidate then return nil, nil, _("Could not prepare a plot layout.") end

  local context = api.type.Context.new()
  context.player = api.engine.util.getPlayer()
  return candidate, context
end

return proposal
