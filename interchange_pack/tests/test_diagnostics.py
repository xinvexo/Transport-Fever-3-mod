import unittest
from pathlib import Path
import tempfile
from geometry_support import CONTENT, runtime


class DiagnosticTests(unittest.TestCase):
    def test_normal_install_does_not_register_background_checks(self):
        lua = runtime()
        lua.execute((CONTENT/'diagnostics.gs.lua').read_text(encoding='utf-8'))
        self.assertEqual(list(lua.globals().data().items()),[])
        lua.execute((CONTENT/'validation.gs.lua').read_text(encoding='utf-8'))
        self.assertEqual(list(lua.globals().data().items()),[])

    def test_passive_observer_never_replays_or_clones_previews(self):
        lua = runtime()
        lua.execute('''
          messages={}
          log={message=function(s) messages[#messages+1]=s end}
          api=setmetatable({},{__index=function() error("observer must not call native APIs") end})
        ''')
        lua.execute((CONTENT/'preview_observer.script.lua').read_text(encoding='utf-8'))
        lua.execute('''
          local observer=data()
          assert(observer.guiUpdate==nil)
          local input={{toAdd={{fileName="xin_interchange_pack_1::/interchanges/cloverleaf.con",
            construction={params={size=1,seed=1}}}},clone=function() error("must not clone") end},
            {errorState={critical=false,messages={}}}}
          observer.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          input[1].toAdd[1].construction.params.seed=2
          observer.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          assert(#messages==1)
          input[2].errorState.messages={"collision"}
          observer.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          assert(#messages==2)
        ''')

    def test_checker_refresh_reads_physical_file_instead_of_cached_vfs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'replay_version.lua').write_text('return 15',encoding='utf-8')
            (root/'replay_check.lua').write_text('''
              reloadCount=reloadCount+1
              return {enqueue=function(key,p,result) assert(p.snapshot); replayCount=replayCount+1 end,
                      step=function() end}
            ''',encoding='utf-8')
            lua = runtime()
            lua.execute('''
              reloadCount,replayCount=0,0
              log={message=function() end}
              api={res={streetTemplateRep={find=function(n) return n end,get=function() return {} end}}}
              resolveutil={resolve=function() error("physical path should be used") end}
              ui={value={},get=function(self) return self.value end,set=function(self,v) self.value=v end}
            ''')
            lua.globals().SCRIPT_SOURCE = (CONTENT/'diagnostics.script.lua').read_text(encoding='utf-8')
            lua.globals().SCRIPT_NAME = '@'+(root/'diagnostics.script.lua').as_posix()
            lua.execute('''
              assert(load(SCRIPT_SOURCE,SCRIPT_NAME))()
              diagnostic=data()
              diagnostic.guiUpdate(nil,nil,ui)
              diagnostic.guiHandleEvent(nil,nil,ui,nil,nil,"builder.proposalCreate",{
                {toAdd={{fileName="xin_interchange_pack_1::/interchanges/diamond.con",construction={params={}}}},
                  proposal={addedNodes={},addedSegments={}},clone=function() return {snapshot=true} end},
                {errorState={critical=false,messages={}}}})
            ''')
            (root/'replay_version.lua').write_text('return 16',encoding='utf-8')
            lua.execute('diagnostic.guiUpdate(nil,nil,ui); assert(reloadCount==1 and replayCount==1)')

    def test_checker_reload_reuses_captured_preview_without_building(self):
        lua = runtime()
        lua.execute('''
          messages, replayed, reloads, steps = {},0,0,0
          hotVersion = 15
          log = {message=function(s) messages[#messages+1]=s end}
          api = {res={streetTemplateRep={find=function(n) return n end,get=function() return {} end}},
            cmd={sendCommand=function() error("must not build") end}}
          resolveutil = {
            resolve=function(path,base) assert(path:find("xin_interchange_pack_1::/",1,true)); return path end,
            loadfile=function(path)
              if path:find("replay_version.lua",1,true) then return function() return hotVersion end end
              assert(path:find("replay_check.lua",1,true))
              reloads=reloads+1
              return function() return {
                enqueue=function(key,proposal,result)
                  assert(proposal.snapshot and result.errorState.critical)
                  replayed=replayed+1
                end,
                step=function() steps=steps+1 end,
              } end
            end,
          }
          ui={value={},get=function(self) return self.value end,set=function(self,v) self.value=v end}
        ''')
        lua.execute((CONTENT/'diagnostics.script.lua').read_text(encoding='utf-8'))
        lua.execute('''
          diagnostic=data()
          diagnostic.guiUpdate(nil,nil,ui)
          local proposal={toAdd={{fileName="xin_interchange_pack_1::/interchanges/directional.con",
            construction={params={size=1}}}},proposal={addedNodes={},addedSegments={}},
            clone=function() return {snapshot=true} end}
          diagnostic.guiHandleEvent(nil,nil,ui,nil,nil,"builder.proposalCreate",{
            proposal,{errorState={critical=true,messages={"cannot build"}}}})
          hotVersion=16
          for i=1,60 do diagnostic.guiUpdate(nil,nil,ui) end
          assert(reloads==1 and replayed==1 and steps>0)
          for i=1,60 do diagnostic.guiUpdate(nil,nil,ui) end
          assert(reloads==1 and replayed==1)
        ''')

    def test_native_preview_logging_is_read_only_and_deduplicated(self):
        lua = runtime()
        lua.execute('''
          messages = {}
          log = { message = function(s) messages[#messages+1] = s end }
          api = {
            cmd = { sendCommand = function() error("diagnostics must not build") end },
            res = { streetTemplateRep = {
              find = function(name) return name end,
              get = function() return { maxSlopeShape = .12, minCurveRadius = 20 } end,
            } },
          }
          ui = { value = {}, get = function(self) return self.value end,
                 set = function(self,v) self.value = v end }
          sim = { subscribed = false, hasEventSubscriptions = function(self) return self.subscribed end,
            subscribeToEvent = function(self,name) assert(name == "builder.proposalCreate"); self.subscribed = true end }
        ''')
        lua.execute((CONTENT/'diagnostics.script.lua').read_text(encoding='utf-8'))
        lua.execute('''
          diagnostic = data()
          diagnostic.update(nil,sim)
          assert(sim.subscribed)
          diagnostic.guiUpdate(nil,nil,ui)
          limitCount = #messages
          assert(limitCount > 0 and table.concat(messages,";"):find("maxSlopeShape=0.12",1,true))
          diagnostic.guiUpdate(nil,nil,ui)
          assert(#messages == limitCount)
          pair = {
            { toAdd = { { fileName = "xin_interchange_pack_1::/interchanges/diamond.con",
              construction = {params={lanes=2,size=1}} } }, proposal = {
                addedNodes = {
                  {entity=-1,comp={position={x=1,y=2,z=3}}},
                  {entity=-2,comp={position={x=1,y=2,z=3}}},
                } } },
            { errorState = {critical=true,messages={"Too steep"},warnings={},infos={}},
              collisionInfo={collisionEntities={}}, entity2tn={[-9]={edges={
                {geometry={calcPos=function(self,u) return {{},{x=1,y=0,z=.3},{}} end}},
              }}} },
          }
          local response = diagnostic.guiHandleEvent(nil,nil,ui,nil,nil,"builder.proposalCreate",pair)
          assert(next(response) == nil)
          local resultMessage = messages[limitCount+1]
          assert(resultMessage:find("Too steep",1,true))
          assert(resultMessage:find("duplicateNodes=-1/-2",1,true))
          assert(resultMessage:find("laneMaxGrade=0.30000",1,true))
          assert(not resultMessage:find("laneReadError",1,true))
          assert(#messages == limitCount+2)
          assert(messages[#messages]:find("UNAVAILABLE",1,true))
          diagnostic.guiHandleEvent(nil,nil,ui,nil,nil,"builder.proposalCreate",pair)
          assert(#messages == limitCount+2)
          assert(pair[2].errorState.critical == true)
          assert(pair[2].errorState.messages[1] == "Too steep")
        ''')
