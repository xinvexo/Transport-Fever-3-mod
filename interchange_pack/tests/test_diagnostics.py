import unittest
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
