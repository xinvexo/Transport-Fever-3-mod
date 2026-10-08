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
              plan = function(entity, gap)
                return { entity = entity, spacing = gap, count = 1, positions = {999.5} }
              end,
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
        self.lua.execute((ROOT / "content/auto_signal/events.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("handlers = data(); handlers.update(nil, simulation); handlers.guiUpdate(nil, simulation, gui)")

    def test_player_placement_enqueues_once_and_builds_with_meters(self):
        self.lua.execute("place(100, 2, 350); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("simulation.subscribed"), "onPostBuildProposal")
        self.assertEqual(self.lua.eval("#simulation.value.jobs"), 1)
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.assertEqual(self.lua.eval("calls[1].proposal.spacing"), 350)
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
        self.assertEqual(self.lua.eval("calls[2].proposal.spacing"), 500)

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

    def test_critical_rejection_does_not_retry_or_block_next_job(self):
        self.lua.execute("place(100, 2, 226); place(101, 2, 350); handlers.guiUpdate(nil, simulation, gui)")
        self.lua.execute("""
            completion({resultProposalData={errorState={critical=true, messages={'cannot build'}}}}, false)
            handlers.guiUpdate(nil, simulation, gui)
        """)
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertEqual(self.lua.eval("calls[1].proposal.entity"), 100)
        self.assertEqual(self.lua.eval("calls[2].proposal.entity"), 101)
        self.assertIn("cannot build", self.lua.eval("warnings[1]"))
        self.lua.execute("completion({}, true); handlers.guiUpdate(nil, simulation, gui)")
        self.assertEqual(self.lua.eval("#calls"), 2)

    def test_planning_rejection_never_submits_a_partial_build(self):
        self.lua.execute("""
            local original = networkFake.plan
            networkFake.plan = function(entity, gap)
                if entity == 100 then return nil, 'fixed point unavailable' end
                return original(entity, gap)
            end
            place(100, 2, 300); place(101, 2, 300)
            handlers.guiUpdate(nil, simulation, gui)
        """)
        self.assertEqual(self.lua.eval("#calls"), 1)
        self.assertEqual(self.lua.eval("calls[1].proposal.entity"), 101)
        self.assertIn("fixed point unavailable", self.lua.eval("warnings[1]"))

    def test_missing_geometry_reports_error_without_removing_seed(self):
        self.lua.execute("""
            networkFake.plan = function() error('track geometry unavailable') end
            place(100, 2, 300); handlers.guiUpdate(nil, simulation, gui)
        """)
        self.assertEqual(self.lua.eval("#calls"), 0)
        self.assertTrue(self.lua.eval("components[100] ~= nil"))
        self.assertIn("geometry unavailable", self.lua.eval("warnings[1]"))

    def test_typed_spacing_outside_slider_range_is_accepted(self):
        for gap in (1, 25, 320, 1200, 5000):
            with self.subTest(gap=gap):
                self.lua.execute(f"place({100+gap}, 2, {gap}); handlers.guiUpdate(nil, simulation, gui)")
                self.assertEqual(self.lua.eval("calls[#calls].proposal.spacing"), gap)
                self.lua.execute("completion({}, true); handlers.guiUpdate(nil, simulation, gui)")

    def test_zero_fractional_and_nonfinite_spacing_does_not_enqueue(self):
        self.lua.execute("""
            place(100, 2, 0); place(101, 2, -1); place(102, 2, 1.5)
            place(103, 2, math.huge); place(104, 2, 0/0)
            handlers.guiUpdate(nil, simulation, gui)
        """)
        self.assertEqual(self.lua.eval("#calls"), 0)


if __name__ == "__main__":
    unittest.main()
