import unittest
from geometry_support import CONTENT,runtime


class AcceptanceTests(unittest.TestCase):
    def make_runtime(self,mismatch=False):
        lua=runtime()
        lua.globals().mismatch=mismatch
        lua.execute(r'''
          calls,messages,cases=0,{},{}
          log={message=function(s) messages[#messages+1]=s end}
          api={cmd={sendCommand=function() error("must not build") end},type={
            Context={new=function() return {} end},SimpleProposal={
              new=function() return {} end,ConstructionEntity={new=function() return {} end}}},
            engine={util={getPlayer=function() return 42 end,proposal={makeProposalData=function(p,context)
              calls=calls+1
              assert(context.player==42)
              local entity=p.constructionsToAdd[1]
              assert(entity.playerEntity==42 and entity.transf.token==123)
              if calls>1 then
                local q=entity.params
                assert(q.size==1 and q.roadType==1 and q.bridge==1 and q._ipProbe==nil)
                assert(q.leafEnabled1==2 and q.rampEnabled4==2)
                local key=entity.fileName..":"..q.lanes..":"..q._ipAcceptVariant
                assert(not cases[key]);cases[key]=true
              end
              local bad=mismatch or (entity.fileName:find("turbine.con",1,true) and entity.params.lanes==2)
              return {p,{errorState={critical=false,messages=bad and {"collision"} or {}}}}
            end}}}}
          input={{toAdd={{fileName="xin_interchange_pack_1::/interchanges/cloverleaf.con",
            transf={token=123},playerEntity=42,construction={params={lanes=1,year=1945}}}},
            proposal={addedNodes={{comp={position={x=0,y=0,z=0}}}},addedSegments={}}},
            {errorState={critical=false,messages={}}}}
        ''')
        lua.execute((CONTENT/'validate_twelve.script.lua').read_text(encoding='utf-8'))
        lua.execute('validator=data()')
        return lua

    def test_acceptance_pauses_during_drag_and_stops_after_twelve_cases(self):
        lua=self.make_runtime()
        lua.execute(r'''
          for i=1,60 do
            input[1].proposal.addedNodes[1].comp.position.x=i
            validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
            validator.guiUpdate()
          end
          assert(calls==0)
          for i=1,119 do validator.guiUpdate() end
          assert(calls==1)
          for i=61,70 do
            input[1].proposal.addedNodes[1].comp.position.x=i
            validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
            validator.guiUpdate()
          end
        ''')
        lua.execute(r'''
          assert(calls==1)
          input[1].toAdd[1].fileName="::/another/construction.con"
          validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          for i=1,200 do validator.guiUpdate() end
          assert(calls==1)
          local saved=input[1].toAdd
          input[1].toAdd={}
          validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          for i=1,200 do validator.guiUpdate() end
          assert(calls==1)
          input[1].toAdd=saved
          input[1].toAdd[1].fileName="xin_interchange_pack_1::/interchanges/cloverleaf.con"
          validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          for i=1,1000 do validator.guiUpdate() end
          assert(calls==16)
          local count=0;for _ in pairs(cases) do count=count+1 end
          assert(count==15)
          assert(input[1].toAdd[1].construction.params.size==nil)
          assert(table.concat(messages,"\n"):find("DONE; resolved=11/12; defaults=11/12; stopped=true",1,true))
          validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          for i=1,1000 do validator.guiUpdate() end
          assert(calls==16)
        ''')

    def test_mismatched_control_does_not_claim_acceptance(self):
        lua=self.make_runtime(mismatch=True)
        lua.execute(r'''
          validator.guiHandleEvent(nil,nil,nil,nil,nil,"builder.proposalCreate",input)
          for i=1,1000 do validator.guiUpdate() end
          assert(calls==1)
          assert(table.concat(messages,"\n"):find("CONTROL MISMATCH",1,true))
        ''')
