local config = require "xin_interchange_pack_1::/interchanges/diagnostic_config.lua"
function data()
  if not config.validateTwelve then return {} end
  return {
    updateScript = {fileName="validate_twelve.script@update"},
    guiUpdateScript = {fileName="validate_twelve.script@guiUpdate"},
    guiHandleEventScript = {fileName="validate_twelve.script@guiHandleEvent"},
  }
end
