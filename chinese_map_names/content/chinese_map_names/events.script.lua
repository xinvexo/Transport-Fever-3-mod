local planner = ug_require "xin_chinese_map_names_1::/chinese_map_names/plan.lua"
local queue = ug_require "xin_chinese_map_names_1::/chinese_map_names/queue.lua"
local names = ug_require "xin_chinese_map_names_1::/chinese_map_names/entity_names.lua"
local batchSize = 64
local prepareRevision = 8

local function isEditor()
  return (api.engine.config.getModParams()[""] or {}).isMapEditor == true
end

local function validPlan(entries)
  if type(entries) ~= "table" then return false end
  for _, entry in ipairs(entries) do
    if type(entry) ~= "table" or type(entry.entity) ~= "number"
      or type(entry.before) ~= "string" or type(entry.after) ~= "string"
      or type(entry.attempts) ~= "number" then return false end
  end
  return true
end

local function newJob()
  return { started = true, prepareRevision = prepareRevision, prepareAttempts = 0,
    cursor = 1, renamed = 0, failed = 0, skipped = 0, retained = 0 }
end

function data()
  return {
    handleEvent = function(_, state, _, id, name)
      if id ~= "" or name ~= "initNewGameFromMap" or isEditor() then return end
      local current = state:get() or {}
      if current.started then return end
      -- Persist authorization first; transient resource/initialization failures
      -- may then recover on a later update without affecting ordinary saves.
      state:set(newJob())
    end,

    update = function(_, state)
      local current = state:get() or {}
      if not current.started or current.done then return end
      if isEditor() then return end
      if current.prepareRevision ~= prepareRevision then
        -- The user explicitly declined changes to older names/saves. Retire
        -- stale queues once, without scanning or sending any rename commands.
        current.done, current.entries, current.stoppedByRevision = true, nil, prepareRevision
        state:set(current)
        log.message("[Chinese Map Names] Older task stopped; existing names were left unchanged.")
        return
      end
      if current.entries ~= nil and type(current.entries) ~= "table" then
        -- Revision 3 could save the pcall success flag as the queue. No rename
        -- was executed in that case; discard it before any length/index use.
        log.warning("[Chinese Map Names] Discarding invalid saved name queue: " .. type(current.entries))
        current.entries, current.cursor, current.prepareAttempts = nil, 1, 0
        state:set(current)
      end
      if not current.entries then
        if current.prepareAttempts >= 3 then return end
        current.prepareAttempts = current.prepareAttempts + 1
        local ok, entries = pcall(function()
          local towns = ug_require "::/names/china/zh_CN/towns.lua"
          local streets = ug_require "::/names/china/zh_CN/streets.lua"
          return planner.build(towns, streets)
        end)
        if not ok or not validPlan(entries) then
          state:set(current)
          log.warning("[Chinese Map Names] Could not prepare names (attempt "
            .. current.prepareAttempts .. "): " .. (ok and ("invalid plan result: " .. type(entries)) or tostring(entries)))
          return
        end
        current.entries, current.queueRevision, current.dependencyIndexes = entries, nil, nil
        state:set(current)
        log.message("[Chinese Map Names] Prepared " .. #entries .. " existing names for a new map game.")
      end
      local entries = current.entries
      if current.queueRevision ~= prepareRevision then
        queue.prepare(entries)
        current.dependencyIndexes = nil
        current.queueRevision, current.prepareRevision, current.cursor = prepareRevision, prepareRevision, 1
        queue.report(current)
      end
      if not current.dependencyIndexes then
        -- Add indices to an in-flight revision-8 save without replaying,
        -- reordering, resetting retries, or retiring its existing task.
        current.dependencyIndexes = queue.indexDependencies(entries)
      end
      current.tick = (current.tick or 0) + 1
      while entries[current.cursor] and entries[current.cursor].done do current.cursor = current.cursor + 1 end
      if current.cursor > #entries then
        current.done, current.entries, current.dependencyIndexes = true, nil, nil
        local ok, report = pcall(planner.audit)
        if ok then
          current.audit = report
          for _, sample in ipairs(report.samples) do
            log.warning("[Chinese Map Names] Remaining " .. sample.category .. " name, entity "
              .. sample.entity .. ": " .. string.format("%q", sample.name))
          end
        else
          current.auditError = tostring(report)
          log.warning("[Chinese Map Names] Remaining-name check failed: " .. current.auditError)
        end
        state:set(current)
        log.message("[Chinese Map Names] Finished: " .. current.renamed .. " renamed, "
          .. (current.retained or 0) .. " inherited Chinese names retained, " .. current.skipped .. " changed/removed, "
          .. current.failed .. " failed; remaining foreign names: " .. (ok and report.remaining or "unknown") .. ".")
        return
      end
      local submitted = 0
      -- A finite active queue, not a periodic world scan: batch independent
      -- names, and wait only for actual parent/stem dependencies.
      for index = current.cursor, #entries do
        local entry = entries[index]
        if not entry.done then
          local exists = api.engine.entityExists(entry.entity)
          local value = exists and api.engine.getComponent(entry.entity, api.type.ComponentType.NAME)
          local own = value and value.name ~= "" and value.name or nil
          local name = own
          if exists and not own and entry.readDisplay then name = api.engine.util.getEntityName(entry.entity) end
          if name == entry.after then
            entry.done = true
            if entry.readDisplay and not own then
              current.retained = (current.retained or 0) + 1
            else
              current.renamed = current.renamed + 1
            end
          elseif not exists or (entry.readDisplay and own) or (not entry.readDisplay and name ~= entry.before) then
            -- New explicit NAME on a previously computed entity is an external
            -- edit. A computed display changing with its renamed parent is not.
            entry.done, current.skipped = true, current.skipped + 1
          elseif entry.readDisplay and not planner.needsChineseName(name) then
            entry.done, current.retained = true, (current.retained or 0) + 1
          elseif not value then
            -- Legacy queues can contain computed station/person/street names.
            -- Wait for their parent if needed, but NEVER submit a name write
            -- on an entity without NAME, regardless of its visible title.
            if queue.ready(entry, entries, current.dependencyIndexes) then
              entry.done, current.skipped = true, current.skipped + 1
              current.missingName = (current.missingName or 0) + 1
              if current.missingName <= 5 then
                log.warning("[Chinese Map Names] Kept computed name without NAME component, entity " .. entry.entity)
              end
            end
          elseif queue.ready(entry, entries, current.dependencyIndexes) and (not entry.retryAt or current.tick >= entry.retryAt) then
            if entry.nativeTown and (not api.engine.entityExists(entry.nativeTown)
              or names.ownName(entry.nativeTown) ~= entry.nativeTownName) then
              entry.done, current.skipped = true, current.skipped + 1
              log.warning("[Chinese Map Names] Town name changed before construction rename, entity " .. entry.entity)
            elseif entry.nativeOwner and (not api.engine.entityExists(entry.nativeOwner)
              or names.ownName(entry.nativeOwner) ~= entry.after) then
              entry.done, current.skipped = true, current.skipped + 1
              log.warning("[Chinese Map Names] Parent construction name was not confirmed; station group kept, entity " .. entry.entity)
            elseif entry.attempts >= 3 then
              entry.done, current.failed = true, current.failed + 1
              log.warning("[Chinese Map Names] Rename did not change the name for entity " .. entry.entity)
            else
              entry.attempts, entry.retryAt = entry.attempts + 1, current.tick + 2
              local ok, sent = pcall(names.submitName, entry.entity, entry.after)
              if not ok or sent then submitted = submitted + 1 end
              if ok and not sent then
                entry.done, current.skipped = true, current.skipped + 1
              elseif not ok then
                log.warning("[Chinese Map Names] Rename command error: " .. tostring(sent))
              end
              local changed = api.engine.entityExists(entry.entity)
                and api.engine.getComponent(entry.entity, api.type.ComponentType.NAME)
              if not entry.done and changed and changed.name == entry.after then
                entry.done, current.renamed = true, current.renamed + 1
              end
            end
          end
        end
        if submitted >= batchSize then break end
      end
      if not current.mapLabelsReported and queue.mapLabelsDone(entries) then
        current.mapLabelsReported = true
        queue.report(current) -- Only the city/facility completion transition.
      end
      -- Save once per batch instead of copying a large queue per resident.
      state:set(current)
    end,
  }
end
