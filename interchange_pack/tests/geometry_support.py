"""Sample the actual Lua52 generator; no game engine is simulated here."""
import json
from pathlib import Path
from lupa.lua52 import LuaRuntime
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'content/interchanges'
KINDS = ('cloverleaf', 'diamond', 'trumpet', 'directional', 'turbine', 'stack')


def unpack(value):
    if hasattr(value, 'items'):
        items = dict(value.items())
        if items and all(isinstance(k, int) for k in items):
            return [unpack(items[i]) for i in range(1, len(items)+1)]
        return {k: unpack(v) for k, v in items.items()}
    return value


def runtime(language='zh_CN'):
    lua = LuaRuntime(unpack_returned_tuples=True)
    translations = json.loads((ROOT / 'strings.json').read_text(encoding='utf-8'))
    lua.globals()._ = translations[language].__getitem__
    lua.globals().CONTENT = CONTENT.as_posix()
    lua.execute('''
      local original = require
      function require(name)
        local file = name:match('^xin_interchange_pack_1::/interchanges/(.+)$')
        if file then return dofile(CONTENT .. '/' .. file) end
        return original(name)
      end
    ''')
    return lua


def generator():
    lua = runtime()
    module = lua.execute((CONTENT / 'geometry.lua').read_text(encoding='utf-8'))
    return lambda kind, **params: unpack(module.generate(kind, lua.table_from(params)))


def road_profile(**params):
    lua = runtime()
    module = lua.execute((CONTENT / 'roads.lua').read_text(encoding='utf-8'))
    return unpack(module.select(lua.table_from(params)))


def sample(segment, count=65):
    u = np.linspace(0, 1, count)[:, None]
    p, q, t, v = (np.array(segment[k]) for k in ('p0', 'p1', 't0', 't1'))
    points = (2*u**3-3*u**2+1)*p + (u**3-2*u**2+u)*t + (-2*u**3+3*u**2)*q + (u**3-u**2)*v
    deriv = (6*u*u-6*u)*p + (3*u*u-4*u+1)*t + (-6*u*u+6*u)*q + (3*u*u-2*u)*v
    second = (12*u-6)*p + (6*u-4)*t + (-12*u+6)*q + (6*u-2)*v
    speed = np.linalg.norm(deriv[:, :2], axis=1)
    grade = np.abs(deriv[:, 2])/speed
    curvature = np.abs(deriv[:, 0]*second[:, 1]-deriv[:, 1]*second[:, 0])/speed**3
    return points, grade, curvature


def cross2(a, b):
    return a[..., 0]*b[..., 1]-a[..., 1]*b[..., 0]


def crossings(network):
    """Interpolated XY intersections, including segment endpoints but excluding junctions."""
    segments = [(r, s, sample(s)[0]) for r in network['roads'] for s in r['segments']]
    found = []
    for i, (r, s, p) in enumerate(segments):
        for other, t, q in segments[i+1:]:
            # Adjacent segments of one road have a legitimate common endpoint.
            shared = [np.array(s[a]) for a in ('p0', 'p1') for b in ('p0', 'p1')
                      if np.linalg.norm(np.array(s[a])-np.array(t[b])) < 1e-6
                      and (r['id'] == other['id'] or
                           (s.get('tag'+a[-1]) and s.get('tag'+a[-1]) == t.get('tag'+b[-1])))]
            if np.any(p[:, :2].max(axis=0) < q[:, :2].min(axis=0)-1e-7) or np.any(q[:, :2].max(axis=0) < p[:, :2].min(axis=0)-1e-7):
                continue
            a, b = p[:-1, None, :2], q[None, :-1, :2]
            v, w = np.diff(p[:, :2], axis=0)[:, None], np.diff(q[:, :2], axis=0)[None, :]
            det = cross2(v, w)
            good = np.abs(det) > 1e-9
            safe = np.where(good, det, 1)
            u, z = cross2(b-a, w)/safe, cross2(b-a, v)/safe
            hits = np.argwhere(good & (u >= -1e-7) & (u <= 1+1e-7) & (z >= -1e-7) & (z <= 1+1e-7))
            for j, k in hits:
                point = p[j]+u[j,k]*(p[j+1]-p[j])
                target = q[k]+z[j,k]*(q[k+1]-q[k])
                if any(np.linalg.norm(point[:2]-x[:2]) < 0.1 for x in shared):
                    continue
                found.append((r['id'], other['id'], abs(point[2]-target[2]), point, s, t))
    return found


if __name__ == '__main__':
    make = generator()
    for kind in KINDS:
        net = make(kind)
        conflicts = crossings(net)
        bad = [(a, b, round(gap, 2), p[:2].round(2).tolist()) for a,b,gap,p,_,_ in conflicts if gap < 7.5]
        grades = [sample(s)[1].max() for r in net['roads'] for s in r['segments']]
        print(kind, 'width', 2*net['l'], 'grade', round(max(grades),3), 'conflicts', bad[:25])
