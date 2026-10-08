local hooks = ug_require "xin_line_vehicle_colors_1::/line_vehicle_colors/hooks.lua"
local ok, reason = pcall(hooks.installGui)
if not ok then
  log.warning("[Line Vehicle Colors] Could not install GUI change hooks: " .. tostring(reason))
end
if not hooks.entry then
  local react = ug_require "::/gui/main/react.lua"
  local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
  hooks.entry = react.RegisterPluginRecipe(
    entryPoint.ModEntryPointExtension, "XinLineVehicleColorsEntry", function() return nil end
  )
end

function data()
  return { entry = hooks.entry }
end
