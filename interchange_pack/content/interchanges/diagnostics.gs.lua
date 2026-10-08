local config = require "xin_interchange_pack_1::/interchanges/diagnostic_config.lua"

function data()
  if config.enabled ~= true then
    if config.observe then
      return {
        updateScript = { fileName = "preview_observer.script@update" },
        guiHandleEventScript = { fileName = "preview_observer.script@guiHandleEvent" },
      }
    end
    return {}
  end
  return {
    updateScript = { fileName = "diagnostics.script@update" },
    guiUpdateScript = { fileName = "diagnostics.script@guiUpdate" },
    guiHandleEventScript = { fileName = "diagnostics.script@guiHandleEvent" },
  }
end
