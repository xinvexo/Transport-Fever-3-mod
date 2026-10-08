-- Logs the result the builder has already computed. No GUI-update callback,
-- geometry sampling, proposal cloning, native replay, or commands.
local seen,count = {},0
local function observe(name,param)
  if name~="builder.proposalCreate" or count>=256 then return end
  local proposal,result = param and param[1],param and param[2]
  if not proposal or not result then return end
  for _,item in ipairs(proposal.toAdd or {}) do
    local file = tostring(item.fileName)
    if file:find("xin_interchange_pack_1::/interchanges/",1,true) then
      local params = {}
      for key,value in pairs(item.construction and item.construction.params or {}) do
        if key~="seed" and key~="rotation" and key~="height" and (type(value)=="number" or type(value)=="string") then
          params[#params+1]=key.."="..tostring(value)
        end
      end
      table.sort(params)
      local state,errors = result.errorState or {},{}
      for _,value in ipairs(state.messages or {}) do errors[#errors+1]=tostring(value) end
      table.sort(errors)
      local external,internal = 0,0
      for _,collision in ipairs((result.collisionInfo or {}).collisionEntities or {}) do
        if collision.entity>0 then external=external+1 else internal=internal+1 end
      end
      local key=file.."; "..table.concat(params,",").."; critical="..tostring(state.critical)
        .."; errors="..table.concat(errors," | ").."; external="..tostring(external>0)
      if not seen[key] then
        seen[key],count=true,count+1
        log.message("[Interchange Preview r17] "..key.."; internalCollisions="..internal)
      end
    end
  end
end

function data()
  return {
    update = function(_,state)
      if not state:hasEventSubscriptions() then state:subscribeToEvent("builder.proposalCreate") end
    end,
    guiHandleEvent = function(_,_,_,_,_,name,param)
      local ok,failure=pcall(observe,name,param)
      if not ok and not seen.failure then
        seen.failure=true
        log.message("[Interchange Preview r17] log read failed: "..tostring(failure))
      end
      return {}
    end,
  }
end
