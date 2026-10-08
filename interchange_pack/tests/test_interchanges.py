import itertools
import os
from pathlib import Path
import struct
import unittest
from zipfile import ZipFile

import numpy as np
from lupa.lua52 import LuaRuntime

from geometry_support import CONTENT, KINDS, crossings, generator, runtime, sample, unpack, road_profile


def node(point, tag=None):
    return tag or tuple(round(v, 6) for v in point)


def geometry_cases():
    for kind,lanes in itertools.product(KINDS,(1,2)):
        yield kind,dict(size=1,roadType=1,lanes=lanes)


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.make = staticmethod(generator())

    def test_all_twelve_highway_configurations(self):
        for kind, params in geometry_cases():
            with self.subTest(kind=kind, **params):
                net = self.make(kind, **params)
                profile = road_profile(**params)
                # Native small T/trumpet comparisons accept these source grades;
                # the engine validates its shaped lanes separately (limit 0.4).
                source_grade_limit = .25 if kind in ('trumpet','directional') else .20
                main_ports = {s['tag'+end]:s['p'+end] for r in net['roads'] if r['role']=='main'
                              for s in r['segments'] for end in ('0','1') if s.get('tag'+end)}
                main_tangents = {s['tag'+end]:s['t'+end] for r in net['roads'] if r['role']=='main'
                                 for s in r['segments'] for end in ('0','1') if s.get('tag'+end)}
                branch_ports = {s['tag'+end] for r in net['roads'] if r.get('profile')=='branch'
                                for s in r['segments'] for end in ('0','1') if s.get('tag'+end)}
                occurrences, tagged = {}, {}
                for road in net['roads']:
                    for index, s in enumerate(road['segments']):
                        points, grade, curvature = sample(s)
                        self.assertTrue(np.isfinite(points).all())
                        self.assertLessEqual(grade.max(), source_grade_limit)
                        width = profile.get(road.get('profile',road['role'])+'Width',profile['rampWidth'])
                        self.assertLessEqual((grade/(1-width/2*curvature)).max(),source_grade_limit)
                        if s['bridge']:
                            self.assertGreaterEqual(min(s['p0'][2],s['p1'][2]),4)
                        self.assertLessEqual(curvature.max(), 1/15)
                        for end in ('0', '1'):
                            point, tag = s['p'+end], s.get('tag'+end)
                            key = node(point, tag)
                            occurrences[key] = occurrences.get(key, 0)+1
                            if tag:
                                if tag in main_ports and road['role'] != 'main' and kind != 'diamond':
                                    delta = np.array(point)-main_ports[tag]
                                    tangent = np.array(main_tangents[tag])
                                    amount = 4 if tag in branch_ports else 6 if params['lanes']==2 else 4
                                    self.assertAlmostEqual(np.linalg.norm(delta[:2]),amount)
                                    self.assertEqual(delta[2],0)
                                    self.assertAlmostEqual(np.dot(delta,tangent),0)
                                    signed = delta[0]*tangent[1]-delta[1]*tangent[0]
                                    self.assertGreater(signed*(-1 if road['role']=='left' else 1),0)
                                elif not tag.startswith('shared-') and not (kind=='diamond' and params['roadType']==1 and tag in main_ports):
                                    if tag in tagged:
                                        np.testing.assert_allclose(point, tagged[tag], atol=1e-8)
                                    tagged[tag] = point
                            if tag and 'external' in tag:
                                self.assertEqual(point[2], 8 if tag.startswith('cross:') else 0)
                                self.assertEqual(s['t'+end][2], 0)
                        if index:
                            previous = road['segments'][index-1]
                            np.testing.assert_allclose(previous['p1'], s['p0'], atol=1e-8)
                            a, b = np.array(previous['t1']), np.array(s['t0'])
                            np.testing.assert_allclose(a/np.linalg.norm(a), b/np.linalg.norm(b), atol=.002)
                for key, count in occurrences.items():
                    if not (isinstance(key, str) and 'external' in key):
                        self.assertGreaterEqual(count, 2, (kind, key))
                for a, b, clearance, point, s, t in crossings(net):
                    self.assertGreaterEqual(clearance, 7.5, (a,b,clearance,point))
                    top = s if sample(s)[0][:,2].max() > sample(t)[0][:,2].max() else t
                    self.assertTrue(top['bridge'], (a,b,'crossing needs a bridge'))

    def test_external_right_hand_traffic_and_reachable_destinations(self):
        for kind, road_type, side in itertools.product(KINDS, (1,2), (1,2)):
            net = self.make(kind, roadType=road_type, loopSide=side)
            graph, inputs, outputs = {}, [], []
            for road in net['roads']:
                for s in road['segments']:
                    a, b = node(s['p0'],s.get('tag0')), node(s['p1'],s.get('tag1'))
                    graph.setdefault(a,set()).add(b)
                    if road['role'] in ('cross','shared'):
                        graph.setdefault(b,set()).add(a)
                    for suffix, key in (('0',a), ('1',b)):
                        if isinstance(key,str) and 'external' in key:
                            p, t = np.array(s['p'+suffix]), np.array(s['t'+suffix])
                            if road['role'] == 'cross':
                                inputs.append(key); outputs.append(key)
                            else:
                                # The traffic's right-hand normal points toward its side of the median.
                                self.assertGreater(p[0]*t[1]-p[1]*t[0], 0)
                                (inputs if np.dot(p[:2],t[:2]) < 0 else outputs).append(key)
            expected = 3 if kind in ('trumpet','directional') else 4
            self.assertEqual(len(inputs),expected)
            self.assertEqual(len(outputs),expected)
            for source in inputs:
                seen, todo = {source}, [source]
                while todo:
                    for target in graph.get(todo.pop(), ()):
                        if target not in seen:
                            seen.add(target); todo.append(target)
                self.assertGreaterEqual(len(set(outputs)&seen),expected-1,(kind,road_type,side,source))

    def test_three_leg_forks_use_distinct_lane_ports(self):
        for kind,lanes,side in itertools.product(('directional','trumpet'),(1,2),(1,2)):
            net = self.make(kind,lanes=lanes,loopSide=side)
            forks = {}
            for road in net['roads']:
                if road['role'] == 'main':
                    continue
                for s in road['segments']:
                    for end in ('0','1'):
                        tag = s.get('tag'+end)
                        if tag in ('S:in','N:out'):
                            forks.setdefault(tag,[]).append(s['p'+end])
            for tag,points in forks.items():
                self.assertEqual(len(points),2,(kind,tag))
                self.assertGreaterEqual(np.linalg.norm(np.array(points[0])-points[1]),8)

    def test_three_lane_trumpet_landing_has_parallel_tangents_without_a_hook(self):
        net=self.make('trumpet',lanes=2)
        stem=next(r for r in net['roads'] if r['id']=='trumpet-stem')['segments'][-1]
        np.testing.assert_allclose(np.array(stem['t0'])/np.linalg.norm(stem['t0']),[0,-1,0],atol=1e-8)
        np.testing.assert_allclose(np.array(stem['t1'])/np.linalg.norm(stem['t1']),[0,-1,0],atol=1e-8)
        points,_,curvature=sample(stem,257)
        self.assertGreaterEqual(points[:,0].min(),min(stem['p0'][0],stem['p1'][0])-1e-8)
        self.assertLessEqual(points[:,0].max(),max(stem['p0'][0],stem['p1'][0])+1e-8)
        self.assertLess(curvature.max(),1/100)

    def test_highway_diamond_forks_keep_main_inner_edge_aligned(self):
        for size,lanes in itertools.product((1,2,3),(1,2)):
            net = self.make('diamond',size=size,lanes=lanes)
            profile = road_profile(lanes=lanes)
            forks = {}
            for road in net['roads']:
                for s in road['segments']:
                    for end in ('0','1'):
                        tag = s.get('tag'+end)
                        if tag in ('W:in','W:out','E:in','E:out'):
                            forks.setdefault(tag,[]).append((road,s['p'+end]))
            for tag,ports in forks.items():
                self.assertEqual(len(ports),3,tag)
                core = next(p for r,p in ports if r['role']=='main' and not r.get('profile'))
                wide = next(p for r,p in ports if r.get('profile')=='connector')
                ramp = next(p for r,p in ports if r['role']=='diamond')
                self.assertAlmostEqual(abs(core[1])-profile['mainWidth']/2,
                                       abs(wide[1])-profile['connectorWidth']/2)
                self.assertAlmostEqual(abs(ramp[1])-abs(wide[1]),4)
                self.assertEqual(core[0],wide[0])
                self.assertEqual(ramp[0],wide[0])
                self.assertEqual(core[2],ramp[2])

    def test_independent_road_surface_envelopes(self):
        # A centreline-only test misses neighbouring decks converging while climbing.
        # Use native full road widths, including shoulders. Shared junction roads
        # legitimately overlap at their merge; their later crossings are tested above.
        for kind, params in geometry_cases():
            net = self.make(kind,**params,crossLanes=2)
            profile = road_profile(**params,crossLanes=2)
            paths = []
            for road in net['roads']:
                tags = {s.get(k) for s in road['segments'] for k in ('tag0','tag1')}-{None}
                points = np.concatenate([sample(s,97)[0] for s in road['segments']])
                width = profile.get(road.get('profile',road['role'])+'Width',profile['rampWidth'])
                paths.append((road['id'],tags,points,width))
            for (a,at,p,aw),(b,bt,q,bw) in itertools.combinations(paths,2):
                if at & bt:
                    continue
                horizontal = np.linalg.norm(p[:,None,:2]-q[None,:,:2],axis=2)
                vertical = np.abs(p[:,None,2]-q[None,:,2])
                bad = (horizontal < (aw+bw)/2-.05) & (vertical < 7.5)
                self.assertFalse(bad.any(),(kind,params,a,b))

    def test_merge_approach_clears_mainline_before_next_internal_node(self):
        # Native failed pairs overlapped all the way to the ramp's next node.
        # Check those pairs too: shared tags cannot exempt the entire road.
        for kind, params in geometry_cases():
            net, profile = self.make(kind,**params), road_profile(**params)
            main_ports = {}
            for road in net['roads']:
                if road['role'] != 'main':
                    continue
                points = np.concatenate([sample(s,257)[0] for s in road['segments']])
                for s in road['segments']:
                    for end in ('0','1'):
                        if s.get('tag'+end):
                            main_ports[s['tag'+end]] = points
            for road in net['roads']:
                if road['role'] == 'main':
                    continue
                width = profile.get(road.get('profile',road['role'])+'Width',profile['rampWidth'])
                for s in road['segments']:
                    for end, other in (('0','1'),('1','0')):
                        tag = s.get('tag'+end)
                        if tag not in main_ports:
                            continue
                        locations = []
                        if kind in ('stack','turbine') and road['role']=='left':
                            locations.append(sample(s,3)[0][1])
                        if s.get('tag'+other) not in main_ports:
                            locations.append(np.array(s['p'+other]))
                        for p in locations:
                            q = main_ports[tag]
                            horizontal = np.linalg.norm(q[:,:2]-p[:2],axis=1)
                            vertical = np.abs(q[:,2]-p[2])
                            bad = (horizontal < (width+profile['mainWidth'])/2-.05) & (vertical < 7.5)
                            self.assertFalse(bad.any(),(kind,params,road['id'],tag,p))

    def test_each_numbered_switch_removes_only_its_own_ramp(self):
        for kind, prefix, ids in (
            ('cloverleaf','leaf',('loop-E','loop-S','loop-W','loop-N')),
            ('diamond','ramp',('ramp1','ramp2','ramp3','ramp4')),
        ):
            original = {r['id']:r for r in self.make(kind)['roads']}
            no_points = {r['id']:r for r in self.make(kind,**{prefix+'Enabled'+str(i):1 for i in range(1,5)})['roads']}
            for switches in itertools.product((1,2),repeat=4):
                net = self.make(kind,**{prefix+'Enabled'+str(i+1):v for i,v in enumerate(switches)})
                actual = {r['id']:r for r in net['roads']}
                removed = {ids[i] for i,v in enumerate(switches) if v == 1}
                added = set()
                if kind == 'cloverleaf':
                    for i,v in enumerate(switches):
                        if v == 1:
                            arm = ids[i].split('-')[-1]
                            right_arm = ('N','E','S','W')[i]
                            removed.update(('loop-tail-'+arm,'shared-'+arm,
                                            'right-in-'+right_arm,'right-out-'+right_arm))
                            added.add('right-'+right_arm)
                self.assertEqual(set(actual),(set(original)-removed)|added)
                for key in actual:
                    self.assertEqual(actual[key],no_points[key] if key in added else original[key])
                    if key in added:
                        self.assertEqual(len(actual[key]['segments']),1)

    def test_native_rotation_and_height_do_not_change_local_geometry(self):
        for kind in KINDS:
            base = self.make(kind)
            for rotation,height in ((10,1),(90,2),(180,-8)):
                self.assertEqual(self.make(kind,rotation=rotation,height=height),base)

    def test_removed_settings_do_not_change_the_fixed_small_highway_geometry(self):
        for kind,params in geometry_cases():
            expected = self.make(kind,lanes=params['lanes'])
            self.assertEqual(self.make(kind,lanes=params['lanes'],size=3,roadType=2,bridge=2,
                                       cloverLayout=2,crossApproach=2,crossLanes=2,loopSide=2),expected)

    def test_hub_right_turn_clears_the_separate_left_turn_node(self):
        for kind,lanes in itertools.product(('stack','turbine'),(1,2)):
            net,profile = self.make(kind,lanes=lanes),road_profile(lanes=lanes)
            nodes = {s['tag'+end]:np.array(s['p'+end]) for road in net['roads'] if road['role']=='main'
                     for s in road['segments'] for end in ('0','1')
                     if s.get('tag'+end,'').endswith(('left-in','left-out'))}
            self.assertEqual(len(nodes),8)
            for road in net['roads']:
                if road['role']!='right': continue
                points=np.concatenate([sample(s,257)[0] for s in road['segments']])
                for tag,p in nodes.items():
                    distance=np.linalg.norm(points[:,:2]-p[:2],axis=1).min()
                    self.assertGreater(distance-(profile['mainWidth']+profile['rampWidth'])/2,.5,
                                       (kind,lanes,road['id'],tag,distance))

    def test_shared_arc_is_one_two_way_road_with_lane_aligned_approaches(self):
        for road_type, lanes in itertools.product((1,2),(1,2)):
            net = self.make('cloverleaf',roadType=road_type,lanes=lanes)
            paths = {r['id']:r for r in net['roads']}
            endpoints = {}
            for road in net['roads']:
                for s in road['segments']:
                    for end in ('0','1'):
                        tag = s.get('tag'+end)
                        if tag and tag.startswith('shared-'):
                            endpoints.setdefault(tag,[]).append((road['id'],end,s['p'+end],s['t'+end]))
            self.assertEqual(len(endpoints),8)
            self.assertEqual(sum(r['role']=='shared' for r in net['roads']),4)
            self.assertFalse(any(key.startswith('shared-return-') for key in paths))
            for tag, connections in endpoints.items():
                self.assertEqual(len(connections),3,tag)
                self.assertEqual({c[1] for c in connections},{'0','1'},tag)
                shared = next(c for c in connections if paths[c[0]]['role']=='shared')
                p,t = np.array(shared[2]),np.array(shared[3])
                forward = t/np.linalg.norm(t)
                right = np.array([forward[1],-forward[0],0])
                for c in connections:
                    path = paths[c[0]]
                    if path['role'] == 'shared':
                        continue
                    self.assertNotEqual(path.get('profile'),'shared')
                    side = -1 if path['role']=='right' else 1
                    np.testing.assert_allclose(c[2],p+side*2.5*right,atol=1e-8)
                    direction = np.array(c[3])/np.linalg.norm(c[3])
                    angle = np.radians(30 if c[1]=='1' else -30)
                    expected = side*np.array([np.cos(angle)*forward[0]-np.sin(angle)*forward[1],
                                              np.sin(angle)*forward[0]+np.cos(angle)*forward[1],0])
                    np.testing.assert_allclose(direction,expected,atol=1e-8)

    def test_compact_defaults_and_different_templates(self):
        limits = {'cloverleaf':285,'diamond':180,'trumpet':280,'directional':272,'turbine':435,'stack':435}
        for kind, limit in limits.items():
            net = self.make(kind)
            points = np.concatenate([sample(s)[0] for r in net['roads'] for s in r['segments']])
            self.assertLessEqual(np.ptp(points[:,:2],axis=0).max(), limit)
        self.assertNotEqual(self.make('turbine')['roads'],self.make('stack')['roads'])
        self.assertEqual(sum(r['role']=='loop' for r in self.make('cloverleaf')['roads']),4)
        self.assertEqual(sum(r['role']=='loop' for r in self.make('trumpet')['roads']),1)
        self.assertEqual(sum(r['role']=='loop' for r in self.make('directional')['roads']),0)

    def test_native_comparison_candidates_preserve_connected_turns(self):
        lua = runtime()
        designs = lua.execute((CONTENT/'design_candidates.lua').read_text(encoding='utf-8'))
        for kind in ('cloverleaf','turbine','stack','trumpet','directional'):
            for probe,road_type,lanes in itertools.product(range(1,len(designs.options(kind))+1),(1,2),(1,2)):
                net = self.make(kind,_ipProbe=probe,roadType=road_type,lanes=lanes)
                graph,inputs,outputs = {},set(),set()
                for road in net['roads']:
                    for s in road['segments']:
                        self.assertTrue(np.isfinite([s['p0'],s['p1'],s['t0'],s['t1']]).all())
                        a,b = node(s['p0'],s.get('tag0')),node(s['p1'],s.get('tag1'))
                        graph.setdefault(a,set()).add(b)
                        if road['role']=='shared': graph.setdefault(b,set()).add(a)
                        if isinstance(a,str) and a.endswith('external-in'): inputs.add(a)
                        if isinstance(b,str) and b.endswith('external-out'): outputs.add(b)
                for source in inputs:
                    seen,todo = {source},[source]
                    while todo:
                        for target in graph.get(todo.pop(),()):
                            if target not in seen: seen.add(target); todo.append(target)
                    self.assertGreaterEqual(len(outputs&seen),len(outputs)-1,(kind,probe,road_type,lanes,source))


class ConstructionTests(unittest.TestCase):
    def test_drag_cache_keeps_fresh_output_and_invalidates_changed_geometry(self):
        lua = runtime()
        lua.execute('''
          generated=0
          local prior=require
          function require(name)
            local value=prior(name)
            if name:find("/geometry.lua",1,true) then
              local generate=value.generate
              value.generate=function(...)
                generated=generated+1
                return generate(...)
              end
            end
            return value
          end
        ''')
        lua.execute((CONTENT/'interchange.script.lua').read_text(encoding='utf-8'))
        lua.execute('''
          local update=data().updateFn
          local first=update({kind="cloverleaf"},{lanes=1})
          local expected=first.edgeLists[1].edges[1][1][1]
          first.edgeLists[1].edges[1][1][1]=999999
          local second=update({kind="cloverleaf"},{lanes=1,seed=3,year=1944,rotation=90,height=5})
          assert(generated==1)
          assert(second.edgeLists[1].edges[1][1][1]==expected)
          update({kind="cloverleaf"},{lanes=2})
          assert(generated==2)
          update({kind="trumpet"},{lanes=2})
          assert(generated==3)
        ''')

    def test_highway_lane_counts_and_native_shared_roads(self):
        lua = runtime()
        for road_type,lanes in itertools.product((1,2),(1,2)):
            profile = road_profile(roadType=road_type,lanes=lanes)
            expected_main = ('highway_new_medium','highway_new_large')[lanes-1]
            self.assertTrue(profile['main'].endswith(expected_main+'.street_template'))
            self.assertTrue(profile['ramp'].endswith('highway_new_small.street_template'))
            self.assertEqual(profile['shared'],'::/infrastructure/street/country/country_new_small.street_template')
            lua.execute((CONTENT/'interchange.script.lua').read_text(encoding='utf-8'))
            callback = lua.globals().data().updateFn
            for kind in KINDS:
                result = unpack(callback(lua.table_from({'kind':kind}),lua.table_from({'roadType':road_type,'lanes':lanes})))
                types = {g['params']['type'] for g in result['edgeLists']}
                self.assertIn(profile['main'],types)
                self.assertIn(profile['shared'] if kind=='cloverleaf' else profile['ramp'],types)
                self.assertTrue(all(name.startswith('::/infrastructure/street/') for name in types))
        for name,count,width in (('town_three',3,21),('shared_town',1,8),('shared_highway',1,7)):
            lua.execute((CONTENT/(name+'.street_template.lua')).read_text(encoding='utf-8'))
            definition = unpack(lua.globals().data())
            car_lanes = [l for l in definition['laneConfigs'] if 'CAR' in l['transportModes']]
            self.assertEqual(len(car_lanes),count)
            self.assertTrue(all(l['forward'] for l in car_lanes))
            self.assertEqual(sum(l['width'] for l in definition['laneConfigs']),width)

    def test_english_construction_menu_and_saved_road_names(self):
        lua = runtime('en')
        lua.execute((CONTENT/'menu_category.res.lua').read_text(encoding='utf-8'))
        self.assertEqual(lua.globals().data().data.name, 'Interchanges')
        names = ('Cloverleaf interchange', 'Diamond interchange', 'Trumpet interchange',
                 'Directional T interchange', 'Turbine interchange', 'Four-level stack interchange')
        for kind, name in zip(KINDS, names):
            with self.subTest(kind=kind):
                lua.execute((CONTENT/(kind+'.con.lua')).read_text(encoding='utf-8'))
                definition = unpack(lua.globals().data())
                self.assertEqual(definition['description']['name'], name)
                self.assertTrue(definition['description']['description'].isascii())
                self.assertEqual(definition['params'][0]['name'], 'Lanes')
                for option in definition['params'][1:]:
                    self.assertEqual(option['values'], ['Off', 'Keep'])
        for kind in ('town_three', 'shared_town', 'shared_highway'):
            lua.execute((CONTENT/(kind+'.street_template.lua')).read_text(encoding='utf-8'))
            self.assertTrue(lua.globals().data().description.name.isascii())

    def test_menu_defaults_and_real_callback(self):
        lua = runtime()
        lua.execute((CONTENT/'menu_category.res.lua').read_text(encoding='utf-8'))
        resource = unpack(lua.globals().data())
        self.assertEqual(resource['type'],'menu_category')
        category = resource['data']
        self.assertEqual(category['menu'],'ROADS')
        self.assertNotEqual(category['category'],'street_constructions')
        for kind in KINDS:
            lua.execute((CONTENT / (kind+'.con.lua')).read_text(encoding='utf-8'))
            con = lua.globals().data()
            definition = unpack(con)
            self.assertEqual(definition['availability'],{'yearFrom':1940,'yearTo':0})
            self.assertEqual(len(definition['menuCategory']['categories']),1)
            self.assertEqual(definition['menuCategory']['categories'][0]['category'],category['category'])
            defaults = {p['key']:p['defaultIndex'] for p in definition['params']}
            self.assertTrue({'height','rotation','levelSpacing','size','roadType','bridge','cloverLayout',
                             'crossApproach','crossLanes','loopSide'}.isdisjoint(defaults))
            self.assertEqual(definition['params'][0]['name'],'车道')
            self.assertEqual(definition['params'][0]['values'],['2','3'])
            self.assertEqual(len(defaults),5 if kind in ('cloverleaf','diamond') else 1)
            for p in definition['params']:
                if p['key'].startswith(('leaf','ramp')):
                    self.assertEqual(p['name'],p['key'][-1])
                    self.assertEqual(p['defaultIndex'],2)
                    self.assertEqual(p['uiType'],'CheckBox')
                    self.assertEqual(p['displayMode'],'Compact')
                    self.assertEqual(p['group'],'interchangePoints')
                    self.assertTrue(p['hideLabel'])
            for field in ('icon','previewIcon'):
                path = CONTENT / definition['description'][field].replace('.tga','@2x.tga')
                header = path.read_bytes()[:18]
                self.assertEqual(header[2],2)
                self.assertGreaterEqual(struct.unpack_from('<H',header,12)[0],256)
            lua.execute((CONTENT/'interchange.script.lua').read_text(encoding='utf-8'))
            result = unpack(lua.globals().data().updateFn(con.updateScript.params,lua.table_from(defaults)))
            self.assertTrue(result['edgeLists'])
            for group in result['edgeLists']:
                self.assertEqual(group['type'],'STREET')
                self.assertEqual(len(group['edges'])%2,0)
                self.assertEqual(group['freeNodes'],list(range(len(group['edges']))))
                self.assertNotIn('alignTerrain',group)
                self.assertTrue(all(len(endpoint)==3 and isinstance(endpoint[2],str) for endpoint in group['edges']))
                self.assertTrue(group['params']['type'].startswith(('::/infrastructure/street/','xin_interchange_pack_1::/interchanges/')))
                if group.get('edgeType'):
                    self.assertEqual(group['edgeType'],'BRIDGE')
                    self.assertTrue(group['edgeTypeName'].endswith('/concrete.bridge'))

    def test_old_choices_cannot_reenable_streets_sizes_or_steel_bridges(self):
        lua = runtime()
        lua.execute((CONTENT/'interchange.script.lua').read_text(encoding='utf-8'))
        callback = lua.globals().data().updateFn
        for lanes, cross, bridge in itertools.product((1,2),repeat=3):
            result = unpack(callback(lua.table_from({'kind':'diamond'}),lua.table_from({'lanes':lanes,'crossLanes':cross,'bridge':bridge})))
            roads = {g['params']['type'].split('/')[-1] for g in result['edgeLists']}
            self.assertIn('highway_new_'+('medium' if lanes==1 else 'large')+'.street_template',roads)
            self.assertIn('country_new_small.street_template',roads)
            bridges = {g['edgeTypeName'] for g in result['edgeLists'] if g.get('edgeTypeName')}
            self.assertEqual(bridges,{'::/infrastructure/bridge/concrete.bridge'})


@unittest.skipUnless(os.environ.get('TF3_GAME_DIR'),'Set TF3_GAME_DIR for native resource checks')
class NativeResourceTests(unittest.TestCase):
    def test_native_lane_counts_directions_and_bridges(self):
        base = Path(os.environ['TF3_GAME_DIR']) / 'base/content/infrastructure'
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('function _(value) return value end')
        with ZipFile(base/'street.zip') as archive:
            for family, size, count in (('highway','small',1),('highway','medium',2),('highway','large',3),('country','small',2),('country','medium',4)):
                name = f'street/{family}/{family}_new_{size}.street_template.lua'
                lua.execute(archive.read(name).decode())
                road = unpack(lua.globals().data())
                self.assertEqual(road['availability']['yearFrom'],1940)
                self.assertEqual(road['availability']['yearTo'],0)
                lanes = [lane for lane in road['laneConfigs'] if 'CAR' in lane['transportModes']]
                self.assertEqual(len(lanes),count)
                self.assertEqual(sum(l['forward'] for l in lanes),count if family=='highway' else count//2)
                expected = {('highway',1):9,('highway',2):18,('highway',3):23,('country',2):14,('country',4):22}
                self.assertEqual(sum(l['width'] for l in road['laneConfigs']),expected[family,count])
            for name,count,width,forward in (
                ('town/town_new_one_way_small',2,16,2),
                ('town/town_new_small',2,16,1),
                ('town/town_new_medium',4,24,2),
                ('constructions/entrance_new_one_way',1,11,1),
            ):
                lua.execute(archive.read('street/'+name+'.street_template.lua').decode())
                road = unpack(lua.globals().data())
                cars = [l for l in road['laneConfigs'] if 'CAR' in l['transportModes']]
                self.assertEqual(len(cars),count)
                self.assertEqual(sum(l['forward'] for l in cars),forward)
                self.assertEqual(sum(l['width'] for l in road['laneConfigs']),width)
        with ZipFile(base/'bridge.zip') as archive:
            self.assertIn('bridge/concrete.bridge.lua',archive.namelist())
            self.assertIn('bridge/steel.bridge.lua',archive.namelist())


if __name__ == '__main__':
    unittest.main()
