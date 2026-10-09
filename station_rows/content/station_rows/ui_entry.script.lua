local builtin = ug_require "::/gui/main/builtin.lua"
local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local proposals = ug_require "xin_station_rows_1::/station_rows/proposal.lua"

local moduleTypes = {
  track = true, cargo_platform = true, passenger_platform = true,
  passenger_platform_roof = true, passenger_platform_addon = true,
}
local target, sent
local busy = false

local function syncTarget(pressed)
  local desired = pressed and not busy and target or nil
  if desired and sent and desired.entity == sent.entity and desired.module == sent.module then return end
  if not desired and not sent then return end
  sent = desired and { entity = desired.entity, module = desired.module } or nil
  api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "xin_station_rows", "stationRowsTarget", sent or {}))
end

local nativeAction = builtin.ConstructionAction
builtin.ConstructionAction = function(params)
  local previous = target
  target = nil
  local builder = params.moduleBuilder or params.moduleBulldozer
  if builder and previous and previous.entity == builder.constructionEntity
    and not api.engine.entityExists(builder.constructionEntity) then
    -- A completed replacement is forwarded from the simulation on the next GUI update.
    target = previous
  end
  if builder and api.engine.entityExists(builder.constructionEntity) then
    local construction = api.engine.getComponent(builder.constructionEntity, api.type.ComponentType.CONSTRUCTION)
    if proposals.isSupported(construction) then
      local supported = params.moduleBuilder == nil
      if params.moduleBuilder then
        local id = api.res.moduleRep.find(builder.moduleResName)
        supported = id >= 0 and moduleTypes[api.res.moduleRep.get(id).type]
      end
      if supported then
        target = { entity = builder.constructionEntity,
          module = params.moduleBuilder and builder.moduleResName or nil }
        -- The key event queues the snapshot before the following native mouse command.
        react.useInputAction("IA_PRECISION_MODE", react.iaHandlerExtended(function(data)
          local status = api.gui.inputAction.InvokeData.Status
          if data.status == status.Triggered then
            syncTarget(true)
          elseif data.status == status.EndReleased or data.status == status.EndAborted then
            syncTarget(false)
          end
        end))
      end
    end
  end
  syncTarget(api.gui.inputAction.modifierOnlyActionIsActive("IA_PRECISION_MODE"))
  return nativeAction(params)
end

local entry = react.RegisterPluginRecipe(
  entryPoint.ModEntryPointExtension, "XinStationRowsEntry", function()
    react.onMount(function()
      api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "xin_station_rows", "stationRowsFinished", {}))
    end)
    react.onEvent("constructionMenuQuit", function()
      target = nil
      syncTarget(false)
    end)
    react.onEvent("xinStationRowsTargetChanged", function(_, change)
      local previous = target or sent
      if not previous or previous.entity ~= change.sourceEntity then return end
      target = { entity = change.entity, module = previous.module }
      if sent and sent.entity == change.sourceEntity then
        sent = { entity = change.entity, module = sent.module }
      end
      api.gui.fireReactEvent("setModuleBuilderEntity", change.entity)
    end)
    react.onEvent("xinStationRowsStarted", function()
      busy = true
      syncTarget(false)
    end)
    react.onEvent("xinStationRowsFinished", function()
      busy = false
      sent = nil
      syncTarget(api.gui.inputAction.modifierOnlyActionIsActive("IA_PRECISION_MODE"))
    end)
    return nil
  end
)
log.message("[Station Rows] Native module controls loaded (revision 17).")

function data()
  return { entry = entry }
end
