import unittest
from geometry_support import CONTENT, runtime


class ReplayCheckTests(unittest.TestCase):
    def test_read_only_native_replay_is_bounded_and_controls_are_checked(self):
        lua = runtime()
        lua.execute(r'''
          messages, checks = {}, 0
          log = { message = function(s) messages[#messages+1]=s end }
          local function copy(value)
            if type(value) ~= "table" then return value end
            local result = {}
            for k,v in pairs(value) do result[k]=copy(v) end
            return result
          end
          local function proposal()
            local p = {toAdd={},toRemove={},terrain={},proposal={addedNodes={},addedSegments={},
              removedNodes={},removedSegments={},edgeObjectsToAdd={},nodeConfigsToAdd={},nodeConfigsToRemove={}}}
            p.clone = function(self) return copy(self) end
            return p
          end
          local function simple()
            return {isSimple=true,constructionsToAdd={},streetProposal={
              nodesToAdd={},edgesToAdd={},nodeConfigsToAdd={}}}
          end
          api = {
            cmd = {sendCommand=function() error("diagnostics must never build") end},
            type = {SimpleProposal={new=simple,ConstructionEntity={new=function() return {} end}},
                    Context={new=function() return {} end}},
            engine = {util={getPlayer=function() return 42 end,proposal={
              makeProposalData=function(p,context)
                checks=checks+1
                assert(context.player==42)
                assert(p.isSimple,"native runtime expects SimpleProposal")
                local street
                if #p.constructionsToAdd > 0 then
                  assert(p.constructionsToAdd[1].params.size==1)
                  assert(p.constructionsToAdd[1].playerEntity==42)
                  street=original.proposal
                else
                  street={addedSegments=p.streetProposal.edgesToAdd,addedNodes=p.streetProposal.nodesToAdd,
                          nodeConfigsToAdd=p.streetProposal.nodeConfigsToAdd}
                end
                assert(#street.nodeConfigsToAdd == #street.addedNodes or #street.nodeConfigsToAdd==0)
                local kept={}
                for _,edge in ipairs(street.addedSegments) do kept[edge.entity]=true end
                for _,config in ipairs(street.nodeConfigsToAdd) do
                  for _,c in ipairs(config.comp.laneConnections) do
                    assert(kept[c.segment0] and kept[c.segment1])
                  end
                end
                for _,edge in ipairs(street.addedSegments) do
                  if edge.entity==-2 then return {p,{errorState={critical=true,messages={"bad segment"}}}} end
                end
                return {p,{errorState={critical=false,messages={}}}}
              end,
            }}},
          }
          original=proposal()
          original.toAdd={{fileName="test",construction={params={size=1}},transf={},playerEntity=42}}
          for i=1,4 do
            original.proposal.addedNodes[i]={entity=-i,comp={position={x=i,y=0,z=0}}}
            original.proposal.nodeConfigsToAdd[i]={entity=-i,comp={userModifiedLaneConnections=false,laneConnections={}}}
          end
          original.proposal.nodeConfigsToAdd[2].comp.laneConnections={{segment0=-1,lane0=0,segment1=-2,lane1=0}}
          for i=1,3 do
            original.proposal.addedSegments[i]={entity=-i,comp={node0=-i,node1=-i-1,type=0,
              roadTemplate="test",position0={x=i,y=0,z=0},position1={x=i+1,y=0,z=0},
              tangent0={x=1,y=0,z=0},tangent1={x=1,y=0,z=0}}}
          end
        ''')
        lua.globals().replay = lua.execute((CONTENT/'replay_check.lua').read_text(encoding='utf-8'))
        lua.execute(r'''
          replay.enqueue("bad",original,{errorState={critical=true,messages={"bad segment"}}})
          for i=1,20 do
            local before=checks
            replay.step()
            assert(checks-before<=1)
          end
          local joined=table.concat(messages,"\n")
          assert(joined:find("case=empty-positive-control; result=false:",1,true))
          assert(joined:find("case=single-2; result=true:bad segment",1,true))
          assert(joined:find("case=first-failing-prefix-2; result=true:bad segment",1,true))
          assert(joined:find("DONE bad",1,true))
          assert(#original.toAdd==1 and #original.proposal.addedSegments==3)
          assert(#original.proposal.addedNodes==4)
          assert(original.proposal.addedSegments[2].comp.node0==-2)
          assert(#original.proposal.nodeConfigsToAdd[2].comp.laneConnections==1)
          local before=checks
          replay.enqueue("mismatch",original,{errorState={critical=false,messages={}}})
          for i=1,5 do replay.step() end
          assert(checks==before+1)
          assert(table.concat(messages,"\n"):find("REPLAY MISMATCH",1,true))

          -- A failed native candidate must not abort the other comparisons.
          local previous=api.engine.util.proposal.makeProposalData
          matrixCases={}
          api.engine.util.proposal.makeProposalData=function(p,context)
            local con=p.constructionsToAdd[1]
            if con and con.params._ipProbe~=nil then
              local q=con.params
              local key=con.fileName..":"..q.roadType..":"..q.lanes..":"..q._ipProbe
              assert(not matrixCases[key]); matrixCases[key]=true
              assert(q.size==1 and q.cloverLayout==1 and q.leafEnabled1==2)
              if q._ipProbe==2 then error("native candidate rejected") end
            end
            return previous(p,context)
          end
          original.toAdd[1].fileName="xin_interchange_pack_1::/interchanges/diamond.con"
          replay.enqueue("matrix-anchor",original,{errorState={critical=true,messages={"bad segment"}}})
          for i=1,400 do
            local before=checks
            replay.step()
            assert(checks-before<=1)
          end
          local count=0; for _ in pairs(matrixCases) do count=count+1 end
          assert(count==144,count)
          assert(original.toAdd[1].construction.params._ipProbe==nil)
          assert(original.toAdd[1].construction.params.roadType==nil)
          assert(table.concat(messages,"\n"):find("DONE MATRIX",1,true))
        ''')
