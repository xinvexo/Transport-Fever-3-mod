local builtin = require "::/gui/main/builtin.lua"
local geometry = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_geometry.lua"
local M = {}

-- Draw the planned rails directly; ProposalViewer may produce no mesh when
-- the engine rejects a junction or collision. This never submits construction.
function M.make(segments, color)
  local edges = {}
  for _,segment in ipairs(segments) do
    for _,offset in ipairs({-0.75,0.75}) do
      local function endpoint(u)
        local p,t,dd=geometry.hermite(segment.p0,segment.p1,segment.t0,segment.t1,u)
        local speed=math.sqrt(t[1]^2+t[2]^2)
        local curvature=(t[1]*dd[2]-t[2]*dd[1])/speed^3
        return {p[1]-offset*t[2]/speed,p[2]+offset*t[1]/speed,p[3]},
          {t[1]*(1-offset*curvature),t[2]*(1-offset*curvature),t[3]}
      end
      local p0,t0=endpoint(0)
      local p1,t1=endpoint(1)
      local shape=api.type.EdgeGeometry.new()
      shape.type=api.type.EdgeGeometry.Type.CUBIC_SPLINE
      shape.cubicSpline.pos={api.type.Vec2f.new(p0[1],p0[2]),api.type.Vec2f.new(p1[1],p1[2])}
      shape.cubicSpline.tangent={api.type.Vec2f.new(t0[1],t0[2]),api.type.Vec2f.new(t1[1],t1[2])}
      shape.height=api.type.Vec2f.new(p0[3],p1[3])
      shape.tangent=api.type.Vec2f.new(t0[3],t1[3])
      local length,previous=0,p0
      for i=1,8 do
        local p=geometry.hermite(p0,p1,t0,t1,i/8)
        length=length+math.sqrt((p[1]-previous[1])^2+(p[2]-previous[2])^2+(p[3]-previous[3])^2)
        previous=p
      end
      shape.length=length;shape.width=0.3
      local edge=builtin.type.EdgeRenderable.Edge.new(shape)
      edge.colors={color,color};edge.width=0.3;edge.offsetZ=0.15;edge.stepSize=1
      edges[#edges+1]=edge
    end
  end
  return edges
end

return M
