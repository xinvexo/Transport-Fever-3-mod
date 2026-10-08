from itertools import product
import math
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
rt = LuaRuntime(unpack_returned_tuples=True)
geom = rt.execute((ROOT / 'content/rail_loop/dynamic_geometry.lua').read_text(encoding='utf-8'))

def table(x):
    if isinstance(x,dict):return rt.table_from({k:table(v) for k,v in x.items()})
    if isinstance(x,(list,tuple)):return rt.table_from([table(v) for v in x])
    return x
def sample(s):
    p0,p1,t0,t1=[np.array(list(s[k].values())) for k in ['p0','p1','t0','t1']]
    u=np.linspace(0,1,25)[:,None]
    p=(2*u**3-3*u*u+1)*p0+(u**3-2*u*u+u)*t0+(-2*u**3+3*u*u)*p1+(u**3-u*u)*t1
    t=(6*u*u-6*u)*p0+(3*u*u-4*u+1)*t0+(-6*u*u+6*u)*p1+(3*u*u-2*u)*t1
    dd=(12*u-6)*p0+(6*u-4)*t0+(-12*u+6)*p1+(6*u-2)*t1
    v=np.linalg.norm(t[:,:2],axis=1)
    radius=v**3/np.maximum(abs(t[:,0]*dd[:,1]-t[:,1]*dd[:,0]),1e-14)
    grade=abs(t[:,2])/v
    return p,t,radius,grade



def verify_geometry():
    cases=[];worst_r=1e9;worst_g=0
    # Skewed/offset tracks and relative loop elevations.
    for spacing,offset,angle,length,height,direction in product([5,12,40],[0,25],[-12,0,12],[0,100],[-16,0,8],[1,2]):
        a={'p':[100,200,10],'t':[0,1,0]}
        b={'p':[100+spacing,200+offset,10],'t':[math.sin(math.radians(angle)),math.cos(math.radians(angle)),0]}
        segs,info=geom.generate(table(a),table(b),table({'extension':length,'elevation':height,'direction':direction}))
        assert np.allclose(list(segs[1].p0.values()),a['p'],atol=1e-6)
        assert np.allclose(list(segs[len(segs)].p1.values()),b['p'],atol=1e-6)
        prev=None
        for s in segs.values():
            p,t,r,g=sample(s)
            assert np.isfinite(p).all() and np.isfinite(t).all()
            worst_r=min(worst_r,float(r.min()));worst_g=max(worst_g,float(g.max()))
            assert r.min()>=54.99, (spacing,offset,angle,length,height,direction,r.min())
            assert g.max()<=.04005
            if prev:
                assert np.linalg.norm(prev[0]-p[0])<1e-6
                assert np.linalg.norm(prev[1]/np.linalg.norm(prev[1])-t[0]/np.linalg.norm(t[0]))<1e-6
            prev=(p[-1],t[-1])
        cases.append((spacing,offset,angle,length,height,direction))

    # Existing graded tracks, and length response at every bridge/tunnel height.
    for height in [-32,-24,-16,0,8,12,16,24]:
        previous=None
        for length in [0,100,800]:
            a={'p':[0,0,15],'t':[0,1,.02]}
            b={'p':[5,0,17],'t':[0,-1,-.02]}
            segs,info=geom.generate(table(a),table(b),table({'extension':length,'elevation':height,'direction':1}))
            assert np.allclose(list(segs[1].p0.values()),a['p'],atol=1e-6)
            assert np.allclose(list(segs[len(segs)].p1.values()),b['p'],atol=1e-6)
            if previous is not None: assert info.extension>previous
            previous=info.extension
            for s in segs.values():
                p,t,r,g=sample(s)
                assert r.min()>=54.99 and g.max()<=.04005
            cases.append(('grade',height,length))

    return len(cases)


class GeometryTests(unittest.TestCase):
    def test_endpoints_continuity_radius_and_grade_for_240_cases(self):
        self.assertEqual(verify_geometry(), 240)
