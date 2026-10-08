-- Pure geometry. Selected endpoints never move when extension/height changes.
local M = {}
local pi, sin, cos, sqrt = math.pi, math.sin, math.cos, math.sqrt
-- The game embeds Lua 5.2: atan ignores a second argument there.
-- atan2 preserves the quadrant; Lua 5.3+ moved that behavior into atan.
local atan2 = math.atan2 or math.atan
local function mod(x) return x % (2 * pi) end
local function norm(t)
  local n = sqrt(t[1]^2 + t[2]^2)
  assert(n > 1e-6, "轨道方向无效")
  return {t[1]/n, t[2]/n, (t[3] or 0)/n}
end
local function smooth(t) return t^3*(10-15*t+6*t*t) end
local function dsmooth(t) return 30*t*t*(1-t)^2 end
local function bump(s, total)
  local q = total * 0.30
  if s < q then return smooth(s/q), dsmooth(s/q)/q end
  if s > total-q then return smooth((total-s)/q), -dsmooth((total-s)/q)/q end
  return 1, 0
end

-- All six forward-only bounded-curvature paths. Validate each solution's
-- endpoint before comparing lengths, including near-degenerate cases.
local function dubins(a, b, ta, tb, r)
  local dx,dy = b[1]-a[1],b[2]-a[2]
  local d = sqrt(dx*dx+dy*dy)/r
  local theta = atan2(dy,dx)
  local alpha,beta = mod(atan2(ta[2],ta[1])-theta),mod(atan2(tb[2],tb[1])-theta)
  local sa,sb,ca,cb = sin(alpha),sin(beta),cos(alpha),cos(beta)
  local cab = cos(alpha-beta)
  local candidates = {}
  local function add(k,t,p,q) candidates[#candidates+1]={k=k,v={mod(t),p,mod(q)}} end
  local p2 = 2+d*d-2*cab+2*d*(sa-sb)
  if p2 >= 0 then
    local tmp=atan2(cb-ca,d+sa-sb)
    add("LSL",tmp-alpha,sqrt(p2),beta-tmp)
  end
  p2=2+d*d-2*cab+2*d*(sb-sa)
  if p2 >= 0 then
    local tmp=atan2(ca-cb,d-sa+sb)
    add("RSR",alpha-tmp,sqrt(p2),tmp-beta)
  end
  p2=-2+d*d+2*cab+2*d*(sa+sb)
  if p2 >= 0 then
    local p=sqrt(p2)
    local tmp=atan2(-ca-cb,d+sa+sb)-atan2(-2,p)
    add("LSR",tmp-alpha,p,tmp-beta)
  end
  p2=d*d-2+2*cab-2*d*(sa+sb)
  if p2 >= 0 then
    local p=sqrt(p2)
    local tmp=atan2(ca+cb,d-sa-sb)-atan2(2,p)
    add("RSL",alpha-tmp,p,beta-tmp)
  end
  local v=(6-d*d+2*cab+2*d*(sa-sb))/8
  if math.abs(v) <= 1 then
    local p=mod(2*pi-math.acos(v))
    local t=mod(alpha-atan2(ca-cb,d-sa+sb)+p/2)
    add("RLR",t,p,alpha-beta-t+p)
  end
  v=(6-d*d+2*cab+2*d*(sb-sa))/8
  if math.abs(v) <= 1 then
    local p=mod(2*pi-math.acos(v))
    local t=mod(-alpha-atan2(ca-cb,d+sa-sb)+p/2)
    add("LRL",t,p,beta-alpha-t+p)
  end
  local valid = {}
  for _,c in ipairs(candidates) do
    local x,y,h,s=a[1],a[2],atan2(ta[2],ta[1]),0
    local pieces={}
    for i=1,3 do
      local k=c.k:sub(i,i)
      local turn=k=="L" and 1 or (k=="R" and -1 or 0)
      local length=c.v[i]*r
      if length > 1e-6 then
        pieces[#pieces+1]={x=x,y=y,h=h,turn=turn,first=s,length=length,r=r}
        if turn==0 then x,y=x+length*cos(h),y+length*sin(h)
        else
          local hn=h+turn*length/r
          x,y=x+r/turn*(sin(hn)-sin(h)),y+r/turn*(cos(h)-cos(hn))
          h=hn
        end
        s=s+length
      end
    end
    if (x-b[1])^2+(y-b[2])^2 < 1e-6 and cos(h)*tb[1]+sin(h)*tb[2]>0.999999 then
      valid[#valid+1]={pieces=pieces,length=s}
    end
  end
  assert(#valid>0, "这两个方向无法生成回环，请切换方向或重新选点")
  table.sort(valid,function(x,y) return x.length<y.length end)
  return valid
end

function M.hermite(p0,p1,t0,t1,u)
  local p,t,dd={},{},{}
  for k=1,3 do
    p[k]=(2*u^3-3*u*u+1)*p0[k]+(u^3-2*u*u+u)*t0[k]+(-2*u^3+3*u*u)*p1[k]+(u^3-u*u)*t1[k]
    t[k]=(6*u*u-6*u)*p0[k]+(3*u*u-4*u+1)*t0[k]+(-6*u*u+6*u)*p1[k]+(3*u*u-2*u)*t1[k]
    dd[k]=(12*u-6)*p0[k]+(6*u-4)*t0[k]+(-12*u+6)*p1[k]+(6*u-2)*t1[k]
  end
  return p,t,dd
end

local function attempt(a,b,ta,tb,r,extension,elevation,path,bend)
  local total=path.length
  local forward=norm({ta[1]-tb[1],ta[2]-tb[2],0})
  local shift={forward[1]*extension-forward[2]*bend*60,forward[2]*extension+forward[1]*bend*60}
  local function point(s)
    local piece=path.pieces[#path.pieces]
    for _,v in ipairs(path.pieces) do if s <= v.first+v.length+1e-7 then piece=v; break end end
    local ds=math.max(0,math.min(piece.length,s-piece.first))
    local h=piece.h+piece.turn*ds/r
    local x,y=piece.x,piece.y
    if piece.turn==0 then x,y=x+ds*cos(h),y+ds*sin(h)
    else x,y=x+r/piece.turn*(sin(h)-sin(piece.h)),y+r/piece.turn*(cos(piece.h)-cos(h)) end
    local f,df=bump(s,total)
    local u=s/total
    local zp,zt=M.hermite({0,0,a[3]},{0,0,b[3]},{0,0,ta[3]*total},{0,0,tb[3]*total},u)
    return {x+shift[1]*f,y+shift[2]*f,zp[3]+elevation*f},
      {cos(h)+shift[1]*df,sin(h)+shift[2]*df,zt[3]/total+elevation*df},f
  end
  local breaks={0,total*.3,total*.7,total}
  for _,p in ipairs(path.pieces) do breaks[#breaks+1]=p.first+p.length end
  if elevation~=0 then
    local target=math.min(1,(elevation>0 and 5 or 10)/math.abs(elevation))
    local lo,hi=0,1
    for _=1,40 do local m=(lo+hi)/2; if smooth(m)<target then lo=m else hi=m end end
    local s=total*.3*(lo+hi)/2
    breaks[#breaks+1]=s;breaks[#breaks+1]=total-s
  end
  table.sort(breaks)
  local segments={}
  for i=1,#breaks-1 do
    local lo,hi=breaks[i],breaks[i+1]
    local f0=bump(lo,total);local f1=bump(hi,total)
    local count=math.max(1,math.ceil(((hi-lo)+(extension+math.abs(bend)*60)*math.abs(f1-f0))/12))
    if hi-lo>1e-6 then
      for j=0,count-1 do
        local s0,s1=lo+(hi-lo)*j/count,lo+(hi-lo)*(j+1)/count
        local p0,t0=point(s0); local p1,t1=point(s1)
        local _,_,f=point((s0+s1)/2)
        local kind="NORMAL"
        if elevation>0 and elevation*f>5 then kind="BRIDGE" end
        if elevation<0 and elevation*f< -10 then kind="TUNNEL" end
        for k=1,3 do t0[k]=t0[k]*(s1-s0); t1[k]=t1[k]*(s1-s0) end
        segments[#segments+1]={p0=p0,p1=p1,t0=t0,t1=t1,kind=kind}
      end
    end
  end
  return segments
end

local function measure(segments)
  local radius,grade,length=math.huge,0,0
  local prev,points=nil,{}
  for _,s in ipairs(segments) do
    for i=0,8 do
      local p,t,dd=M.hermite(s.p0,s.p1,s.t0,s.t1,i/8)
      local speed=sqrt(t[1]^2+t[2]^2)
      if speed<1e-7 then return nil end
      local cross=math.abs(t[1]*dd[2]-t[2]*dd[1])
      if cross>1e-8 then radius=math.min(radius,speed^3/cross) end
      grade=math.max(grade,math.abs(t[3])/speed)
      if prev then length=length+sqrt((p[1]-prev[1])^2+(p[2]-prev[2])^2+(p[3]-prev[3])^2) end
      prev=p
      if i==4 or i==8 then points[#points+1]=p end
    end
  end
  -- Reject planar self-crossings instead of silently creating a crossover.
  local function orient(a,b,c) return (b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1]) end
  for i=1,#points-1 do for j=i+2,#points-1 do
    local a,b,c,d=points[i],points[i+1],points[j],points[j+1]
    if orient(a,b,c)*orient(a,b,d)< -1e-6 and orient(c,d,a)*orient(c,d,b)< -1e-6 then return nil end
  end end
  return {minRadius=radius,maxGrade=grade,length=length}
end

function M.generate(a,b,options)
  local ta,tb=norm(a.t),norm(b.t)
  if ta[1]*tb[1]+ta[2]*tb[2]<0 then for k=1,3 do tb[k]=-tb[k] end end
  local sign=options.direction==2 and -1 or 1
  for k=1,3 do ta[k]=ta[k]*sign;tb[k]=-tb[k]*sign end
  local elevation=options.elevation or 0
  -- Native height ranges to +/-5000 m. Bound computation before allocation.
  assert(math.abs(elevation)<=64,"回环高度过大，请将原高度调回 −64 至 64 米以内")
  local extension=(options.extension or 0)+math.abs(elevation)/.03*1.25
  local radius=60
  for _=1,16 do
    for _,path in ipairs(dubins(a.p,b.p,ta,tb,radius)) do
      local segments=attempt(a.p,b.p,ta,tb,radius,extension,elevation,path,options.bend or 0)
      local info=measure(segments)
      if info and info.minRadius>=55 and info.maxGrade<=.04001 then
        info.extension=extension;info.radius=radius
        return segments,info
      end
    end
    radius=radius*1.18
  end
  error("当前位置无法保持圆润或坡度过大，请调整长度、方向或选点")
end

return M
