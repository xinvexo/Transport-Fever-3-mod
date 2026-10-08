from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class EventTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
          components, calls, warnings = {}, {}, {}
          function makeState()
            return {
              value = {},
              get = function(self) return self.value end,
              set = function(self, value) self.value = value end,
              hasEventSubscriptions = function(self) return self.subscribed end,
              subscribeToEvent = function(self, event) self.subscribed = event end,
            }
          end
          simulation, gui = makeState(), makeState()
          log = { warning = function(message) warnings[#warnings + 1] = message end }
          api = {
            engine = {
              getComponent = function(entity, kind)
                return components[entity] and components[entity][kind]
              end,
              util = { getPlayer = function() return 7 end },
              system = { streetSystem = {
                getNodeTrackSegments = function(node) return { 10 } end,
              } },
            },
            type = {
              ComponentType = { BASE_EDGE = 'base', EDGE_OBJECT = 'object' },
              enum = { EdgeObjectType = { SIGNAL = 2 } },
              Context = { new = function() return {} end },
            },
            cmd = {
              makeWorldBuildProposalCmd = function(proposal, context, ignore, player)
                return { proposal = proposal, context = context, player = player }
              end,
              sendCommand = function(command, callback)
                calls[#calls + 1] = command
                completion = callback
              end,
            },
          }
          networkFake = {
              plan = function(entity, minimum, layout)
                local phase = layout and layout.phase or 0.5
                return {
                entity = entity, minimum = minimum, count = 1,
                sourceEdges = {10}, positions = {phase * 1000},
              } end,
              proposal = function(plan) return plan end,
          }
          function ug_require()
            return networkFake
          end
          function place(entity, enabled, minimum, oldObjects, playerInitiated)
            components[entity] = { object = {
              params = { asEnabled = enabled, asMinimumSpacing = minimum }
            } }
            components[10] = { base = { node0 = 1, node1 = 2, objects = { { entity, 2 } } } }
            local street = {
              addedSegments = { { comp = components[10].base }, { comp = components[10].base } },
              removedSegments = { { comp = { objects = oldObjects or {} } } },
            }
            handlers.handleEvent(nil, simulation, nil, 'apply_command', 'onPostBuildProposal',
              { { proposal = street }, {}, {}, playerInitiated ~= false })
          end
        """)
        self.lua.execute((ROOT / "content/auto_signal/events.script.lua").read_text())
        self.lua.execute("handlers = data(); handlers.update(nil, simulation); handlers.guiUpdate(nil, simulation, gui)")

    def test_player_placement_enqueues_once_and_builds_with_meters(self):
        self.lua.execute("place(100, 2, 350); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("simulation.subscribed"), "onPostBuildProposal")
        self.assertEqual(self.lua.eval("#simulation.value.jobs"), 1)
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.assertEqual(self.lua.eval("calls[1].proposal.minimum"), 350)
        self.assertEqual(self.lua.eval("calls[1].context.player"), 7)
        self.assertFalse(self.lua.eval("calls[1].player"))

    def test_manual_placement_does_not_start_automatic_job(self):
        self.lua.execute("place(100, 1, 300); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_rebuilt_signals_do_not_start_another_job(self):
        self.lua.execute("place(100, nil, nil, nil, false); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_existing_objects_in_track_edit_are_not_new_placements(self):
        self.lua.execute("place(100, 2, 300, {{100, 2}}); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_commands_wait_for_previous_completion(self):
        self.lua.execute("place(100, 2, 300); place(101, 2, 500)")
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.lua.execute("completion({}, true); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertEqual(self.lua.eval("calls[2].proposal.minimum"), 500)

    def test_failed_command_reports_error_and_releases_queue(self):
        self.lua.execute("place(100, 2, 300); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("completion({resultProposalData={errorState={messages={'collision'}}}}, false)")
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui)")
        self.assertIn("collision", self.lua.eval("warnings[1]"))
        self.lua.execute("place(101, 2, 300); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)

    def test_seed_already_removed_by_previous_rebuild_is_skipped(self):
        self.lua.execute("place(100, 2, 300); components[100] = nil; handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_loading_save_does_not_replay_old_jobs(self):
        self.lua.execute("place(100, 2, 300); gui = makeState(); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_critical_rejection_tries_a_new_position_then_stops_after_success(self):
        self.lua.execute("place(100, 2, 226); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("""
          completion({resultProposalData={errorState={critical=true, messages={'cannot build'}}}}, false)
        """)
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertNotEqual(
            self.lua.eval("calls[1].proposal.positions[1]"),
            self.lua.eval("calls[2].proposal.positions[1]"),
        )
        self.assertEqual(self.lua.eval("calls[1].proposal.minimum"), 226)
        self.assertEqual(self.lua.eval("calls[2].proposal.minimum"), 226)
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.lua.execute("completion({}, true); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertEqual(self.lua.eval("#warnings"), 0)

    def test_failed_alternatives_finish_without_repeating_positions_and_release_next_job(self):
        self.lua.execute("""
          local originalPlan = networkFake.plan
          networkFake.plan = function(entity, minimum, layout)
            local plan = originalPlan(entity, minimum, layout)
            -- A constrained allowed range can make two phases choose the same point.
            if layout.phase == 1 then
              plan.positions = {750}
            end
            return plan
          end
          place(100, 2, 226); place(101, 2, 350)
          handlers.guiUpdate(nil, simulation, gui)
        """)
        for _ in range(4):
            self.lua.execute("""
              completion({resultProposalData={errorState={critical=true, messages={'cannot build'}}}}, false)
              handlers.guiUpdate(nil, simulation, gui)
            """)
        self.assertEqual(self.lua.eval("#calls"), 5)
        positions = []
        for index in range(1, 5):
            self.assertEqual(self.lua.eval(f"calls[{index}].proposal.entity"), 100)
            self.assertEqual(self.lua.eval(f"calls[{index}].proposal.minimum"), 226)
            positions.append(self.lua.eval(f"calls[{index}].proposal.positions[1]"))
        self.assertEqual(len(set(positions)), 4)
        self.assertIn("no accepted layout after 4 attempts", self.lua.eval("warnings[1]"))
        self.assertEqual(self.lua.eval("calls[5].proposal.entity"), 101)
        self.assertEqual(self.lua.eval("calls[5].proposal.minimum"), 350)
        self.lua.execute("completion({}, true); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 5)

    def test_changed_track_section_ends_recovery_and_allows_a_new_job(self):
        self.lua.execute("place(100, 2, 226); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("""
          local originalPlan = networkFake.plan
          networkFake.plan = function(entity, minimum, layout)
            local plan = originalPlan(entity, minimum, layout)
            plan.sourceEdges = {10, 11}
            return plan
          end
          completion({resultProposalData={errorState={critical=true, messages={'cannot build'}}}}, false)
          handlers.guiUpdate(nil, simulation, gui)
        """)
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.assertIn("track section changed", self.lua.eval("warnings[1]"))
        self.lua.execute("place(101, 2, 350); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertEqual(self.lua.eval("calls[2].proposal.entity"), 101)


if __name__ == "__main__":
    unittest.main()
