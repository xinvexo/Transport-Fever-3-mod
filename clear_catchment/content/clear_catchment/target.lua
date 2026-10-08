local target = {}

function target.isStation(definition, entity)
  if not definition then return false end
  local action = definition.action
  if action == "ACTION_STREET_TERMINAL_BUILDER" then
    if not definition.resName then return false end
    local id = api.res.constructionRep.find(definition.resName)
    if id < 0 then return false end
    local desc = api.res.constructionRep.get(id)
    local edge = desc and desc.edgeObject
    return edge ~= nil and (edge.catchmentPassengers == true or edge.catchmentCargo == true)
  end
  if action == "ACTION_CONSTRUCTION_BUILDER" then
    -- This is the native station HUD signature, including station templates.
    -- Depots and warehouses also show station icons but do not show districts.
    local hud = definition.hudIcons
    if not hud or not hud.showDistricts then return false end
    for _, component in ipairs(hud.componentTypes or {}) do
      if component == api.type.ComponentType.STATION_GROUP then return true end
    end
    return false
  end
  if action == "ACTION_MODULE_BUILDER" or action == "ACTION_MODULE_BULLDOZER" then
    if not entity or not api.engine.entityExists(entity) then return false end
    local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
    return construction ~= nil and construction.stations ~= nil and #construction.stations > 0
  end
  return false
end

return target
