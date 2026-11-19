"""Survival Race rebuild - procedural Blender models (Blender 5.x as python module).
Everything is built facing Blender -Y (exports to glTF +Z = game forward), Z up.
"""
import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

OUT = sys.argv[-1] if sys.argv[-1].endswith('.glb') else '/home/claude/models/sr_models.glb'

# ---------------------------------------------------------------- utils
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

MATS = {}
def mat(name, color, metal=0.0, rough=0.5, emit=None, alpha=1.0):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Roughness'].default_value = rough
    if emit:
        bsdf.inputs['Emission Color'].default_value = (*emit, 1)
        bsdf.inputs['Emission Strength'].default_value = 1.0
    if alpha < 1:
        bsdf.inputs['Alpha'].default_value = alpha
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
    MATS[name] = m
    return m

def srgb(h):
    h = h.lstrip('#'); c = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(((x+0.055)/1.055)**2.4 if x > 0.04045 else x/12.92 for x in c)

def new_obj(name, bm, material=None, parent=None, smooth=True, angle=40):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material: me.materials.append(material)
    if parent: ob.parent = parent
    for p in me.polygons: p.use_smooth = smooth
    if smooth:
        try:
            bpy.context.view_layer.objects.active = ob
            for o in bpy.context.selected_objects: o.select_set(False)
            ob.select_set(True)
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
        except Exception as e:
            pass
    return ob

def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    if parent: e.parent = parent
    return e

def add_mod(ob, kind, **kw):
    m = ob.modifiers.new(kind.lower(), kind)
    for k, v in kw.items(): setattr(m, k, v)
    return m

def apply_mods(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)

def catmull(pts, t):
    """pts: list of (t,v) sorted; smooth interpolation."""
    if t <= pts[0][0]: return pts[0][1]
    if t >= pts[-1][0]: return pts[-1][1]
    for i in range(len(pts)-1):
        if pts[i][0] <= t <= pts[i+1][0]: break
    p0 = pts[max(i-1, 0)][1]; p1 = pts[i][1]; p2 = pts[i+1][1]; p3 = pts[min(i+2, len(pts)-1)][1]
    u = (t-pts[i][0])/(pts[i+1][0]-pts[i][0])
    return 0.5*((2*p1) + (-p0+p2)*u + (2*p0-5*p1+4*p2-p3)*u*u + (-p0+3*p1-3*p2+p3)*u**3)

def ring(y, zb, zt, wb, wt, p, N):
    pts = []
    for k in range(N):
        a = 2*math.pi*k/N
        c, s = math.cos(a), math.sin(a)
        u = math.copysign(abs(c)**p, c); v = math.copysign(abs(s)**p, s)
        f = (v+1)/2
        z = zb + f*(zt-zb); w = wb + f*(wt-wb)
        pts.append((u*w, y, z))
    return pts

def loft(sections, N=24, cap=True):
    """sections: list of (y, zb, zt, wb, wt, p) ordered rear->front (y decreasing)."""
    bm = bmesh.new()
    rings = []
    for s in sections:
        rings.append([bm.verts.new(v) for v in ring(*s, N)])
    for a, b in zip(rings, rings[1:]):
        for k in range(N):
            k2 = (k+1) % N
            try: bm.faces.new((a[k], a[k2], b[k2], b[k]))
            except ValueError: pass
    if cap:
        for r, flip in ((rings[0], False), (rings[-1], True)):
            c = bm.verts.new(tuple(sum(v.co[i] for v in r)/N for i in range(3)))
            for k in range(N):
                vs = (r[k], r[(k+1) % N], c) if not flip else (r[(k+1) % N], r[k], c)
                try: bm.faces.new(vs)
                except ValueError: pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def box(sx, sy, sz, loc=(0, 0, 0), bevel=0.0, segs=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segs, affect='EDGES', profile=0.5)
    return bm

def cyl(r, depth, segs=24, loc=(0, 0, 0), axis='Z', r2=None, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r if r2 is None else r2, depth=depth)
    if bevel > 0:
        caps = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6]
        bmesh.ops.bevel(bm, geom=caps, offset=bevel, segments=3, affect='EDGES', profile=0.5)
    if axis == 'X': bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi/2, 3, 'Y'))
    if axis == 'Y': bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi/2, 3, 'X'))
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return bm

def sphere(r, loc=(0, 0, 0), seg=24, rings=16, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return bm

def join(objs, name):
    bpy.context.view_layer.objects.active = objs[0]
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]

# ---------------------------------------------------------------- materials
def materials():
    mat('Paint', srgb('e8322f'), metal=0.2, rough=0.25)
    mat('Glass', srgb('15181f'), metal=0.6, rough=0.08)
    mat('Trim', srgb('1d1f24'), rough=0.6)
    mat('Chrome', srgb('d8dde3'), metal=1.0, rough=0.18)
    mat('HeadLight', srgb('ffffff'), rough=0.2, emit=srgb('fff6d8'))
    mat('TailLight', srgb('ff1a1a'), rough=0.3, emit=srgb('ff0000'))
    mat('Tyre', srgb('1a1a1c'), rough=0.85)
    mat('Rim', srgb('c9ced6'), metal=1.0, rough=0.25)
    mat('RimDark', srgb('2a2d33'), metal=0.8, rough=0.35)

# ---------------------------------------------------------------- cars
CARS = {
    # name: params
    'striker': dict(L=4.35, W=0.96, R=0.36, wr=0.19, wf=0.80,
        top=[(0, .80), (.12, .84), (.35, .76), (.6, .70), (.78, .58), (.92, .49), (1, .40)],
        bot=[(0, .30), (.5, .24), (1, .27)],
        wid=[(0, .90), (.2, .97), (.5, .95), (.8, .93), (1, .74)],
        gh=(.34, .70), roof=1.14, rakeF=.17, rakeR=.13, ghw=(.86, .56), p=.42, spoiler='wing', vents=True),
    'drifter': dict(L=4.5, W=0.93, R=0.36, wr=0.18, wf=0.79,
        top=[(0, .82), (.15, .85), (.4, .84), (.62, .82), (.8, .76), (.94, .66), (1, .55)],
        bot=[(0, .30), (.5, .25), (1, .28)],
        wid=[(0, .88), (.18, .94), (.5, .92), (.82, .91), (1, .80)],
        gh=(.27, .62), roof=1.30, rakeF=.15, rakeR=.12, ghw=(.86, .6), p=.38, spoiler='bigwing'),
    'hyper': dict(L=4.55, W=0.99, R=0.37, wr=0.19, wf=0.80,
        top=[(0, .86), (.15, .88), (.4, .80), (.62, .74), (.8, .66), (.94, .58), (1, .50)],
        bot=[(0, .30), (.5, .25), (1, .27)],
        wid=[(0, .86), (.2, .99), (.5, .98), (.8, .96), (1, .78)],
        gh=(.30, .70), roof=1.19, rakeF=.18, rakeR=.2, ghw=(.84, .55), p=.55, spoiler=None, stripe=True),
    'muscle': dict(L=4.7, W=0.98, R=0.38, wr=0.18, wf=0.80,
        top=[(0, .88), (.1, .90), (.35, .86), (.6, .88), (.8, .88), (.95, .84), (1, .74)],
        bot=[(0, .32), (.5, .27), (1, .30)],
        wid=[(0, .94), (.2, .97), (.5, .96), (.8, .97), (1, .92)],
        gh=(.24, .56), roof=1.38, rakeF=.11, rakeR=.12, ghw=(.88, .66), p=.28, spoiler='lip', scoop=True),
    'hatch': dict(L=3.95, W=0.92, R=0.35, wr=0.17, wf=0.82,
        top=[(0, .94), (.1, .96), (.4, .90), (.65, .86), (.82, .80), (.95, .72), (1, .64)],
        bot=[(0, .30), (.5, .26), (1, .29)],
        wid=[(0, .88), (.15, .92), (.5, .92), (.85, .9), (1, .80)],
        gh=(.07, .63), roof=1.47, rakeF=.17, rakeR=.04, ghw=(.88, .66), p=.36, spoiler='roof'),
    'gt': dict(L=4.5, W=0.95, R=0.36, wr=0.19, wf=0.79,
        top=[(0, .78), (.12, .82), (.36, .80), (.6, .76), (.8, .70), (.94, .60), (1, .50)],
        bot=[(0, .29), (.5, .25), (1, .27)],
        wid=[(0, .86), (.18, .95), (.5, .93), (.82, .92), (1, .78)],
        gh=(.18, .66), roof=1.24, rakeF=.16, rakeR=.30, ghw=(.86, .56), p=.45, spoiler='duck'),
}

def build_car(name, P):
    root = empty('CAR_' + name)
    L, W = P['L'], P['W']
    Y = lambda t: (0.5 - t) * L          # t=0 rear (+Y), t=1 nose (-Y)
    top = lambda t: catmull(P['top'], t)
    bot = lambda t: catmull(P['bot'], t)
    R = P['R'] = P['R']*1.1
    def wid(t):
        bump = 0.0
        for wt in (P['wr'], P['wf']):
            d = abs(t-wt)/0.11
            if d < 1: bump += 0.07*(1-d*d)
        return (catmull(P['wid'], t) + bump) * W
    S = 30
    ts = [(i/(S-1))**1.0 for i in range(S)]
    # tighten ends for rounded nose/tail
    sec = []
    for t in ts:
        endk = min(t, 1-t)
        round_in = 1 - (1 - min(1, endk/0.04))**2 * 0.25
        zb = bot(t) + 0.10
        sec.append((Y(t), zb, top(t), wid(t)*0.93*round_in, wid(t)*0.86*round_in, P['p']))
    body = new_obj(name + '_body', loft(sec, N=28), MATS['Paint'], root, angle=50)
    add_mod(body, 'SUBSURF', levels=1, render_levels=1); apply_mods(body)
    # black skirt / underbody
    sk = []
    for t in ts[1:-1]:
        sk.append((Y(t), bot(t), bot(t)+0.17, wid(t)*0.9, wid(t)*0.92, 0.35))
    new_obj(name + '_skirt', loft(sk, N=16), MATS['Trim'], root, angle=60)
    # greenhouse (glass)
    g0, g1 = P['gh']; roof = P['roof']; rf, rr = P['rakeF'], P['rakeR']
    def roofz(t):
        belt = top(t) - 0.03
        if t < g0 + rr: k = (t-g0)/rr; return belt + (roof - belt)*math.sin(min(max(k, 0), 1)*math.pi/2)
        if t > g1 - rf: k = (g1-t)/rf; return belt + (roof - belt)*math.sin(min(max(k, 0), 1)*math.pi/2)
        return roof + 0.025*math.sin((t-g0)/(g1-g0)*math.pi)
    gs = []
    G = 22
    for i in range(G):
        t = g0 + (g1-g0)*i/(G-1)
        belt = top(t) - 0.05
        gs.append((Y(t), belt, max(roofz(t), belt+0.01), wid(t)*P['ghw'][0], wid(t)*P['ghw'][1], 0.45))
    gl = new_obj(name + '_glass', loft(gs, N=20), MATS['Glass'], root, angle=50)
    add_mod(gl, 'SUBSURF', levels=1); apply_mods(gl)
    # roof panel (paint) - covers the flat middle so windows read as a band
    rs = []
    a, b = g0 + rr*0.85, g1 - rf*0.85
    for i in range(14):
        t = a + (b-a)*i/13
        z = roofz(t)
        rs.append((Y(t), z-0.07, z+0.022, wid(t)*P['ghw'][1]*1.06, wid(t)*P['ghw'][1]*0.98, 0.5))
    rp = new_obj(name + '_roof', loft(rs, N=20), MATS['Paint'], root, angle=50)
    # pillars: thin paint bands at front/rear of the glass, sides only
    # head lights
    tn = 0.985
    for sx in (-1, 1):
        hl = box(0.32, 0.1, 0.09, bevel=0.025)
        o = new_obj(name + '_hl', hl, MATS['HeadLight'], root, angle=30)
        o.location = (sx*wid(tn)*0.6, Y(tn)+0.04, top(tn)-0.05); o.rotation_euler = (0.35, 0, -sx*0.25)
    # tail light strip + exhausts
    tr = 0.008
    tl = box(wid(tr)*1.7, 0.06, 0.07, loc=(0, Y(tr)+0.01, top(tr)-0.12), bevel=0.02)
    new_obj(name + '_tl', tl, MATS['TailLight'], root, angle=30)
    for sx in (-1, 1):
        new_obj(name + '_tl2', box(0.36, 0.07, 0.11, loc=(sx*wid(tr)*0.62, Y(tr)+0.005, top(tr)-0.12), bevel=0.025), MATS['TailLight'], root)
        new_obj(name + '_exh', cyl(0.06, 0.18, 16, loc=(sx*0.3, Y(0.0)+0.04, bot(0)+0.12), axis='Y'), MATS['Chrome'], root)
    # grille / front intake
    new_obj(name + '_grille', box(wid(1)*1.2, 0.08, 0.14, loc=(0, Y(1.0)+0.02, bot(1)+0.2), bevel=0.03), MATS['Trim'], root)
    # mirrors
    tm = g1 - rf*0.9
    for sx in (-1, 1):
        new_obj(name + '_mirror', box(0.16, 0.1, 0.08, loc=(sx*(wid(tm)*0.98), Y(tm), top(tm)+0.06), bevel=0.03), MATS['Paint'], root)
    if P.get('vents'):
        for sx in (-1, 1):
            new_obj(name + '_vent', box(0.06, 0.55, 0.16, loc=(sx*wid(.42)*0.93, Y(.42), (top(.42)+bot(.42))/2+0.05), bevel=0.02), MATS['Trim'], root)
    if P.get('scoop'):
        new_obj(name + '_scoop', box(0.42, 0.7, 0.12, loc=(0, Y(.8), top(.8)+0.03), bevel=0.04), MATS['Trim'], root)
    if P.get('stripe'):
        for sx in (-1, 1):
            st = []
            for i in range(10):
                t = 0.3 + 0.38*i/9
                z = (top(t)+bot(t))/2 + 0.12*math.sin((t-.3)/.38*math.pi)
                st.append((Y(t), z-0.025, z+0.025, wid(t)*0.935*0.98, wid(t)*0.935*0.98, 1.0))
            # thin strips just outside the body side
            bm = bmesh.new()
            for (y, z0, z1, w, _, _) in st: pass
        # chrome side accent as a curved thin box on each side
        for sx in (-1, 1):
            new_obj(name + '_accent', box(0.025, L*0.36, 0.05, loc=(sx*(wid(.5)*0.92), Y(.5), (top(.5)+bot(.5))/2+0.1), bevel=0.012), MATS['Chrome'], root)
    sp = P['spoiler']
    if sp in ('wing', 'bigwing'):
        h = 0.32 if sp == 'bigwing' else 0.22
        z = top(0.04) + h
        for sx in (-1, 1):
            new_obj(name + '_post', box(0.05, 0.12, h+0.05, loc=(sx*wid(0.05)*0.55, Y(0.05), top(0.05)+h/2-0.02), bevel=0.01), MATS['Trim'], root)
        wing = box(wid(0.03)*2.1, 0.34, 0.05, loc=(0, Y(0.03), z), bevel=0.02)
        o = new_obj(name + '_spoiler', wing, MATS['Trim'] if sp == 'bigwing' else MATS['Paint'], root)
        for sx in (-1, 1):
            new_obj(name + '_endplate', box(0.03, 0.4, 0.16, loc=(sx*wid(0.03)*1.05, Y(0.03), z-0.03), bevel=0.01), MATS['Trim'], root)
    elif sp == 'lip':
        new_obj(name + '_spoiler', box(wid(0.03)*1.7, 0.18, 0.07, loc=(0, Y(0.03), top(0.03)+0.03), bevel=0.03), MATS['Paint'], root)
    elif sp == 'duck':
        o = new_obj(name + '_spoiler', box(wid(0.03)*1.6, 0.26, 0.06, bevel=0.03), MATS['Paint'], root); o.location = (0, Y(0.025), top(0.025)+0.04); o.rotation_euler = (-0.25, 0, 0)
    elif sp == 'roof':
        o = new_obj(name + '_spoiler', box(wid(g0)*1.2, 0.3, 0.06, bevel=0.03), MATS['Paint'], root); o.location = (0, Y(g0)-0.05, roof-0.01); o.rotation_euler = (-0.15, 0, 0)
    # wheel anchors (game positions wheels here)
    for tag, t in (('R', P['wr']), ('F', P['wf'])):
        for sx, side in ((-1, 'L'), (1, 'R')):
            empty(f'{name}_W_{tag}{side}', (sx*(W*0.96), Y(t), R), root)
    empty(f'{name}_WING', (W*0.7, Y(0.48), top(0.48)-0.05), root)
    root['wheelR'] = R
    return root

def build_wheel(name, rim_mat):
    root = empty(name)
    R, D = 1.0, 0.62   # unit radius; scaled in game
    t = cyl(R, D, 32, axis='X', bevel=0.18)
    new_obj('tyre', t, MATS['Tyre'], root, angle=35)
    new_obj('rim', cyl(0.66, D*0.92+0.04, 28, axis='X', bevel=0.04), MATS[rim_mat], root, angle=35)
    # outer rim lip and spokes
    lip = bmesh.new()
    bmesh.ops.create_cone(lip, cap_ends=False, segments=28, radius1=0.66, radius2=0.6, depth=0.06)
    bmesh.ops.rotate(lip, verts=lip.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi/2, 3, 'Y'))
    for sx in (-1, 1):
        for k in range(5):
            a = k*2*math.pi/5
            bm = box(0.06, 0.14, 1.08, loc=(sx*(D*0.48+0.02), 0, 0), bevel=0.02)
            bmesh.ops.translate(bm, vec=(0, 0, 0), verts=bm.verts)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(a, 3, 'X'))
            new_obj('spoke', bm, MATS['Chrome' if rim_mat=='Rim' else 'RimDark'], root, angle=30)
        new_obj('hub', cyl(0.16, 0.08, 16, axis='X', loc=(sx*(D*0.48+0.04), 0, 0)), MATS['Chrome'], root)
    lip.free()
    return root

def build_wing():
    """Single wing extending +X from hinge at origin; game mirrors it for the left side."""
    root = empty('WING')
    bm = bmesh.new()
    # tapered, swept wing with an elbow
    span1, span2 = 1.2, 1.15
    pts = [(0, -0.5), (span1, -0.38), (span1+span2, -0.22), (span1+span2, 0.10), (span1, 0.16), (0, 0.38)]
    top = [bm.verts.new((x, y, 0.06*(1-x/3))) for x, y in pts]
    botv = [bm.verts.new((x, y, -0.04*(1-x/3))) for x, y in pts]
    bm.faces.new(top); bm.faces.new(list(reversed(botv)))
    n = len(pts)
    for i in range(n):
        j = (i+1) % n
        bm.faces.new((top[i], botv[i], botv[j], top[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.025, segments=2, affect='EDGES')
    # elbow dihedral: lift outer part
    for v in bm.verts:
        if v.co.x > span1: v.co.z += (v.co.x-span1)*0.18
    new_obj('wing_panel', bm, MATS['Paint'], root, angle=35)
    # trailing edge stripe + root hinge
    new_obj('wing_hinge', cyl(0.12, 0.6, 16, axis='Y', loc=(0.02, 0, 0)), MATS['Trim'], root)
    new_obj('wing_tip', box(0.06, 0.34, 0.1, loc=(span1+span2, -0.06, 0.22), bevel=0.02), MATS['Trim'], root)
    return root

# ---------------------------------------------------------------- props
def star_shape(bm, r1, r2, z0, z1, loc=(0, 0, 0), axis='Z'):
    pts = []
    for i in range(10):
        r = r1 if i % 2 == 0 else r2
        a = math.pi/2 + i*math.pi/5
        pts.append((math.cos(a)*r, math.sin(a)*r))
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    ct = bm.verts.new((0, 0, z1)); cb = bm.verts.new((0, 0, z0))
    for i in range(10):
        j = (i+1) % 10
        bm.faces.new((top[i], top[j], ct)); bm.faces.new((bot[j], bot[i], cb))
        bm.faces.new((top[i], bot[i], bot[j], top[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if axis == 'Y': bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi/2, 3, 'X'))
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    return bm

def build_props():
    W = mat('White', srgb('ffffff'), rough=0.45)
    G1 = mat('IslandTop', srgb('d4d8e0'), rough=0.6)
    G2 = mat('IslandSide', srgb('aeb4c0'), rough=0.6)
    Blue = mat('PinBlue', srgb('1fa2ff'), rough=0.3, emit=srgb('0a4f8f'))
    Gold = mat('Gold', srgb('ffc21a'), metal=0.7, rough=0.25, emit=srgb('6b4a00'))
    NitroB = mat('NitroBlue', srgb('2e6bff'), metal=0.4, rough=0.3)
    Red = mat('RageRed', srgb('ff2a3a'), rough=0.35, emit=srgb('7a0010'))
    Balloon = mat('Balloon', srgb('ff3b5c'), rough=0.25)
    Orange = mat('PadOrange', srgb('ff8a1c'), rough=0.4, emit=srgb('5a2800'))
    Cyan = mat('PadGlow', srgb('3df0ff'), rough=0.3, emit=srgb('20c8ff'))
    Black = mat('Black', srgb('121214'), rough=0.6)
    BBall = mat('BasketOrange', srgb('ec7a22'), rough=0.55)
    Rugby = mat('RugbyRed', srgb('b3262d'), rough=0.5)
    Net = mat('Net', srgb('ffffff'), rough=0.6, alpha=0.55)
    Steel = mat('Container', srgb('2f6fd6'), rough=0.6)
    Steel2 = mat('ContainerRed', srgb('d6402f'), rough=0.6)

    # --- hex island: radius 3, height 1.2, white rim, light top
    root = empty('ISLAND')
    new_obj('island_side', cyl(3.0, 1.2, 6, loc=(0, 0, -0.6), r2=2.85), G2, root, smooth=False)
    new_obj('island_rim', cyl(3.04, 0.16, 6, loc=(0, 0, -0.06)), W, root, smooth=False)
    new_obj('island_top', cyl(2.6, 0.06, 6, loc=(0, 0, 0.0)), G1, root, smooth=False)
    for o in root.children: o.rotation_euler = (0, 0, math.pi/6)

    # --- star pin (map marker) ~1.6 tall
    root = empty('STARPIN')
    bm = bmesh.new()
    # lathe profile: teardrop
    prof = []
    for i in range(17):
        a = -math.pi/2 + math.pi*i/16
        prof.append((0.55*math.cos(a), 0.95 + 0.55*math.sin(a)))
    prof = [(0.0, 0.0), (0.12, 0.18), (0.3, 0.45)] + [p for p in prof if p[1] > 0.55]
    prof[-1] = (0.0, prof[-1][1])
    segs = 28
    rings_ = []
    for (r, z) in prof:
        rings_.append([bm.verts.new((r*math.cos(2*math.pi*k/segs), r*math.sin(2*math.pi*k/segs)*0.55, z)) for k in range(segs)])
    for a, b in zip(rings_, rings_[1:]):
        for k in range(segs):
            k2 = (k+1) % segs
            try: bm.faces.new((a[k], a[k2], b[k2], b[k]))
            except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    new_obj('pin_body', bm, Blue, root, angle=60)
    for sy in (-1, 1):
        s = star_shape(bmesh.new(), 0.3, 0.13, -0.03, 0.03, loc=(0, sy*0.31, 0.95), axis='Y')
        new_obj('pin_star', s, W, root, smooth=False)
    ring_ = bmesh.new()
    bmesh.ops.create_cone(ring_, cap_ends=True, segments=6, radius1=0.75, radius2=0.75, depth=0.06)
    inner = cyl(0.5, 0.08, 6)
    new_obj('pin_base', ring_, W, root, smooth=False)
    root.children[-1].rotation_euler = (0, 0, math.pi/6)
    inner.free()

    # --- coin
    root = empty('COIN')
    new_obj('coin_disc', cyl(0.5, 0.12, 32, axis='Y', bevel=0.03), Gold, root, angle=40)
    for sy in (-1, 1):
        new_obj('coin_star', star_shape(bmesh.new(), 0.26, 0.11, -0.02, 0.02, loc=(0, sy*0.07, 0), axis='Y'), Gold, root, smooth=False)

    # --- nitro bottle
    root = empty('NITRO')
    new_obj('n_body', cyl(0.26, 0.9, 24, loc=(0, 0, 0.45), bevel=0.08), NitroB, root)
    new_obj('n_neck', cyl(0.12, 0.22, 16, loc=(0, 0, 0.98)), MATS['Chrome'], root)
    new_obj('n_valve', box(0.32, 0.08, 0.08, loc=(0, 0, 1.1), bevel=0.02), MATS['Chrome'], root)
    new_obj('n_band', cyl(0.27, 0.16, 24, loc=(0, 0, 0.55)), W, root)

    # --- rage orb (spiky)
    root = empty('RAGE')
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.42)
    spikes = bmesh.ops.extrude_discrete_faces(bm, faces=bm.faces[:])['faces']
    for f in spikes:
        c = f.calc_center_median(); n = c.normalized()
        for v in f.verts: v.co = v.co*0.6 + n*0.25
        bmesh.ops.translate(bm, vec=n*0.28, verts=f.verts)
    new_obj('rage_spikes', bm, Red, root, smooth=False)
    new_obj('rage_core', sphere(0.42, seg=20, rings=14), Red, root)

    # --- balloon with string
    root = empty('BALLOON')
    b = sphere(0.7, loc=(0, 0, 0.85), seg=24, rings=16, scale=(1, 1, 1.18))
    for v in b.verts:
        if v.co.z < 0.85: v.co.x *= 0.8 + 0.2*(v.co.z/0.85); v.co.y *= 0.8 + 0.2*(v.co.z/0.85)
    new_obj('balloon_body', b, Balloon, root)
    new_obj('balloon_knot', cyl(0.08, 0.12, 10, loc=(0, 0, 0.02), r2=0.03), Balloon, root)
    new_obj('balloon_string', cyl(0.012, 1.2, 6, loc=(0, 0, -0.6)), W, root, smooth=False)

    # --- hex jump pad (r=2)
    root = empty('JUMPHEX')
    new_obj('jp_base', cyl(2.0, 0.3, 6, loc=(0, 0, 0.15)), MATS['Trim'], root, smooth=False)
    new_obj('jp_glow', cyl(1.75, 0.34, 6, loc=(0, 0, 0.17)), Cyan, root, smooth=False)
    new_obj('jp_top', cyl(1.45, 0.38, 6, loc=(0, 0, 0.19)), Orange, root, smooth=False)
    for k, o in enumerate(root.children): o.rotation_euler = (0, 0, math.pi/6)
    for i in range(3):
        bm = bmesh.new()
        pts = [(-0.7, 0.25), (0, -0.45), (0.7, 0.25), (0.7, 0.55), (0, -0.15), (-0.7, 0.55)]
        f = bm.faces.new([bm.verts.new((x, y + 0.0 - i*0.45 + 0.45, 0.39)) for x, y in pts])
        bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for v in bm.verts:
            if v.co.z > 0.385 and v.co.z < 0.395 and not v.is_boundary: pass
        o = new_obj('jp_arrow', bm, W, root, smooth=False)
        o.scale = (0.8, 0.8, 1.0)

    # --- quad ramp (wedge 4 wide, 5 long, 1.4 high), rising toward -Y (forward)
    root = empty('RAMP')
    bm = bmesh.new()
    w, l, h = 2.0, 2.6, 1.4
    vs = [bm.verts.new(p) for p in [(-w, l, 0), (w, l, 0), (w, -l, 0), (-w, -l, 0), (-w, -l, h), (w, -l, h)]]
    for f in [(0, 1, 2, 3), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2), (0, 4, 5, 1)]:
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    new_obj('ramp_body', bm, Orange, root, smooth=False)
    for i in range(4):
        y0 = l - 0.6 - i*1.25
        z0 = h*(l - y0)/(2*l)
        o = new_obj('ramp_stripe', box(3.6, 0.35, 0.04), W, root, smooth=False)
        o.location = (0, y0, z0+0.03); o.rotation_euler = (-math.atan2(h, 2*l), 0, 0)
    for sx in (-1, 1):
        o = new_obj('ramp_rail', box(0.12, 2*l*1.02, 0.12), Cyan, root, smooth=False); o.location = (sx*w, 0, h/2+0.05); o.rotation_euler = (-math.atan2(h, 2*l), 0, 0)

    # --- soccer ball (truncated icosahedron, r=1)
    root = empty('BALL_SOCCER')
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=0, radius=1.0)
    bmesh.ops.bevel(bm, geom=list(bm.verts), offset=1/3, offset_type='PERCENT', affect='VERTICES') if False else None
    res = bmesh.ops.bevel(bm, geom=list(bm.verts), offset=0.333, offset_type='OFFSET', segments=1, affect='VERTICES')
    pent = set(res['faces'])
    for v in bm.verts: v.co = v.co.normalized()
    me_w, me_b = bmesh.new(), bmesh.new()
    # split into two meshes by face type, then subdivide each & cast to sphere
    def extract(src, faces_keep, name, m):
        out = src.copy()
        keep_idx = {f.index for f in faces_keep}
        out.faces.ensure_lookup_table()
        dele = [f for f in out.faces if f.index not in keep_idx]
        bmesh.ops.delete(out, geom=dele, context='FACES')
        bmesh.ops.subdivide_edges(out, edges=out.edges[:], cuts=3, use_grid_fill=True)
        for v in out.verts: v.co = v.co.normalized()
        new_obj(name, out, m, root, angle=80)
    bm.faces.ensure_lookup_table()
    extract(bm, [f for f in bm.faces if f in pent], 'soccer_black', Black)
    extract(bm, [f for f in bm.faces if f not in pent], 'soccer_white', W)
    bm.free(); me_w.free(); me_b.free()

    # --- basketball (r=1)
    root = empty('BALL_BASKET')
    new_obj('bb_body', sphere(1.0, seg=32, rings=20), BBall, root)
    def seam(points, name):
        # tube along a closed polyline
        bm = bmesh.new()
        n = len(points); segs = 6; rr = 0.025
        rings_ = []
        for i, p in enumerate(points):
            p = Vector(p); t = (Vector(points[(i+1) % n]) - Vector(points[i-1])).normalized()
            a = p.normalized().cross(t).normalized(); b2 = t.cross(a).normalized()
            rings_.append([bm.verts.new(p + (a*math.cos(2*math.pi*k/segs) + b2*math.sin(2*math.pi*k/segs))*rr) for k in range(segs)])
        for i in range(n):
            A, B = rings_[i], rings_[(i+1) % n]
            for k in range(segs):
                bm.faces.new((A[k], A[(k+1) % segs], B[(k+1) % segs], B[k]))
        new_obj(name, bm, Black, root, angle=80)
    N = 64
    seam([(math.cos(2*math.pi*i/N)*1.005, math.sin(2*math.pi*i/N)*1.005, 0) for i in range(N)], 'seam_eq')
    seam([(0, math.cos(2*math.pi*i/N)*1.005, math.sin(2*math.pi*i/N)*1.005) for i in range(N)], 'seam_m')
    for sx in (-1, 1):
        pts = []
        for i in range(N):
            a = 2*math.pi*i/N
            v = Vector((sx*0.62, math.cos(a)*0.79, math.sin(a)*0.79)).normalized()*1.005
            pts.append(tuple(v))
        seam(pts, 'seam_c')

    # --- rugby ball (lathe, long axis Y, r~0.75 x 1.25)
    root = empty('BALL_RUGBY')
    bm = bmesh.new(); segs = 28; prof = []
    for i in range(21):
        u = -1 + 2*i/20
        prof.append((0.75*(1-u*u)**0.75, u*1.25))
    rings_ = []
    for r, y in prof:
        rings_.append([bm.verts.new((r*math.cos(2*math.pi*k/segs), y, r*math.sin(2*math.pi*k/segs))) for k in range(segs)])
    for a, b in zip(rings_, rings_[1:]):
        for k in range(segs):
            try: bm.faces.new((a[k], a[(k+1) % segs], b[(k+1) % segs], b[k]))
            except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    new_obj('rugby_body', bm, Rugby, root, angle=80)
    for sy in (-1, 1):
        new_obj('rugby_band', cyl(0.62, 0.09, 28, axis='Y', loc=(0, sy*0.72, 0)), W, root)
    new_obj('rugby_lace', box(0.08, 0.7, 0.05, loc=(0, 0, 0.75)), W, root, smooth=False)
    for i in range(5):
        new_obj('rugby_stitch', box(0.26, 0.05, 0.05, loc=(0, -0.28 + i*0.14, 0.75)), W, root, smooth=False)

    # --- goal (opening faces -Y): 8 wide, 3.5 high, 3 deep
    root = empty('GOAL')
    gw, gh, gd, t = 4.0, 3.5, 3.0, 0.22
    for sx in (-1, 1):
        new_obj('post', box(t, t, gh, loc=(sx*gw, 0, gh/2), bevel=0.05), W, root)
        new_obj('back_post', box(t*0.6, t*0.6, gh*0.9, loc=(sx*gw, gd, gh*0.45)), W, root)
        new_obj('side_top', box(t*0.6, gd, t*0.6, loc=(sx*gw, gd/2, gh-0.1)), W, root)
    new_obj('bar', box(gw*2+t, t, t, loc=(0, 0, gh), bevel=0.05), W, root)
    new_obj('back_bar', box(gw*2, t*0.6, t*0.6, loc=(0, gd, gh*0.9)), W, root)
    for (sx, sy, sz, loc, rot) in [(gw*2, 0.02, gh*0.9, (0, gd, gh*0.45), None), (0.02, gd, gh*0.9, (-gw, gd/2, gh*0.45), None),
                                   (0.02, gd, gh*0.9, (gw, gd/2, gh*0.45), None), (gw*2, gd, 0.02, (0, gd/2, gh-0.1), None)]:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
        new_obj('net', bm, Net, root, smooth=False)

    # --- shipping container decor (6 x 2.4 x 2.6)
    for nm, m in (('CONTAINER_A', Steel), ('CONTAINER_B', Steel2)):
        root = empty(nm)
        new_obj('cont_body', box(2.44, 6.06, 2.59, loc=(0, 0, 1.3)), m, root, smooth=False)
        for i in range(8):
            for sx in (-1, 1):
                new_obj('rib', box(0.08, 0.2, 2.3, loc=(sx*1.24, -2.6 + i*0.74, 1.3)), m, root, smooth=False)
        new_obj('cont_frame', box(2.6, 0.18, 2.75, loc=(0, 3.06, 1.3)), MATS['Trim'], root, smooth=False)
        new_obj('cont_frame', box(2.6, 0.18, 2.75, loc=(0, -3.06, 1.3)), MATS['Trim'], root, smooth=False)

    # --- floating rock island decor
    root = empty('ROCK')
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    import random
    random.seed(4)
    for v in bm.verts:
        v.co *= 1 + random.uniform(-0.12, 0.12)
        if v.co.z > 0.25: v.co.z = 0.25 + (v.co.z-0.25)*0.15
        else: v.co.z *= 1.7
    new_obj('rock', bm, mat('Rock', srgb('8a7f99'), rough=0.9), root, smooth=False)
    new_obj('grass', cyl(0.97, 0.14, 12, loc=(0, 0, 0.3)), mat('Grass', srgb('7ed957'), rough=0.8), root, smooth=False)

# ---------------------------------------------------------------- main
reset()
materials()
x = 0
for name, P in CARS.items():
    r = build_car(name, P); r.location.x = x; x += 3
build_wheel('WHEEL', 'Rim')
build_wheel('WHEEL_DARK', 'RimDark')
build_wing()
build_props()
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True, export_extras=True)
print('EXPORTED', OUT)
