from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime


CONTENT = Path(__file__).resolve().parents[1] / "content/station_rows"


class NativeStationRowsTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            function copy(value)
                if type(value) ~= 'table' then return value end
                local result = {}
                for key, item in pairs(value) do result[key] = copy(item) end
                return result
            end
            function module(name)
                return {name = name, variant = 0, metadata = {capacity = 32},
                    updateScript = {fileName = name .. '.script', params = {}}}
            end
            function state()
                return {
                    value = {}, subscriptions = {},
                    get = function(self) return copy(self.value) end,
                    set = function(self, value) self.value = copy(value) end,
                    subscribeToNoEvents = function(self) self.subscriptions = {} end,
                    subscribeToEvent = function(self, name)
                        self.subscriptions[#self.subscriptions + 1] = name
                    end,
                }
            end
            engineState, guiState = state(), state()
            components, commands, originals, sent = {}, {}, {}, {}
            commandQueue, guiCallbacks, emitted, warnings = {}, {}, {}, {}
            inputActions, reactEvents = {}, {}
            lane, shift = 'gui', false
            builtin = {ConstructionAction = function(params)
                return {kind = 'NativeAction', params = params}
            end}
            react = {
                RegisterPluginRecipe = function(extension, name, render) return render end,
                onMount = function(callback) callback() end,
                onEvent = function(name, callback) reactEvents[name] = callback end,
                onStep = function() error('Station rows must use input events, not frame polling') end,
                useInputAction = function(name, handler) inputActions[name] = handler end,
                iaHandlerExtended = function(callback)
                    return {callback = callback}
                end,
            }
            log = {
                message = function() end,
                warning = function(message) warnings[#warnings + 1] = message end,
            }
            api = {
                type = {ComponentType = {CONSTRUCTION = 'CONSTRUCTION'},
                    Context = {new = function() return {} end}},
                engine = {
                    entityExists = function(entity)
                        assert(type(entity) == 'number', 'Entity APIs require an ID, not a revision pair')
                        return components[entity] ~= nil
                    end,
                    getComponent = function(entity, kind)
                        return copy(components[entity] and components[entity][kind])
                    end,
                    util = {
                        getPlayer = function() return 7 end,
                        proposal = {createProposalReplaceConstruction = function(entity, params)
                            return {toRemove = {entity}, toAdd = {{
                                fileName = components[entity].CONSTRUCTION.fileName,
                                construction = {params = copy(params)},
                            }}}
                        end},
                    },
                },
                gui = {
                    inputAction = {InvokeData = {Status = {
                        Triggered = 'Triggered', EndReleased = 'EndReleased', EndAborted = 'EndAborted',
                    }}, modifierOnlyActionIsActive = function(name)
                        assert(name == 'IA_PRECISION_MODE')
                        return shift
                    end},
                    construction = {
                        getRefundableEntities = function() return {88} end,
                        updateRefundableEntities = function(entities, proposal)
                            refunded = {entities = copy(entities), proposal = proposal}
                        end,
                    },
                    fireReactEvent = function(name, ...)
                        assert(lane == 'gui', 'React events belong to the GUI lane')
                        local payload = {...}
                        emitted[#emitted + 1] = {name = name, payload = copy(payload)}
                        if name == 'setModuleBuilderEntity' then
                            menuTarget = payload[1]
                            local builder = uiParams.moduleBuilder or uiParams.moduleBulldozer
                            builder.constructionEntity = menuTarget
                            renderNative()
                        end
                        if reactEvents[name] then reactEvents[name](name, ...) end
                    end,
                },
                res = {moduleRep = {
                    find = function(name) return name == 'cargo.module' and 1 or -1 end,
                    get = function(id)
                        local result = module('cargo.module')
                        result.type = 'cargo_platform'
                        return result
                    end,
                }},
                cmd = {
                    makeScriptingSendEventCmd = function(fileName, id, name, params)
                        return {kind = 'script', fileName = fileName, id = id, name = name, params = copy(params)}
                    end,
                    makeWorldBuildProposalCmd = function(proposal, context, ignoreErrors, playerInitiated)
                        return {kind = 'world', proposal = proposal, context = context,
                            ignoreErrors = ignoreErrors, playerInitiated = playerInitiated}
                    end,
                    sendCommand = function(command, callback)
                        assert(not callback or lane == 'gui', 'engine cannot receive command callbacks')
                        sent[#sent + 1] = command
                        commandQueue[#commandQueue + 1] = {command = command, callback = callback}
                        if command.kind == 'world' and not command.native then
                            local index = #commands + 1
                            commands[index] = command
                            originals[index] = copy(components[command.proposal.toRemove[1]].CONSTRUCTION.params.modules)
                        end
                    end,
                },
            }
            modules = {
                ['::/gui/main/builtin.lua'] = builtin,
                ['::/gui/main/react.lua'] = react,
                ['::/gui/main/mod_entry_point.tl'] = {ModEntryPointExtension = 'extension'},
                ['::/scripts/table_util.tl'] = {copy = copy},
                ['::/scripts/entity_util.tl'] = {entityChanged = function(value)
                    return not api.engine.entityExists(value.entity)
                        or value.revision.num[1] < (components[value.entity].revision or 1)
                end},
            }
            function ug_require(name)
                assert(modules[name], 'unexpected module ' .. name)
                return modules[name]
            end
            local construction = {
                fileName = '::/stations/rail/modular_station/modular_station.con',
                params = {modules = {}, seed = 123}, slots = {},
            }
            for j = -2, 1 do
                construction.params.modules[8400000 + 10 * j] = module('rail.module')
                construction.params.modules[7401000 + 10 * j] = module('passenger.module')
                for _, kind in ipairs({
                    {6398000, 'cargo_platform'}, {7401000, 'passenger_platform'},
                    {10401000, 'passenger_platform_roof'}, {10801000, 'passenger_platform_addon'},
                }) do
                    construction.slots[#construction.slots + 1] = {id = kind[1] + 10 * j, type = kind[2]}
                end
            end
            components[10] = {CONSTRUCTION = construction}
            currentEntity, menuTarget = 10, 10
            uiParams = {moduleBuilder = {constructionEntity = 10, moduleResName = 'cargo.module'}}
            function renderNative() node = builtin.ConstructionAction(uiParams) end
            function press()
                shift = true
                inputActions.IA_PRECISION_MODE.callback({status = 'Triggered'})
            end
            function release()
                shift = false
                inputActions.IA_PRECISION_MODE.callback({status = 'EndReleased'})
            end
            function guiStep() end
            function nativeEdit(changes)
                local params = copy(components[currentEntity].CONSTRUCTION.params)
                for id, name in pairs(changes) do params.modules[id] = name and module(name) or nil end
                local proposal = api.engine.util.proposal.createProposalReplaceConstruction(currentEntity, params)
                local command = api.cmd.makeWorldBuildProposalCmd(proposal, {player = 7}, false, true)
                command.native = true
                api.cmd.sendCommand(command, function(result, success)
                    if success then renderNative() end
                end)
            end
            function executeNext(success, extraModules)
                local queued = assert(table.remove(commandQueue, 1), 'no queued command')
                local command = queued.command
                lane = 'engine'
                if command.kind == 'script' then
                    handlers.handleEvent(nil, engineState, nil, command.id, command.name, copy(command.params))
                else
                    if success == nil then success = true end
                    local ids = {}
                    if success then
                        local old = command.proposal.toRemove[1]
                        local new = old + 1
                        components[new] = copy(components[old])
                        components[new].CONSTRUCTION.params = copy(command.proposal.toAdd[1].construction.params)
                        for id, item in pairs(extraModules or {}) do
                            components[new].CONSTRUCTION.params.modules[id] = copy(item)
                        end
                        components[new].EMPTY_CONSTRUCTION =
                            next(components[new].CONSTRUCTION.params.modules) == nil and {} or nil
                        components[old] = nil
                        currentEntity, ids = new, {new}
                    end
                    local data = {errorState = {critical = not success, messages = {}}}
                    handlers.handleEvent(nil, engineState, nil, 'apply_command', 'onPostBuildProposal',
                        {command.proposal, data, ids, command.playerInitiated})
                    if queued.callback then
                        local revisions = {}
                        for _, entity in ipairs(ids) do
                            revisions[#revisions + 1] = {entity, {num = {components[entity].revision or 1, 0, 0}}}
                        end
                        guiCallbacks[#guiCallbacks + 1] = {callback = queued.callback, success = success,
                            result = {resultEntities = revisions, proposal = {proposal = command.proposal}}}
                    end
                end
                lane = 'gui'
                return command.kind
            end
            function flushScripts()
                while commandQueue[1] and commandQueue[1].command.kind == 'script' do executeNext() end
            end
            function runCallbacks()
                while #guiCallbacks > 0 do
                    local item = table.remove(guiCallbacks, 1)
                    item.callback(item.result, item.success)
                end
            end
            function claim() handlers.guiUpdate(nil, engineState, guiState) end
            function changedSlots(index)
                local before = originals[index]
                local after = commands[index].proposal.toAdd[1].construction.params.modules
                local result = {}
                for id, old in pairs(before) do
                    if not after[id] or after[id].name ~= old.name then result[#result + 1] = id end
                end
                for id in pairs(after) do
                    if not before[id] then result[#result + 1] = id end
                end
                return result
            end
        """)
        for name in ("rows", "proposal", "sequence"):
            self.lua.globals().modules[
                f"xin_station_rows_1::/station_rows/{name}.lua"
            ] = self.lua.execute((CONTENT / f"{name}.lua").read_text(encoding="utf-8"))
        self.lua.execute((CONTENT / "events.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("handlers = data(); lane = 'engine'; handlers.update(nil, engineState); lane = 'gui'; claim()")
        self.lua.execute((CONTENT / "ui_entry.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("data().entry(); flushScripts(); sent = {}; renderNative()")
        self.lua.execute("sequence = modules['xin_station_rows_1::/station_rows/sequence.lua']")

    def start_native_addition(self):
        self.lua.execute("press(); nativeEdit({[6398000] = 'cargo.module'}); release(); executeNext(); executeNext(); flushScripts(); runCallbacks(); claim(); flushScripts()")

    def test_subscription_upgrade_replaces_old_listeners(self):
        self.lua.execute("""
            engineState.value = {listenerRevision = 14, nextId = 8}
            engineState.subscriptions = {'builder.proposalApply', 'builder.proposalPrepareForApply'}
            lane = 'engine'; handlers.update(nil, engineState); lane = 'gui'
        """)
        self.assertEqual(self.lua.eval("engineState.value.listenerRevision"), 15)
        self.assertEqual(set(self.lua.globals().engineState.subscriptions.values()), {
            "stationRowsTarget", "stationRowsFinished", "onPostBuildProposal",
        })

    def test_native_action_and_shift_target_sync_only_on_changes(self):
        self.assertEqual(self.lua.eval("node.kind"), "NativeAction")
        self.assertTrue(self.lua.eval("node.params == uiParams"))
        self.lua.execute("press(); guiStep(); renderNative(); guiStep()")
        self.assertEqual(self.lua.eval("#sent"), 1)
        self.assertEqual(self.lua.eval("sent[1].name"), "stationRowsTarget")
        self.assertEqual(self.lua.eval("sent[1].params.entity"), 10)
        self.lua.execute("release(); guiStep()")
        self.assertEqual(self.lua.eval("#sent"), 2)
        self.assertIsNone(self.lua.eval("sent[2].params.entity"))

    def test_shift_snapshot_precedes_native_edit_and_release_keeps_job(self):
        self.lua.execute("press(); nativeEdit({[6398000] = 'cargo.module'}); release()")
        self.assertEqual(self.lua.eval("commandQueue[1].command.name"), "stationRowsTarget")
        self.assertEqual(self.lua.eval("commandQueue[2].command.kind"), "world")
        self.assertIsNone(self.lua.eval("commandQueue[3].command.params.entity"))
        self.lua.execute("executeNext()")
        self.assertEqual(self.lua.eval("engineState.value.target.entity"), 10)
        self.lua.execute("executeNext()")
        self.assertFalse(self.lua.eval("api.engine.entityExists(10)"))
        self.assertEqual(self.lua.eval("#engineState.value.job.steps"), 3)
        self.assertEqual(self.lua.eval("engineState.value.job.entity"), 11)
        self.assertEqual(self.lua.eval("engineState.value.job.sourceEntity"), 10)
        self.lua.execute("executeNext(); runCallbacks(); claim(); flushScripts()")
        self.assertEqual(self.lua.eval("#commands"), 1)
        self.assertEqual(self.lua.eval("guiState.value.done"), self.lua.eval("engineState.value.job.id"))
        for index, slot in enumerate((6397990, 6398010, 6397980), 1):
            self.assertEqual(self.lua.eval("#commands"), index)
            self.assertEqual(self.lua.eval(f"#changedSlots({index})"), 1)
            self.assertEqual(self.lua.eval(f"changedSlots({index})[1]"), slot)
            self.assertEqual(self.lua.eval(f"commands[{index}].proposal.toRemove[1]"), 10 + index)
            self.lua.execute("claim(); executeNext()")
            self.assertEqual(self.lua.eval("#commands"), index)
            self.assertEqual(self.lua.eval("engineState.value.nextId"), 1)
            self.lua.execute("runCallbacks(); flushScripts()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertEqual(self.lua.eval("currentEntity"), 14)
        self.assertEqual(self.lua.eval("menuTarget"), 14)
        self.lua.execute("claim()")
        self.assertEqual(self.lua.eval("#commands"), 3)
        for j in range(-2, 2):
            self.assertEqual(self.lua.eval(f"components[14].CONSTRUCTION.params.modules[{6398000 + 10 * j}].name"), "cargo.module")
        self.assertEqual(self.lua.eval("#warnings"), 0)

    def test_zero_remaining_operations_still_follow_replacement_root(self):
        self.lua.execute("""
            components[10].CONSTRUCTION.params.modules = {
                [8400000] = module('rail.module'), [7401000] = module('passenger.module'),
            }
            press(); nativeEdit({[6398000] = 'cargo.module'}); executeNext(); executeNext()
            runCallbacks(); claim(); guiStep()
        """)
        self.assertEqual(self.lua.eval("#engineState.value.job.steps"), 0)
        self.assertEqual(self.lua.eval("uiParams.moduleBuilder.constructionEntity"), 11)
        self.assertEqual(self.lua.eval("#commands"), 0)
        self.assertEqual(self.lua.eval("#commandQueue"), 0)
        self.lua.execute("nativeEdit({[6398010] = 'cargo.module'}); executeNext(); runCallbacks(); claim()")
        self.assertEqual(self.lua.eval("engineState.value.job.sourceEntity"), 11)
        self.assertEqual(self.lua.eval("engineState.value.job.entity"), 12)
        self.assertEqual(self.lua.eval("uiParams.moduleBuilder.constructionEntity"), 12)
        self.assertEqual(self.lua.eval("guiState.value.done"), 2)
        self.assertEqual(self.lua.eval("#commands"), 0)

    def test_finished_sequence_rearms_for_next_operation_on_same_station(self):
        self.start_native_addition()
        for _ in range(3):
            self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
        self.assertEqual(self.lua.eval("uiParams.moduleBuilder.constructionEntity"), 14)
        self.lua.execute("""
            local slots = components[14].CONSTRUCTION.slots
            for j = -2, 1 do slots[#slots + 1] = {id = 6396000 + 10 * j, type = 'cargo_platform'} end
            press(); nativeEdit({[6396000] = 'cargo.module'}); release()
            executeNext(); executeNext(); flushScripts(); runCallbacks(); claim(); flushScripts()
        """)
        self.assertEqual(self.lua.eval("engineState.value.job.sourceEntity"), 14)
        self.assertEqual(self.lua.eval("engineState.value.job.id"), 2)
        self.assertEqual(self.lua.eval("changedSlots(4)[1]"), 6395990)
        for _ in range(3):
            self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
        self.assertEqual(self.lua.eval("#commands"), 6)
        self.assertEqual(self.lua.eval("currentEntity"), 18)
        self.assertEqual(self.lua.eval("uiParams.moduleBuilder.constructionEntity"), 18)
        self.assertFalse(self.lua.eval("engineState.value.busy"))

    def test_native_failure_or_ordinary_click_does_not_start_continuation(self):
        for tracked, success in ((True, False), (False, True)):
            with self.subTest(tracked=tracked, success=success):
                self.setUp()
                if tracked:
                    self.lua.execute("press(); executeNext()")
                self.lua.execute("nativeEdit({[6398000] = 'cargo.module'})")
                self.lua.globals().nativeSuccess = success
                self.lua.execute("executeNext(nativeSuccess); runCallbacks(); claim(); flushScripts()")
                self.assertEqual(self.lua.eval("#commands"), 0)
                self.assertFalse(self.lua.eval("sequence.running()"))
                self.assertEqual(self.lua.eval("currentEntity"), 11 if success else 10)

    def test_new_occupancy_in_rebuilt_station_is_skipped(self):
        self.start_native_addition()
        self.lua.execute("executeNext(true, {[7398010] = module('passenger.module')}); runCallbacks()")
        self.assertEqual(self.lua.eval("#commands"), 2)
        self.assertEqual(self.lua.eval("changedSlots(2)[1]"), 6397980)
        self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertEqual(self.lua.eval("components[13].CONSTRUCTION.params.modules[7398010].name"), "passenger.module")
        self.assertIsNone(self.lua.eval("components[13].CONSTRUCTION.params.modules[6398010]"))

    def test_rejected_step_stops_queue_and_clears_busy_after_gui_callback(self):
        self.start_native_addition()
        self.lua.execute("executeNext(); runCallbacks(); executeNext(false)")
        self.assertTrue(self.lua.eval("sequence.running()"))
        self.lua.execute("runCallbacks(); flushScripts(); claim()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertFalse(self.lua.eval("engineState.value.busy"))
        self.assertEqual(self.lua.eval("#commands"), 2)
        self.assertEqual(self.lua.eval("currentEntity"), 12)
        self.assertEqual(self.lua.eval("components[12].CONSTRUCTION.params.modules[6397990].name"), "cargo.module")
        self.assertEqual(self.lua.eval("#warnings"), 1)

    def test_changed_result_revision_stops_before_editing_again(self):
        self.start_native_addition()
        self.lua.execute("executeNext(); components[currentEntity].revision = 2; runCallbacks(); flushScripts()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertFalse(self.lua.eval("engineState.value.busy"))
        self.assertEqual(self.lua.eval("#commands"), 1)
        self.assertEqual(self.lua.eval("#refunded.entities"), 0)
        self.assertEqual(self.lua.eval("#warnings"), 1)

    def test_command_preparation_and_callback_errors_release_the_queue(self):
        for failing_api in (
            "api.type.Context.new",
            "api.gui.construction.getRefundableEntities",
            "api.gui.construction.updateRefundableEntities",
        ):
            with self.subTest(failing_api=failing_api):
                self.setUp()
                self.lua.execute(f"{failing_api} = function() error('unavailable native API') end")
                self.start_native_addition()
                if failing_api.endswith("updateRefundableEntities"):
                    self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
                self.assertFalse(self.lua.eval("sequence.running()"))
                self.assertFalse(self.lua.eval("engineState.value.busy"))
                self.assertEqual(self.lua.eval("#warnings"), 1)
                self.assertEqual(self.lua.eval("#commandQueue"), 0)

    def test_aborted_modifier_and_tool_changes_clear_the_snapshot_without_polling(self):
        self.lua.execute("press(); flushScripts()")
        self.assertEqual(self.lua.eval("engineState.value.target.entity"), 10)
        self.lua.execute("inputActions.IA_PRECISION_MODE.callback({status = 'EndAborted'}); flushScripts()")
        self.assertIsNone(self.lua.eval("engineState.value.target"))
        self.lua.execute("press(); flushScripts(); uiParams = {}; renderNative(); flushScripts()")
        self.assertIsNone(self.lua.eval("engineState.value.target"))
        self.lua.execute("""
            uiParams = {moduleBulldozer = {constructionEntity = 10}}
            renderNative(); flushScripts()
        """)
        self.assertEqual(self.lua.eval("engineState.value.target.entity"), 10)
        self.assertIsNone(self.lua.eval("engineState.value.target.module"))

    def test_held_modifier_rearms_after_completion_without_another_key_event(self):
        self.lua.execute("""
            press(); nativeEdit({[6398000] = 'cargo.module'})
            executeNext(); executeNext(); runCallbacks(); claim(); flushScripts()
        """)
        for _ in range(3):
            self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertEqual(self.lua.eval("engineState.value.target.entity"), 14)
        self.assertEqual(self.lua.eval("engineState.value.target.module"), "cargo.module")
        self.lua.execute("""
            for j = -2, 1 do
                local slots = components[14].CONSTRUCTION.slots
                slots[#slots + 1] = {id = 6396000 + 10 * j, type = 'cargo_platform'}
            end
            nativeEdit({[6396000] = 'cargo.module'})
            executeNext(); runCallbacks(); claim(); flushScripts()
        """)
        self.assertEqual(self.lua.eval("#commands"), 4)
        self.assertEqual(self.lua.eval("engineState.value.job.id"), 2)

    def test_new_gui_mount_clears_saved_pending_work(self):
        self.lua.execute("""
            engineState.value.busy = true
            engineState.value.job = {id = 12, entity = 10, steps = {{slotId = 6398000}}}
            engineState.value.target = {entity = 10}
            data().entry(); flushScripts(); claim()
        """)
        self.assertIsNone(self.lua.eval("engineState.value.job"))
        self.assertFalse(self.lua.eval("engineState.value.busy"))
        self.assertEqual(self.lua.eval("#commands"), 0)

    def test_native_dependency_deletion_continues_attachments_before_platforms(self):
        self.lua.execute("""
            local items = {}
            for j = -2, 1 do items[7401000 + 10 * j] = module('passenger.module') end
            for j = 0, 1 do
                items[10401000 + 10 * j] = module('roof.module')
                items[10801000 + 10 * j] = module('addon.module')
            end
            components[10].CONSTRUCTION.params.modules = items
            uiParams = {moduleBulldozer = {constructionEntity = 10}}
            renderNative(); press()
            nativeEdit({[7401010] = false, [10401010] = false, [10801010] = false})
            release(); executeNext(); executeNext(); flushScripts(); runCallbacks(); claim(); flushScripts()
        """)
        for index, slot in enumerate((10401000, 10801000, 7400980, 7400990, 7401000), 1):
            self.assertEqual(self.lua.eval("#commands"), index)
            self.assertEqual(self.lua.eval(f"#changedSlots({index})"), 1)
            self.assertEqual(self.lua.eval(f"changedSlots({index})[1]"), slot)
            self.lua.execute("executeNext(); runCallbacks(); flushScripts()")
        self.assertFalse(self.lua.eval("sequence.running()"))
        self.assertEqual(self.lua.eval("currentEntity"), 16)
        self.assertIsNotNone(self.lua.eval("components[16].EMPTY_CONSTRUCTION"))
        self.assertIsNone(self.lua.eval("next(components[16].CONSTRUCTION.params.modules)"))
        self.assertEqual(self.lua.eval("#warnings"), 0)


if __name__ == "__main__":
    unittest.main()
