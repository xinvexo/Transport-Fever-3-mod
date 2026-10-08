-- Compatibility entry point for saves that still reference names.script@update.
-- Vehicle renaming is retired; never issue a name command here.
function data()
  return { update = function() end }
end
