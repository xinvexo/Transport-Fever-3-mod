local builtin = require "::/gui/main/builtin.lua"
local geometry = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_geometry.lua"
local M = {}

function M.controlPoint(point,hover,invalid)
  local kind=builtin.type.ControlPointInfo
  local state=invalid and kind.State.Invalid or (hover and kind.State.Hover or kind.State.Idle)
  return kind.new(api.type.Vec3f.new(point.p[1],point.p[2],point.p[3]),0.25,2.5,state)
end

local function makeEdge(p0,p1,t0,t1,color,width)
  local shape=api.type.EdgeGeometry.new()
  shape.type=api.type.EdgeGeometry.Type.CUBIC_SPLINE
  -- Assign native nested values back explicitly; their getters may copy.
  local spline=api.type.EdgeGeometry.CubicSpline.new()
  spline.pos={api.type.Vec2f.new(p0[1],p0[2]),api.type.Vec2f.new(p1[1],p1[2])}
  spline.tangent={api.type.Vec2f.new(t0[1],t0[2]),api.type.Vec2f.new(t1[1],t1[2])}
  shape.cubicSpline=spline
  shape.height=api.type.Vec2f.new(p0[3],p1[3])
  shape.tangent=api.type.Vec2f.new(t0[3],t1[3])
  local length,previous=0,p0
  for i=1,8 do
    local p=geometry.hermite(p0,p1,t0,t1,i/8)
    length=length+math.sqrt((p[1]-previous[1])^2+(p[2]-previous[2])^2+(p[3]-previous[3])^2)
    previous=p
  end
  shape.length=length;shape.width=width
  local maxError=0
  local function check(value)
    for _,u in ipairs({0,0.5,1}) do
      local expected=geometry.hermite(p0,p1,t0,t1,u)
      local actual=value:calcPos(u)[1]
      local distance=math.sqrt((actual.x-expected[1])^2+(actual.y-expected[2])^2+(actual.z-expected[3])^2)
      assert(distance==distance and distance<0.1,"原生预览几何坐标与回环不一致")
      maxError=math.max(maxError,distance)
    end
  end
  check(shape)
  local edge=builtin.type.EdgeRenderable.Edge.new(shape)
  check(edge.geometry)
  edge.colors={color,color};edge.width=width;edge.offsetZ=0.25;edge.stepSize=0.5
  return edge,maxError
end

-- Fixed points are small rings, not selected rail entities. They join the same
-- edge batch as the loop; only the active point uses the one ProposalViewer.
function M.fixedPoint(point)
  local radius=1.25
  local tangent=4*(math.sqrt(2)-1)*radius
  local axes={{1,0},{0,1},{-1,0},{0,-1},{1,0}}
  local color=api.type.Vec4f.new(0.2,0.7,1,0.9)
  local edges={}
  for i=1,4 do
    local a,b=axes[i],axes[i+1]
    local p0={point.p[1]+radius*a[1],point.p[2]+radius*a[2],point.p[3]}
    local p1={point.p[1]+radius*b[1],point.p[2]+radius*b[2],point.p[3]}
    edges[#edges+1]=makeEdge(p0,p1,{-tangent*a[2],tangent*a[1],0},{-tangent*b[2],tangent*b[1],0},color,0.65)
  end
  return edges
end

-- Draw the planned rails even when the engine rejects the construction.
function M.make(segments,color)
  local edges,maxError={},0
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
      local edge,error=makeEdge(p0,p1,t0,t1,color,1)
      edges[#edges+1]=edge;maxError=math.max(maxError,error)
    end
  end
  return edges,{maxError=maxError,first=edges[1].geometry:calcPos(0)[1],last=edges[#edges].geometry:calcPos(1)[1]}
end

return M
