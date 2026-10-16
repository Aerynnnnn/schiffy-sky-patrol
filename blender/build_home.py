"""
Schiffy Sky Patrol: home isle items (home.glb) for the Edit home catalogue.

Run with Blender's Python module (bpy):  python build_home.py <out_dir>
Writes <out_dir>/home.glb (one root per item: Home_<id>, with a static body mesh and pivoted moving parts) and
<out_dir>/home_parts.json (each item's collision boxes for the game, [cx, cz, hx, hz, y0, y1] in game units).

Everything is modelled in the game's frame (x right, y up, z toward the camera = the item's front) and turned to
Blender's frame (x, -z, y) on export, so the glTF comes back out exactly in game coordinates. Units: Schiffy is about
1.1 tall, the Cosy Doghouse 1.6 wide, a tree 5 tall.

Materials: flat toon colours (the game draws them with MeshToonMaterial). Names starting with Glow become unlit glowing
materials in the game, "Glass" is see-through and "Gold" gets a warm sheen (propMat in index.html). Every other name is
prefixed H so it can't collide with the game's shared material cache.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector, Euler

OUT = sys.argv[-1] if len(sys.argv) > 1 and not sys.argv[-1].endswith('.py') else '.'
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------- materials
def lin(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)

MATS = {}
def mat(name, hexcol):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = lin(hexcol); p.inputs['Roughness'].default_value = 0.85
    if name.startswith('Glow'):
        p.inputs['Emission Color'].default_value = lin(hexcol); p.inputs['Emission Strength'].default_value = 2.0
    if name == 'Glass':
        p.inputs['Alpha'].default_value = 0.3
    MATS[name] = m
    return m

C = dict(
    cream=0xfff4dc, white=0xfffaf0, wood=0xc98a5a, woodL=0xe0a877, woodD=0x8a5a3a, bark=0x6b4a3c, navy=0x26315c, iron=0x3a3554,
    stone=0xddd8ee, stoneD=0xa9a3c4, rock=0x8f89b0, leaf=0x5fbf4f, leafD=0x3f9a3c, leafL=0x8fd96f, pink=0xff8fc0, pinkD=0xe86fa3,
    red=0xe8475a, redD=0xb8323f, yellow=0xffd34d, orange=0xff9a3d, blue=0x5fb8ff, blueD=0x3a7fd0, teal=0x2ec4c6, lilac=0xc9a6ff,
    soil=0x7a4f3a, hay=0xe8c26a, hayD=0xc99a3e, sand=0xf2d9a0, ice=0xbfeaff, iceD=0x8fd3f0, fur=0xfff0e0, mint=0x7fe0c0, slate=0x4a4a6a,
)
def M(key, hexcol=None):
    """material by palette key (H<key>) or by explicit name + colour (Glow..., Glass, Gold)."""
    if hexcol is None: return mat('H' + key[0].upper() + key[1:], C[key])
    return mat(key, hexcol)
GOLD = lambda: mat('Gold', 0xffc53d)
GLASS = lambda: mat('Glass', 0xbfeaff)

# ---------------------------------------------------------------- geometry in the game frame
def xf(at=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    r = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix().to_4x4()
    return Matrix.Translation(Vector(at)) @ r @ Matrix.Diagonal(Vector((*scale, 1)))

class Part:
    """one mesh object: primitives are added into a single bmesh with per-face material slots."""
    def __init__(self, name, pivot=(0, 0, 0)):
        self.name, self.pivot, self.bm, self.mats = name, Vector(pivot), bmesh.new(), []
    def _slot(self, m):
        if m not in self.mats: self.mats.append(m)
        return self.mats.index(m)
    def _merge(self, tmp, m, matrix, smooth):
        bmesh.ops.transform(tmp, matrix=Matrix.Translation(-self.pivot) @ matrix, verts=tmp.verts)
        idx = self._slot(m)
        for f in tmp.faces: f.material_index = idx; f.smooth = smooth
        me = bpy.data.meshes.new('tmp'); tmp.to_mesh(me); tmp.free()
        self.bm.from_mesh(me); bpy.data.meshes.remove(me)
        return self

    def box(self, size, at, m, rot=(0, 0, 0), bevel=0.035):
        t = bmesh.new(); bmesh.ops.create_cube(t, size=1.0)
        bmesh.ops.scale(t, vec=Vector(size), verts=t.verts)
        if bevel > 0: bmesh.ops.bevel(t, geom=list(t.edges), offset=min(bevel, min(size) * 0.3), segments=2, affect='EDGES', profile=0.5)
        return self._merge(t, m, xf(at, rot), False)

    def cyl(self, r, h, at, m, n=14, r2=None, rot=(0, 0, 0), smooth=True, scale=(1, 1, 1)):
        """cylinder (or cone / frustum with r2) along y, centred on at."""
        t = bmesh.new()
        bmesh.ops.create_cone(t, cap_ends=True, cap_tris=False, segments=n, radius1=r, radius2=r if r2 is None else r2, depth=h)
        bmesh.ops.rotate(t, verts=t.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-90), 4, 'X'))   # z axis -> y axis
        return self._merge(t, m, xf(at, rot, scale), smooth)

    def sph(self, r, at, m, scale=(1, 1, 1), seg=14, ring=9, rot=(0, 0, 0), smooth=True):
        t = bmesh.new(); bmesh.ops.create_uvsphere(t, u_segments=seg, v_segments=ring, radius=r)
        return self._merge(t, m, xf(at, rot, scale), smooth)

    def tor(self, R, r, at, m, rot=(0, 0, 0), seg=24, sides=8, arc=1.0, scale=(1, 1, 1)):
        """torus in the xz plane (around y), optionally only part of the ring (arc 0..1)."""
        t = bmesh.new(); verts = []
        n = max(3, int(seg * arc)); closed = arc >= 0.999
        cnt = n if closed else n + 1
        for i in range(cnt):
            a = 2 * math.pi * arc * i / n
            ring = []
            for j in range(sides):
                b = 2 * math.pi * j / sides
                d = R + r * math.cos(b)
                ring.append(t.verts.new((d * math.cos(a), r * math.sin(b), d * math.sin(a))))
            verts.append(ring)
        for i in range(n if closed else cnt - 1):
            a, b = verts[i], verts[(i + 1) % cnt]
            for j in range(sides):
                t.faces.new((a[j], b[j], b[(j + 1) % sides], a[(j + 1) % sides]))
        if not closed:
            t.faces.new(list(reversed(verts[0]))); t.faces.new(verts[-1])
        bmesh.ops.recalc_face_normals(t, faces=t.faces)
        return self._merge(t, m, xf(at, rot, scale), True)

    def poly(self, pts, faces, m, at=(0, 0, 0), rot=(0, 0, 0), smooth=False):
        t = bmesh.new(); vs = [t.verts.new(p) for p in pts]
        for f in faces: t.faces.new([vs[i] for i in f])
        bmesh.ops.recalc_face_normals(t, faces=t.faces)
        return self._merge(t, m, xf(at, rot), smooth)

    def wedge(self, w, h, d, at, m, rot=(0, 0, 0)):
        """triangular prism: a gable along x (base w x d, ridge h above the base)."""
        x, z = w / 2, d / 2
        pts = [(-x, 0, -z), (x, 0, -z), (x, 0, z), (-x, 0, z), (-x, h, 0), (x, h, 0)]
        return self.poly(pts, [(0, 1, 2, 3), (0, 4, 5, 1), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2)], m, at, rot)

    def star(self, r1, r2, depth, at, m, rot=(0, 0, 0), points=5):
        pts, n = [], points * 2
        for k in range(n):
            a = math.pi / 2 + 2 * math.pi * k / n; r = r1 if k % 2 == 0 else r2
            pts += [(r * math.cos(a), r * math.sin(a), -depth / 2), (r * math.cos(a), r * math.sin(a), depth / 2)]
        faces = [tuple(range(0, 2 * n, 2))[::-1], tuple(range(1, 2 * n, 2))]
        for k in range(n):
            a, b = 2 * k, 2 * ((k + 1) % n)
            faces.append((a, b, b + 1, a + 1))
        return self.poly(pts, faces, m, at, rot)

    def bone(self, length, r, at, m, rot=(0, 0, 0)):
        """a cartoon dog bone along x."""
        self.cyl(r, length, at, m, n=10, rot=(rot[0], rot[1], rot[2] + 90))
        e = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix()
        for s in (-1, 1):
            for o in (-1, 1):
                off = e @ Vector((s * length / 2, o * r * 0.9, 0))
                self.sph(r * 1.25, tuple(Vector(at) + off), m, seg=10, ring=7)
        return self

    def paw(self, s, at, m, rot=(0, 0, 0), depth=0.05):
        """a paw print (pad + four toes), flat in the xy plane, facing +z."""
        self.cyl(0.5 * s, depth, at, m, n=14, rot=(90 + rot[0], rot[1], rot[2]), scale=(1.15, 1, 0.95))
        e = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix()
        for dx, dy in ((-0.55, 0.55), (-0.2, 0.85), (0.2, 0.85), (0.55, 0.55)):
            off = e @ Vector((dx * s, dy * s, 0))
            self.cyl(0.2 * s, depth, tuple(Vector(at) + off), m, n=10, rot=(90 + rot[0], rot[1], rot[2]))
        return self

    def to_object(self, parent):
        me = bpy.data.meshes.new(self.name)
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=0.0005)
        # game frame -> Blender frame in the mesh data itself (the game resets a model root's rotation when it clones it)
        bmesh.ops.transform(self.bm, matrix=TO_BLENDER, verts=self.bm.verts)
        self.bm.to_mesh(me); self.bm.free()
        for m in self.mats: me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = parent; ob.location = TO_BLENDER @ self.pivot
        return ob

# ---------------------------------------------------------------- items
TO_BLENDER = Matrix.Rotation(math.radians(90), 4, 'X')   # (x, y, z) -> (x, -z, y)
ITEMS, PARTS = {}, {}
def item(iid, parts):
    """decorator: fn(B, P) fills B (static body) and may add moving parts via P(name, pivot)."""
    def deco(fn):
        ITEMS[iid] = fn; PARTS[iid] = parts; return fn
    return deco

def picket(B, x, z, h, m, w=0.18):
    B.box((w, h, 0.07), (x, h / 2, z), m, bevel=0.02)
    B.poly([(-w / 2, 0, -0.035), (w / 2, 0, -0.035), (w / 2, 0, 0.035), (-w / 2, 0, 0.035), (0, w * 0.7, -0.035), (0, w * 0.7, 0.035)],
           [(0, 1, 2, 3), (0, 4, 5, 3)[::-1], (1, 2, 5, 4)[::-1], (0, 1, 4), (3, 5, 2)], m, at=(x, h, z))

# ============================== GOLD: everyday furniture and garden =========================
@item('fence', [[0, 0, 1.58, 0.12, 0, 1.15]])
def _(B, P):
    for i in range(9):
        picket(B, -1.4 + i * 0.35, 0.03, 0.95, M('cream'))
    for y in (0.3, 0.72):
        B.box((3.1, 0.1, 0.07), (0, y, -0.04), M('cream'), bevel=0.02)
    for x in (-1.55, 1.55):
        B.box((0.16, 1.08, 0.16), (x, 0.54, -0.01), M('woodL'))
        B.sph(0.1, (x, 1.12, -0.01), GOLD(), seg=10, ring=7)

@item('path', [[0, 0, 1.05, 1.05, 0, 0.14]])
def _(B, P):
    for (x, z, r, a) in ((-0.5, -0.45, 0.48, 10), (0.52, -0.3, 0.42, 40), (-0.25, 0.55, 0.44, 70), (0.6, 0.62, 0.3, 20)):
        B.cyl(r, 0.12, (x, 0.06, z), M('stone'), n=9, scale=(1.15, 1, 0.9), rot=(0, a, 0), smooth=False)
        B.cyl(r * 0.55, 0.02, (x - r * 0.15, 0.125, z - r * 0.1), M('stoneD'), n=7, rot=(0, a + 20, 0), smooth=False)
    for (x, z) in ((0.1, 0.05), (-0.85, 0.15), (0.9, 0.1)):
        B.sph(0.09, (x, 0.04, z), M('leafL'), scale=(1, 0.6, 1), seg=8, ring=5)

@item('bench', [[0, 0, 0.98, 0.36, 0, 1.05]])
def _(B, P):
    for i, z in enumerate((-0.15, 0.0, 0.15)):
        B.box((1.8, 0.07, 0.13), (0, 0.48, z + 0.02), M('woodL' if i % 2 else 'wood'), bevel=0.02)
    for i, y in enumerate((0.72, 0.9)):
        B.box((1.8, 0.12, 0.06), (0, y, -0.25), M('wood' if i else 'woodL'), rot=(-12, 0, 0), bevel=0.02)
    for x in (-0.85, 0.85):
        B.box((0.08, 0.48, 0.08), (x, 0.24, 0.17), M('iron'), bevel=0.02)
        B.box((0.08, 1.0, 0.08), (x, 0.5, -0.24), M('iron'), rot=(-8, 0, 0), bevel=0.02)
        B.tor(0.17, 0.035, (x, 0.62, -0.02), M('iron'), rot=(90, 90, 0), arc=0.5)
        B.box((0.1, 0.05, 0.5), (x, 0.66, -0.04), M('iron'), bevel=0.015)
    B.paw(0.12, (0, 0.82, -0.215), GOLD(), rot=(-12, 0, 0), depth=0.02)

@item('lamp', [[0, 0, 0.32, 0.32, 0, 3.15]])
def _(B, P):
    B.cyl(0.3, 0.14, (0, 0.07, 0), M('iron'), n=12)
    B.cyl(0.18, 0.22, (0, 0.24, 0), M('iron'), n=12, r2=0.1)
    B.cyl(0.07, 2.25, (0, 1.45, 0), M('iron'), n=10)
    B.tor(0.1, 0.03, (0, 1.0, 0), GOLD(), seg=16)
    B.cyl(0.16, 0.08, (0, 2.6, 0), M('iron'), n=8)
    for x in (-0.15, 0.15):
        for z in (-0.15, 0.15):
            B.box((0.03, 0.42, 0.03), (x, 2.85, z), M('iron'), bevel=0.0)
    B.box((0.27, 0.38, 0.27), (0, 2.85, 0), mat('GlowHLamp', 0xffe0a0), bevel=0.02)
    B.cyl(0.26, 0.24, (0, 3.18, 0), M('iron'), n=4, r2=0.02, rot=(0, 45, 0), smooth=False)
    B.sph(0.05, (0, 3.33, 0), GOLD(), seg=8, ring=6)

@item('planter', [[0, 0, 0.78, 0.33, 0, 1.0]])
def _(B, P):
    B.box((1.5, 0.5, 0.56), (0, 0.27, 0), M('wood'))
    for x in (-0.5, 0, 0.5):
        B.box((0.04, 0.42, 0.02), (x, 0.27, 0.285), M('woodD'), bevel=0.0)
    B.box((1.38, 0.05, 0.44), (0, 0.5, 0), M('soil'), bevel=0.01)
    cols = [M('pink'), M('yellow'), mat('HPetalBlue', 0x9fd3ff), M('white'), M('red'), M('lilac')]
    for i in range(7):
        x = -0.6 + i * 0.2; z = 0.08 if i % 2 else -0.08; h = 0.3 + 0.12 * ((i * 7) % 3)
        B.cyl(0.018, h, (x, 0.5 + h / 2, z), M('leafD'), n=6)
        B.sph(0.06, (x + 0.05, 0.5 + h * 0.45, z), M('leaf'), scale=(1.4, 0.5, 0.8), seg=8, ring=5)
        c = cols[i % len(cols)]
        for k in range(5):
            a = 2 * math.pi * k / 5
            B.sph(0.06, (x + 0.07 * math.cos(a), 0.52 + h, z + 0.07 * math.sin(a)), c, scale=(1, 0.45, 1), seg=8, ring=5)
        B.sph(0.04, (x, 0.54 + h, z), M('yellow') if c is not M('yellow') else M('orange'), seg=8, ring=5)

@item('mailbox', [[0, 0, 0.3, 0.42, 0, 1.55]])
def _(B, P):
    B.box((0.12, 1.0, 0.12), (0, 0.5, 0), M('woodD'))
    B.box((0.3, 0.06, 0.6), (0, 1.0, 0), M('woodD'), bevel=0.02)
    B.box((0.38, 0.3, 0.7), (0, 1.18, 0), M('blue'), bevel=0.04)
    B.cyl(0.19, 0.7, (0, 1.33, 0), M('blue'), n=16, rot=(90, 0, 0))
    B.cyl(0.2, 0.04, (0, 1.24, 0.36), M('blueD'), n=16, rot=(90, 0, 0), scale=(1, 1, 1))
    B.box((0.4, 0.15, 0.04), (0, 1.12, 0.37), M('blueD'), bevel=0.01)
    B.sph(0.035, (0, 1.24, 0.39), GOLD(), seg=8, ring=6)
    B.box((0.03, 0.42, 0.04), (0.21, 1.42, -0.15), M('iron'), bevel=0.0)
    B.box((0.03, 0.18, 0.24), (0.21, 1.56, -0.04), M('red'), bevel=0.01)
    B.paw(0.12, (0.0, 1.34, 0.375), M('white'), depth=0.015)
    for z in (-0.12, 0.12):
        B.sph(0.07, (0.05, 0.12, z), M('leafL'), scale=(1, 0.8, 1), seg=8, ring=5)

@item('birdbath', [[0, 0, 0.62, 0.62, 0, 1.25]])
def _(B, P):
    B.cyl(0.4, 0.12, (0, 0.06, 0), M('stone'), n=12)
    B.cyl(0.3, 0.12, (0, 0.18, 0), M('stoneD'), n=12)
    B.cyl(0.12, 0.62, (0, 0.55, 0), M('stone'), n=10, r2=0.16)
    B.cyl(0.6, 0.16, (0, 0.92, 0), M('stone'), n=16, r2=0.62)
    B.cyl(0.18, 0.06, (0, 0.85, 0), M('stoneD'), n=12, r2=0.5)
    B.cyl(0.54, 0.03, (0, 1.0, 0), mat('GlowHWater', 0x9fe8ff), n=16)
    # a little blue bird on the rim
    B.sph(0.11, (0.42, 1.12, 0.1), M('blue'), scale=(1.2, 1, 1), seg=10, ring=7)
    B.sph(0.08, (0.5, 1.22, 0.12), M('blue'), seg=10, ring=7)
    B.cyl(0.03, 0.08, (0.59, 1.22, 0.12), M('orange'), n=6, r2=0.0, rot=(0, 0, -90))
    B.sph(0.016, (0.55, 1.25, 0.18), M('navy'), seg=6, ring=4)
    B.box((0.12, 0.03, 0.1), (0.3, 1.16, 0.1), M('blueD'), rot=(0, 0, 25), bevel=0.0)

@item('campfire', [[0, 0, 0.62, 0.62, 0, 0.45], [-1.45, 0, 0.32, 0.62, 0, 0.5], [1.45, 0, 0.32, 0.62, 0, 0.5]])
def _(B, P):
    for k in range(9):
        a = 2 * math.pi * k / 9
        B.sph(0.16, (0.48 * math.cos(a), 0.1, 0.48 * math.sin(a)), M('stoneD' if k % 2 else 'stone'), scale=(1, 0.7, 1), seg=8, ring=6, smooth=False)
    B.cyl(0.36, 0.03, (0, 0.02, 0), mat('HAsh', 0x5a4a5a), n=12)
    for a in (0, 60, 120):
        B.cyl(0.06, 0.62, (0, 0.13, 0), M('bark'), n=8, rot=(0, a, 75))
    for s in (-1, 1):
        B.cyl(0.24, 1.2, (s * 1.45, 0.24, 0), M('bark'), n=12, rot=(90, 0, 0))
        B.cyl(0.2, 0.02, (s * 1.45, 0.24, 0.6), M('woodL'), n=12, rot=(90, 0, 0))
        B.cyl(0.2, 0.02, (s * 1.45, 0.24, -0.6), M('woodL'), n=12, rot=(90, 0, 0))
    # the fire: a ring of leaning orange tongues round a tall yellow core, an ember glow under it (flickers in game)
    F = P('flame', (0, 0.1, 0))
    fire, core = mat('GlowHFire', 0xff7a2e), mat('GlowHFireCore', 0xffd84d)
    F.cyl(0.3, 0.05, (0, 0.12, 0), mat('GlowHEmber', 0xff5a3d), n=10)
    for k in range(6):
        a = 2 * math.pi * k / 6; h = 0.55 + 0.2 * ((k * 3) % 2)
        F.cyl(0.13, h, (0.15 * math.cos(a), 0.12 + h / 2, 0.15 * math.sin(a)), fire, n=6, r2=0.0, smooth=False,
              rot=(18 * math.sin(a), 0, -18 * math.cos(a)))
    F.cyl(0.17, 0.95, (0, 0.55, 0), core, n=7, r2=0.0, smooth=False)
    F.cyl(0.09, 0.5, (0.08, 0.35, 0.08), mat('GlowHFireTip', 0xfff3b0), n=6, r2=0.0, smooth=False)

@item('hydrant', [[0, 0, 0.36, 0.36, 0, 1.0]])
def _(B, P):
    B.cyl(0.3, 0.1, (0, 0.05, 0), M('redD'), n=12)
    B.cyl(0.22, 0.6, (0, 0.4, 0), M('red'), n=14)
    B.tor(0.22, 0.04, (0, 0.68, 0), M('redD'))
    B.sph(0.22, (0, 0.74, 0), M('red'), scale=(1, 0.75, 1), seg=14, ring=8)
    B.cyl(0.07, 0.12, (0, 0.92, 0), GOLD(), n=6)
    for s in (-1, 1):
        B.cyl(0.08, 0.16, (s * 0.27, 0.48, 0), M('redD'), n=10, rot=(0, 0, 90))
        B.cyl(0.09, 0.05, (s * 0.36, 0.48, 0), GOLD(), n=6, rot=(0, 0, 90))
    B.cyl(0.1, 0.12, (0, 0.44, 0.25), M('redD'), n=10, rot=(90, 0, 0))
    B.cyl(0.11, 0.05, (0, 0.44, 0.32), GOLD(), n=6, rot=(90, 0, 0))

@item('toybox', [[0, 0, 0.62, 0.42, 0, 0.95]])
def _(B, P):
    B.box((1.15, 0.55, 0.7), (0, 0.29, 0), M('red'))
    for x in (-0.57, 0.57):
        B.box((0.06, 0.58, 0.74), (x, 0.29, 0), M('yellow'), bevel=0.02)
    B.box((1.17, 0.06, 0.74), (0, 0.05, 0), M('yellow'), bevel=0.02)
    B.star(0.12, 0.05, 0.03, (0, 0.3, 0.36), M('yellow'))
    B.box((1.15, 0.08, 0.7), (0, 0.78, -0.48), M('blue'), rot=(-70, 0, 0))   # the lid propped open
    B.sph(0.16, (-0.25, 0.6, 0.0), mat('HTennis', 0xd8f04a), seg=12, ring=8)
    B.sph(0.18, (0.22, 0.62, -0.08), M('pink'), seg=12, ring=8)
    B.bone(0.4, 0.05, (0.05, 0.66, 0.18), M('white'), rot=(0, 25, 30))
    B.box((0.22, 0.22, 0.22), (-0.32, 0.6, -0.15), M('teal'), rot=(10, 30, 0), bevel=0.05)

@item('hay', [[0, 0, 0.66, 0.4, 0, 0.75]])
def _(B, P):
    B.box((1.25, 0.7, 0.75), (0, 0.35, 0), M('hay'), bevel=0.08)
    for x in (-0.32, 0.32):
        B.box((0.05, 0.72, 0.77), (x, 0.35, 0), mat('HTwine', 0xa8462e), bevel=0.01)
    for k in range(10):
        x = -0.55 + (k * 0.127); z = 0.36 if k % 2 else -0.36
        B.cyl(0.012, 0.14, (x, 0.72, z * 0.9), M('hayD'), n=4, rot=(25 * (1 if k % 3 else -1), 0, 15), smooth=False)

@item('picnic', [[0, 0, 0.95, 0.42, 0, 0.82], [0, 0.72, 0.95, 0.2, 0, 0.5], [0, -0.72, 0.95, 0.2, 0, 0.5]])
def _(B, P):
    for i, z in enumerate((-0.27, -0.09, 0.09, 0.27)):
        B.box((1.8, 0.07, 0.17), (0, 0.78, z), M('woodL' if i % 2 else 'wood'), bevel=0.02)
    for s in (-1, 1):
        B.box((1.8, 0.06, 0.32), (0, 0.45, s * 0.72), M('wood'), bevel=0.02)
        for x in (-0.7, 0.7):
            B.box((0.08, 0.9, 0.08), (x, 0.42, s * 0.22), M('woodD'), rot=(s * 30, 0, 0), bevel=0.02)
    for x in (-0.7, 0.7):
        B.box((0.08, 0.06, 1.6), (x, 0.4, 0), M('woodD'), bevel=0.02)
    # a checked cloth runner, a jug and a cake
    for i in range(6):
        B.box((0.25, 0.012, 0.5), (-0.62 + i * 0.25, 0.82, 0), M('red') if i % 2 else M('white'), bevel=0.0)
    B.cyl(0.09, 0.22, (0.45, 0.94, 0.05), mat('HJug', 0xffe9a8), n=12)
    B.cyl(0.17, 0.12, (-0.35, 0.89, 0), M('pink'), n=16)
    B.sph(0.04, (-0.35, 0.98, 0), M('red'), seg=8, ring=6)

@item('veggies', [[0, 0, 1.08, 0.78, 0, 0.65]])
def _(B, P):
    B.box((2.1, 0.22, 1.5), (0, 0.11, 0), M('woodD'), bevel=0.04)
    B.box((1.95, 0.06, 1.35), (0, 0.22, 0), M('soil'), bevel=0.02)
    for i in range(5):    # carrots
        x = -0.75 + i * 0.36
        B.cyl(0.06, 0.12, (x, 0.24, -0.42), M('orange'), n=8, r2=0.03)
        for a in (-20, 0, 20):
            B.cyl(0.015, 0.22, (x, 0.36, -0.42), M('leaf'), n=4, rot=(a, 0, a * 0.5), smooth=False)
    for i in range(4):    # cabbages
        x = -0.72 + i * 0.48
        B.sph(0.16, (x, 0.32, 0.02), M('leafL'), seg=12, ring=8)
        B.sph(0.12, (x, 0.36, 0.02), M('leaf'), scale=(1, 0.8, 1), seg=10, ring=6)
    for x in (-0.45, 0.4):    # pumpkins
        for k in range(6):
            a = 2 * math.pi * k / 6
            B.sph(0.12, (x + 0.1 * math.cos(a), 0.36, 0.45 + 0.1 * math.sin(a)), M('orange'), scale=(1, 1.1, 1), seg=10, ring=7)
        B.cyl(0.025, 0.1, (x, 0.53, 0.45), M('leafD'), n=6)
    # a little scarecrow sign post
    B.box((0.06, 0.7, 0.06), (0.95, 0.5, 0.6), M('woodD'))
    B.box((0.4, 0.22, 0.04), (0.95, 0.8, 0.63), M('cream'), bevel=0.02)
    B.paw(0.07, (0.95, 0.8, 0.655), M('leafD'), depth=0.01)

@item('swing', [[-1.25, 0, 0.22, 0.62, 0, 2.6], [1.25, 0, 0.22, 0.62, 0, 2.6], [0, 0, 1.45, 0.16, 2.35, 2.7], [0, 0, 0.45, 0.22, 0.35, 1.25]])
def _(B, P):
    for s in (-1, 1):
        for z in (-1, 1):
            B.box((0.12, 2.65, 0.12), (s * 1.25, 1.27, z * 0.38), M('wood'), rot=(z * 12, 0, 0), bevel=0.02)
        B.box((0.08, 0.08, 0.75), (s * 1.25, 0.9, 0), M('woodD'), bevel=0.02)
    B.cyl(0.1, 2.75, (0, 2.55, 0), M('woodL'), n=10, rot=(0, 0, 90))
    T = P('tyre', (0, 2.5, 0))
    for x in (-0.25, 0.25):
        T.cyl(0.02, 1.55, (x * 0.6, 1.72, 0), mat('HRope', 0xe8d8b0), n=5, rot=(0, 0, x * -12))
    T.tor(0.32, 0.12, (0, 0.82, 0), mat('HTyre', 0x3a3554), rot=(90, 0, 0), seg=20, sides=8)

# ============================== PAW GEMS: showpiece buildings ===============================
@item('cottage', [[0, 0, 2.25, 1.75, 0, 2.6], [0, 0, 2.55, 2.0, 2.6, 4.6], [1.25, -0.55, 0.3, 0.3, 3.4, 5.1], [0, 1.95, 0.55, 0.3, 0, 0.2]])
def _(B, P):
    B.box((4.4, 0.25, 3.4), (0, 0.12, 0), M('stoneD'), bevel=0.05)
    B.box((4.2, 2.4, 3.2), (0, 1.4, 0), M('cream'), bevel=0.06)
    for x in (-2.08, 2.08):
        for z in (-1.58, 1.58):
            B.box((0.18, 2.45, 0.18), (x, 1.4, z), M('woodD'), bevel=0.03)
    B.box((4.3, 0.16, 0.12), (0, 2.6, 1.6), M('woodD'), bevel=0.03)
    # the roof: two pink slabs, a ridge and gable ends
    for s in (-1, 1):
        B.box((4.9, 0.16, 2.35), (0, 3.55, s * 0.95), M('pink'), rot=(s * 40, 0, 0), bevel=0.04)
    B.cyl(0.11, 4.95, (0, 4.32, 0), M('pinkD'), n=10, rot=(0, 0, 90))
    for x in (-2.1, 2.1):
        B.wedge(0.12, 1.5, 3.1, (x, 2.62, 0), M('cream'), rot=(0, 90, 0))
    B.box((0.55, 1.5, 0.55), (1.25, 4.25, -0.55), M('stone'), bevel=0.04)
    B.box((0.66, 0.14, 0.66), (1.25, 5.03, -0.55), M('stoneD'), bevel=0.03)
    # door, step, round window, flower boxes, paw sign
    B.box((0.95, 1.55, 0.08), (0, 0.98, 1.62), M('navy'), bevel=0.03)
    B.cyl(0.475, 0.08, (0, 1.74, 1.62), M('navy'), n=16, rot=(90, 0, 0), scale=(1, 1, 1))
    B.sph(0.06, (0.3, 0.98, 1.68), GOLD(), seg=8, ring=6)
    B.box((1.2, 0.16, 0.5), (0, 0.08, 1.92), M('stone'), bevel=0.03)
    for x in (-1.35, 1.35):
        B.cyl(0.45, 0.06, (x, 1.55, 1.61), GLASS(), n=18, rot=(90, 0, 0))
        B.tor(0.45, 0.06, (x, 1.55, 1.62), M('woodD'), rot=(90, 0, 0), seg=20, sides=6)
        B.box((0.9, 0.05, 0.05), (x, 1.55, 1.66), M('woodD'), bevel=0.0)
        B.box((0.05, 0.9, 0.05), (x, 1.55, 1.66), M('woodD'), bevel=0.0)
        B.box((1.0, 0.2, 0.28), (x, 1.0, 1.72), M('wood'), bevel=0.03)
        for k in range(5):
            B.sph(0.09, (x - 0.38 + k * 0.19, 1.15, 1.74), [M('pink'), M('yellow'), M('white'), M('red'), M('lilac')][k], seg=8, ring=6)
    B.box((0.9, 0.5, 0.06), (0, 2.85, 1.72), M('woodL'), bevel=0.03)
    B.paw(0.15, (0, 2.85, 1.76), M('pinkD'), depth=0.02)
    B.cyl(0.32, 0.08, (-1.3, 3.55, 1.75), M('cream'), n=16, rot=(50, 0, 0))   # attic porthole
    B.cyl(0.24, 0.1, (-1.3, 3.55, 1.76), mat('GlowHWindow', 0xffe0a0), n=16, rot=(50, 0, 0))

@item('treehouse', [[0, 0, 0.62, 0.62, 0, 2.6], [0, 0, 1.65, 1.65, 2.45, 2.75], [0, 0, 1.0, 0.9, 2.75, 4.9], [0, 0, 2.1, 2.1, 4.9, 6.9], [0, 1.85, 0.42, 0.18, 0, 2.6]])
def _(B, P):
    B.cyl(0.55, 3.2, (0, 1.6, 0), M('bark'), n=10, r2=0.42)
    for a in range(0, 360, 72):
        B.cyl(0.18, 0.9, (0.5 * math.cos(math.radians(a)), 0.25, 0.5 * math.sin(math.radians(a))), M('bark'), n=6, r2=0.05, rot=(0, -a, 60))
    B.box((3.3, 0.22, 3.3), (0, 2.6, 0), M('wood'), bevel=0.04)
    for s in (-1, 1):
        for t in (-1, 1):
            B.box((0.12, 2.5, 0.12), (s * 1.4, 1.35, t * 1.4), M('woodD'), rot=(t * 6, 0, -s * 6), bevel=0.02)
    for k in range(-6, 7):   # railing on three sides
        B.box((0.06, 0.55, 0.06), (k * 0.25, 2.98, -1.6), M('woodL'), bevel=0.0)
        if abs(k) <= 6:
            B.box((0.06, 0.55, 0.06), (-1.6, 2.98, k * 0.25), M('woodL'), bevel=0.0)
            B.box((0.06, 0.55, 0.06), (1.6, 2.98, k * 0.25), M('woodL'), bevel=0.0)
    for (x, z, ry) in ((0, -1.6, 0), (-1.6, 0, 90), (1.6, 0, 90)):
        B.box((3.25, 0.08, 0.1), (x, 3.25, z), M('woodD'), rot=(0, ry, 0), bevel=0.02)
    # the hut
    B.box((1.9, 1.6, 1.7), (0, 3.52, -0.15), M('woodL'), bevel=0.05)
    for y in (3.0, 3.4, 3.8, 4.2):
        B.box((1.95, 0.04, 1.75), (0, y, -0.15), M('wood'), bevel=0.0)
    B.box((0.7, 1.05, 0.06), (0, 3.25, 0.72), M('navy'), bevel=0.02)
    B.cyl(0.35, 0.06, (0, 3.78, 0.72), M('navy'), n=12, rot=(90, 0, 0))
    for s in (-1, 1):
        B.box((2.3, 0.12, 1.3), (0, 4.65, -0.15 + s * 0.55), M('red'), rot=(s * 35, 0, 0), bevel=0.03)
    B.box((0.28, 0.24, 0.05), (0.6, 3.8, 0.73), GLASS(), bevel=0.0)
    B.box((0.5, 0.25, 0.05), (0, 4.28, 0.68), M('cream'), bevel=0.02)
    # the ladder
    for x in (-0.3, 0.3):
        B.box((0.08, 2.75, 0.08), (x, 1.32, 1.85), M('woodD'), rot=(12, 0, 0), bevel=0.02)
    for k in range(7):
        B.cyl(0.035, 0.6, (0, 0.25 + k * 0.36, 1.92 - k * 0.075), M('woodL'), n=6, rot=(0, 0, 90))
    # canopy and a few apples
    for (x, y, z, r) in ((0, 5.9, -0.4, 1.4), (-1.1, 5.4, 0.3, 1.0), (1.1, 5.5, 0.2, 1.05), (0.2, 6.3, 0.6, 0.95), (-0.5, 5.6, -1.3, 0.95), (0.9, 5.7, -1.1, 0.9)):
        B.sph(r, (x, y, z), M('leaf') if r > 1 else M('leafL'), seg=12, ring=8)
    for (x, y, z) in ((-1.0, 5.0, 1.0), (1.4, 5.1, 0.9), (0.4, 6.0, 1.45)):
        B.sph(0.12, (x, y, z), M('red'), seg=8, ring=6)

@item('windmill', [[0, 0, 1.35, 1.35, 0, 4.6], [0, 0, 1.05, 1.05, 4.6, 5.9], [0, 1.5, 0.45, 0.35, 3.6, 4.8]])
def _(B, P):
    B.cyl(1.4, 0.3, (0, 0.15, 0), M('stoneD'), n=8, smooth=False)
    B.cyl(1.25, 4.3, (0, 2.45, 0), M('cream'), n=8, r2=0.85, smooth=False)
    for y in (1.6, 3.2):
        B.cyl(1.25 - (y / 4.3) * 0.4 + 0.04, 0.12, (0, y, 0), M('woodD'), n=8, smooth=False)
    B.cyl(1.0, 1.4, (0, 5.25, 0), M('red'), n=8, r2=0.05, smooth=False)
    B.cyl(0.92, 0.14, (0, 4.6, 0), M('woodD'), n=8, smooth=False)
    B.box((0.8, 1.3, 0.1), (0, 0.95, 1.18), M('navy'), rot=(-5, 0, 0), bevel=0.03)
    B.cyl(0.4, 0.1, (0, 1.6, 1.15), M('navy'), n=12, rot=(85, 0, 0))
    for (y, x) in ((2.4, 0), (3.6, 0.3)):
        B.box((0.36, 0.44, 0.08), (x, y, 1.0 - (y - 2) * 0.09), GLASS(), rot=(-5, 0, 0), bevel=0.02)
        B.box((0.44, 0.06, 0.1), (x, y - 0.25, 1.02 - (y - 2) * 0.09), M('woodD'), rot=(-5, 0, 0), bevel=0.0)
    B.cyl(0.28, 0.5, (0, 4.2, 1.0), M('woodD'), n=10, rot=(90, 0, 0))
    S = P('sails', (0, 4.2, 1.35))
    S.sph(0.22, (0, 4.2, 1.35), GOLD(), seg=10, ring=7)
    for k in range(4):
        a = k * 90
        r = Euler((0, 0, math.radians(a)), 'XYZ').to_matrix()
        arm = r @ Vector((0, 1.25, 0))
        S.box((0.12, 2.5, 0.08), tuple(Vector((0, 4.2, 1.42)) + arm), M('woodD'), rot=(0, 0, a), bevel=0.02)
        for j in range(5):
            o = r @ Vector((0.28, 0.55 + j * 0.4, 0))
            S.box((0.42, 0.06, 0.04), tuple(Vector((0, 4.2, 1.45)) + o), M('woodL'), rot=(0, 0, a), bevel=0.0)
        o = r @ Vector((0.3, 1.38, 0))
        S.box((0.46, 1.7, 0.03), tuple(Vector((0, 4.2, 1.5)) + o), M('white'), rot=(0, 0, a), bevel=0.0)

@item('lighthouse', [[0, 0, 1.15, 1.15, 0, 6.3], [0, 0, 0.95, 0.95, 6.3, 8.4]])
def _(B, P):
    B.cyl(1.35, 0.4, (0, 0.2, 0), M('stoneD'), n=12)
    for i in range(6):
        y0 = 0.4 + i; r0 = 1.1 - i * 0.065
        B.cyl(r0, 1.0, (0, y0 + 0.5, 0), M('red') if i % 2 == 0 else M('white'), n=16, r2=r0 - 0.065)
    B.cyl(1.0, 0.18, (0, 6.45, 0), M('navy'), n=16)
    for k in range(16):
        a = 2 * math.pi * k / 16
        B.cyl(0.025, 0.45, (0.95 * math.cos(a), 6.75, 0.95 * math.sin(a)), M('navy'), n=5)
    B.tor(0.95, 0.03, (0, 6.98, 0), M('navy'), seg=24, sides=5)
    B.cyl(0.58, 1.05, (0, 7.06, 0), GLASS(), n=12)
    for k in range(6):
        a = 2 * math.pi * k / 6
        B.box((0.05, 1.05, 0.05), (0.58 * math.cos(a), 7.06, 0.58 * math.sin(a)), M('navy'), bevel=0.0)
    B.cyl(0.7, 0.75, (0, 7.95, 0), M('red'), n=12, r2=0.06)
    B.sph(0.1, (0, 8.35, 0), GOLD(), seg=8, ring=6)
    B.box((0.7, 1.15, 0.1), (0, 0.98, 1.08), M('navy'), rot=(-3, 0, 0), bevel=0.03)
    B.cyl(0.35, 0.1, (0, 1.55, 1.07), M('navy'), n=12, rot=(87, 0, 0))
    B.box((0.32, 0.4, 0.08), (0, 3.4, 0.93), GLASS(), rot=(-4, 0, 0), bevel=0.02)
    L = P('beam', (0, 7.06, 0))
    L.sph(0.3, (0, 7.06, 0), mat('GlowHBeacon', 0xfff0a0), seg=12, ring=8)
    for s in (-1, 1):
        L.cyl(0.24, 0.5, (s * 0.32, 7.06, 0), mat('GlowHBeacon', 0xfff0a0), n=10, r2=0.06, rot=(0, 0, s * 90))

@item('balloon', [[0, 0, 0.55, 0.55, 0, 0.85], [0, 0, 1.75, 1.75, 1.7, 5.6]])
def _(B, P):
    B.box((0.95, 0.72, 0.95), (0, 0.36, 0), mat('HWicker', 0xc9955a), bevel=0.08)
    for y in (0.2, 0.45):
        B.box((0.98, 0.05, 0.98), (0, y, 0), mat('HWickerD', 0x9a6a3a), bevel=0.02)
    B.tor(0.5, 0.05, (0, 0.74, 0), mat('HWickerD', 0x9a6a3a), seg=4, sides=6, rot=(0, 45, 0), scale=(1.35, 1, 1.35))
    for s in (-1, 1):
        B.cyl(0.1, 0.25, (s * 0.52, 0.45, 0.2), mat('HSandbag', 0xd9c9a0), n=8)
    # pegs and slack ropes holding it down
    for (x, z) in ((-1.1, 0.9), (1.1, -0.9)):
        B.cyl(0.04, 0.3, (x, 0.12, z), M('woodD'), n=6)
    Bd = P('envelope', (0, 0, 0))
    for (x, z) in ((-0.42, -0.42), (0.42, -0.42), (0.42, 0.42), (-0.42, 0.42)):
        Bd.cyl(0.018, 1.2, (x * 1.4, 1.32, z * 1.4), mat('HRope', 0xe8d8b0), n=4, rot=(z * -25, 0, x * 25))
    Bd.cyl(0.42, 0.22, (0, 1.85, 0), mat('HBurner', 0x3a3554), n=10)
    Bd.cyl(0.12, 0.25, (0, 1.75, 0), mat('GlowHFire', 0xff8a3d), n=6, r2=0.0, smooth=False, rot=(180, 0, 0))
    # the envelope: 12 gores in alternating colours, a teardrop narrowing to the mouth
    cols = [M('pink'), M('yellow'), M('teal'), M('cream')]
    n, rings = 12, 10
    for g in range(n):
        pts, faces = [], []
        for i in range(rings + 1):
            t = i / rings; y = 1.9 + t * 3.6
            # a teardrop: widening from the mouth to the waist, then a rounded dome closing at the top
            if t < 0.45: r = 0.42 + (1.75 - 0.42) * math.sin(t / 0.45 * math.pi / 2) ** 1.1
            else: u = (t - 0.45) / 0.55; r = 1.75 * math.sqrt(max(0.0, 1 - u * u))
            for j in (0, 1):
                a = 2 * math.pi * (g + j) / n
                pts.append((r * math.cos(a), y, r * math.sin(a)))
        for i in range(rings):
            faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
        Bd.poly(pts, faces, cols[g % len(cols)], smooth=True)
    Bd.cyl(0.25, 0.1, (0, 5.52, 0), cols[1], n=12)
    Bd.paw(0.35, (0, 3.9, 1.79), M('white'), rot=(0, 0, 0), depth=0.03)

@item('gazebo', [[1.07, 1.85, 0.16, 0.16, 0, 2.7], [2.14, 0, 0.16, 0.16, 0, 2.7], [1.07, -1.85, 0.16, 0.16, 0, 2.7], [-1.07, -1.85, 0.16, 0.16, 0, 2.7], [-2.14, 0, 0.16, 0.16, 0, 2.7], [-1.07, 1.85, 0.16, 0.16, 0, 2.7], [0, 0, 2.4, 2.4, 2.6, 4.4]])
def _(B, P):
    # a hexagon with a flat side to the front (create_cone's corners sit at these same angles), open at the front
    B.cyl(2.35, 0.12, (0, 0.06, 0), M('stone'), n=6, smooth=False)
    B.cyl(2.15, 0.06, (0, 0.13, 0), M('woodL'), n=6, smooth=False)
    posts = [(2.14 * math.sin(math.radians(a)), 2.14 * math.cos(math.radians(a))) for a in range(30, 390, 60)]
    for (x, z) in posts:
        B.cyl(0.11, 2.55, (x, 1.35, z), M('white'), n=8)
        B.cyl(0.16, 0.14, (x, 2.62, z), M('white'), n=8)
    for k in range(6):
        (x0, z0), (x1, z1) = posts[k], posts[(k + 1) % 6]
        mx, mz = (x0 + x1) / 2, (z0 + z1) / 2; ang = math.degrees(math.atan2(z1 - z0, x1 - x0))
        B.box((2.1, 0.12, 0.12), (mx, 2.62, mz), M('white'), rot=(0, -ang, 0), bevel=0.02)
        if k != 5:   # leave the front open
            B.box((2.0, 0.08, 0.08), (mx, 0.85, mz), M('white'), rot=(0, -ang, 0), bevel=0.02)
            for j in (-0.6, -0.3, 0, 0.3, 0.6):
                B.box((0.05, 0.7, 0.05), (mx + (x1 - x0) * j / 2.14, 0.5, mz + (z1 - z0) * j / 2.14), M('white'), bevel=0.0)
        B.tor(0.45, 0.04, (mx, 2.62, mz), M('leafD'), rot=(90, -ang, 0), arc=0.5, seg=16, sides=5)
    B.cyl(2.5, 1.5, (0, 3.45, 0), mat('HMintRoof', 0x7fd0b0), n=6, r2=0.12, smooth=False)
    B.cyl(2.52, 0.14, (0, 2.75, 0), M('white'), n=6, smooth=False)
    B.sph(0.14, (0, 4.3, 0), GOLD(), seg=10, ring=7)
    for k in range(10):    # hanging flowers round the eaves
        a = 2 * math.pi * k / 10
        B.sph(0.11, (2.3 * math.cos(a), 2.5, 2.3 * math.sin(a)), [M('pink'), M('white')][k % 2], seg=8, ring=6)

@item('hotspring', [[0, 0, 1.9, 1.5, 0, 0.6]])
def _(B, P):
    pts = [(1.75 * math.cos(2 * math.pi * k / 16), 1.35 * math.sin(2 * math.pi * k / 16)) for k in range(16)]
    for k, (x, z) in enumerate(pts):
        B.sph(0.32 + 0.06 * ((k * 5) % 3), (x, 0.24, z), M('rock') if k % 3 else M('stoneD'), scale=(1.1, 0.8, 1), seg=8, ring=6, smooth=False)
    B.cyl(1.6, 0.06, (0, 0.3, 0), mat('GlowHSpring', 0x3fc8c8), n=24, scale=(1, 1, 0.78))
    B.cyl(1.0, 0.02, (0.2, 0.34, -0.1), mat('GlowHSpringL', 0x8fe8e0), n=16, scale=(1, 1, 0.7))
    # a wooden bucket and a folded towel
    B.cyl(0.24, 0.32, (1.75, 0.68, 0.8), M('wood'), n=12, r2=0.2)
    B.tor(0.23, 0.025, (1.75, 0.6, 0.8), M('iron'), seg=16, sides=5)
    B.box((0.5, 0.12, 0.35), (-1.65, 0.62, -0.75), M('pink'), bevel=0.05)
    B.box((0.5, 0.06, 0.35), (-1.65, 0.71, -0.75), M('white'), bevel=0.03)
    B.sph(0.12, (0.6, 0.32, 0.4), M('yellow'), scale=(1, 0.7, 0.8), seg=10, ring=7)   # a rubber duck
    B.sph(0.07, (0.67, 0.42, 0.42), M('yellow'), seg=8, ring=6)
    B.cyl(0.03, 0.06, (0.75, 0.42, 0.42), M('orange'), n=6, r2=0.0, rot=(0, 0, -90))

@item('agility', [[-1.7, 0, 0.95, 0.5, 0, 1.2], [0.45, 0, 0.12, 0.62, 0, 1.8], [2.15, 0, 0.75, 0.12, 0, 1.0]])
def _(B, P):
    for s in (-1, 1):   # the A-frame
        B.box((1.05, 0.06, 0.9), (-1.7 + s * 0.45, 0.6, 0), M('blue'), rot=(0, 0, -s * 50), bevel=0.02)
        for k in range(4):
            B.box((0.04, 0.04, 0.88), (-1.7 + s * (0.2 + k * 0.17), 0.3 + (3 - k) * 0.2 + 0.03, 0), M('white'), rot=(0, 0, -s * 50), bevel=0.0)
    B.box((0.1, 0.1, 0.92), (-1.7, 1.2, 0), M('yellow'), bevel=0.02)
    # the hoop jump
    for z in (-0.55, 0.55):
        B.box((0.1, 1.7, 0.1), (0.45, 0.85, z), M('white'), bevel=0.02)
        B.box((0.5, 0.08, 0.12), (0.45, 0.04, z), M('white'), bevel=0.02)
    B.tor(0.42, 0.06, (0.45, 1.05, 0), M('red'), rot=(90, 0, 90), seg=20, sides=6)
    for z in (-0.47, 0.47):
        B.box((0.06, 0.06, 0.1), (0.45, 1.05, z), M('white'), bevel=0.0)
    # weave poles
    B.box((1.55, 0.05, 0.12), (2.15, 0.03, 0), M('white'), bevel=0.02)
    for k in range(6):
        B.cyl(0.035, 0.95, (1.5 + k * 0.26, 0.5, 0), M('red') if k % 2 else M('yellow'), n=8)
    B.paw(0.12, (-1.7, 0.75, 0.47), M('white'), rot=(0, 0, 0), depth=0.01)

# ============================== UNLOCKS: trophies for milestones ============================
def plinth(B, w=0.9, h=0.35, m=None):
    B.box((w, h, w), (0, h / 2, 0), m or M('stone'), bevel=0.04)
    B.box((w + 0.1, 0.08, w + 0.1), (0, 0.04, 0), M('stoneD'), bevel=0.02)
    B.box((w * 0.5, 0.14, 0.04), (0, h * 0.55, w / 2 + 0.01), GOLD(), bevel=0.01)

@item('t_oak', [[0, 0, 0.8, 0.8, 0, 2.7]])
def _(B, P):
    B.cyl(0.55, 0.55, (0, 0.28, 0), M('stone'), n=12, r2=0.62)
    B.tor(0.6, 0.05, (0, 0.55, 0), M('stoneD'))
    B.cyl(0.55, 0.04, (0, 0.55, 0), M('soil'), n=12)
    B.cyl(0.2, 1.3, (0, 1.15, 0), mat('HOakBark', 0x4a3328), n=8, r2=0.12, rot=(0, 0, 6))
    B.sph(0.11, (0.02, 1.15, 0.16), mat('HOakHollow', 0x120c18), scale=(0.9, 1.3, 0.5), seg=10, ring=7)   # the Hollow Oak's hollow
    for s in (-1, 1):
        B.sph(0.025, (0.02 + s * 0.04, 1.18, 0.21), mat('GlowHLilac', 0xc69bff), seg=6, ring=4)
    for (a, l) in ((40, 0.6), (-35, 0.5), (150, 0.45)):
        B.cyl(0.05, l, (0.18 * math.cos(math.radians(a)), 1.45, 0.18 * math.sin(math.radians(a))), mat('HOakBark', 0x4a3328), n=6, r2=0.02, rot=(0, -a, 55))
    for (x, y, z, r) in ((0, 2.05, 0, 0.6), (-0.42, 1.8, 0.15, 0.4), (0.45, 1.85, -0.1, 0.42), (0.1, 2.35, 0.25, 0.35)):
        B.sph(r, (x, y, z), mat('HOakLeaf', 0x2f6b55), seg=12, ring=8)
    for (x, y, z) in ((-0.35, 1.6, 0.45), (0.5, 1.7, 0.3), (0.1, 2.0, 0.6), (-0.2, 2.35, 0.4), (0.55, 2.1, 0.0), (-0.6, 1.9, -0.2)):
        B.cyl(0.008, 0.12, (x, y + 0.08, z), mat('HOakBark', 0x4a3328), n=4)
        B.sph(0.09, (x, y, z), mat('GlowHLilac', 0xc69bff), scale=(1, 1.2, 1), seg=8, ring=6)
    B.box((0.5, 0.18, 0.04), (0, 0.3, 0.6), GOLD(), bevel=0.01)

@item('t_aquarium', [[0, 0, 1.0, 0.55, 0, 1.95]])
def _(B, P):
    for x in (-0.85, 0.85):
        for z in (-0.4, 0.4):
            B.box((0.1, 0.8, 0.1), (x, 0.4, z), M('woodD'), bevel=0.02)
    B.box((1.95, 0.12, 1.05), (0, 0.82, 0), M('wood'), bevel=0.03)
    B.box((1.8, 0.95, 0.9), (0, 1.36, 0), GLASS(), bevel=0.02)
    for x in (-0.9, 0.9):
        for z in (-0.45, 0.45):
            B.box((0.05, 1.0, 0.05), (x, 1.37, z), M('navy'), bevel=0.0)
    B.box((1.85, 0.06, 0.95), (0, 1.86, 0), M('navy'), bevel=0.02)
    B.box((1.7, 0.1, 0.8), (0, 0.93, 0), M('sand'), bevel=0.02)
    for (x, z, c, h) in ((-0.55, -0.15, 0xff6f8f, 0.55), (-0.25, 0.1, 0xff9a3d, 0.4), (0.5, -0.2, 0xc69bff, 0.6), (0.7, 0.15, 0xff6f8f, 0.35)):
        B.cyl(0.05, h, (x, 0.98 + h / 2, z), mat('HCoral%06x' % c, c), n=6, r2=0.03)
        B.cyl(0.04, h * 0.6, (x + 0.08, 0.98 + h * 0.4, z), mat('HCoral%06x' % c, c), n=6, r2=0.02, rot=(0, 0, -35))
        B.sph(0.07, (x, 0.98 + h, z), mat('HCoral%06x' % c, c), seg=8, ring=6)
    for (x, y, z, c) in ((-0.1, 1.45, 0.05, 0xffd34d), (0.3, 1.25, -0.1, 0x7fe0ff), (-0.5, 1.6, -0.1, 0xff9a3d)):
        B.sph(0.09, (x, y, z), mat('GlowHFish%06x' % c, c), scale=(1.5, 1, 0.6), seg=10, ring=7)
        B.cyl(0.07, 0.1, (x - 0.16, y, z), mat('GlowHFish%06x' % c, c), n=4, r2=0.0, rot=(0, 0, 90), scale=(1, 1, 0.4), smooth=False)
    for k in range(4):
        B.sph(0.035, (0.2 + 0.05 * k, 1.1 + 0.18 * k, 0.2), M('white'), seg=6, ring=4)
    B.box((0.5, 0.14, 0.03), (0, 0.82, 0.54), GOLD(), bevel=0.01)

@item('t_throne', [[0, 0, 0.95, 0.85, 0, 2.7]])
def _(B, P):
    ice, iceD = M('ice'), M('iceD')
    B.box((1.7, 0.5, 1.4), (0, 0.25, 0), iceD, bevel=0.08)
    B.box((1.35, 0.4, 1.0), (0, 0.7, 0.1), ice, bevel=0.08)
    B.box((1.5, 1.8, 0.35), (0, 1.6, -0.5), ice, bevel=0.08)
    for (x, h) in ((-0.55, 0.9), (-0.2, 1.3), (0.2, 1.2), (0.55, 0.85)):
        B.cyl(0.18, h, (x, 2.5 + h / 2 - 0.05, -0.5), mat('GlowHIce', 0xbff6ff), n=5, r2=0.0, smooth=False)
    for s in (-1, 1):
        B.box((0.3, 0.55, 1.0), (s * 0.68, 1.05, 0.05), iceD, bevel=0.06)
        B.cyl(0.13, 0.4, (s * 0.68, 1.45, 0.45), mat('GlowHIce', 0xbff6ff), n=5, r2=0.0, smooth=False)
    B.box((1.15, 0.16, 0.85), (0, 0.98, 0.12), M('fur'), bevel=0.07)
    B.box((1.2, 1.1, 0.12), (0, 1.55, -0.3), M('fur'), bevel=0.05)
    for k in range(5):
        a = 2 * math.pi * k / 5
        B.cyl(0.07, 0.22, (0.22 * math.cos(a), 2.98, -0.5 + 0.22 * math.sin(a)), GOLD(), n=4, r2=0.0, smooth=False)
    B.tor(0.22, 0.05, (0, 2.86, -0.5), GOLD(), seg=16, sides=5)
    B.sph(0.06, (0, 2.9, -0.27), mat('GlowHLilac', 0xc69bff), seg=8, ring=6)

@item('t_lantern', [[0, 0, 0.48, 0.48, 0, 2.45]])
def _(B, P):
    B.cyl(0.45, 0.14, (0, 0.07, 0), M('slate'), n=6, smooth=False)
    B.cyl(0.07, 1.6, (0, 0.9, 0), M('slate'), n=6, smooth=False)
    for k in range(3):
        a = 2 * math.pi * k / 3
        B.cyl(0.04, 0.6, (0.22 * math.cos(a), 0.35, 0.22 * math.sin(a)), M('slate'), n=5, rot=(0, -math.degrees(a), 40))
    B.cyl(0.3, 0.1, (0, 1.75, 0), M('slate'), n=6, smooth=False)
    B.cyl(0.26, 0.5, (0, 2.05, 0), mat('GlowHCrimson', 0xff4f6a), n=6, r2=0.2, smooth=False)
    for k in range(6):
        a = 2 * math.pi * k / 6 + math.pi / 6
        B.box((0.04, 0.55, 0.04), (0.26 * math.cos(a), 2.05, 0.26 * math.sin(a)), M('slate'), bevel=0.0)
    B.cyl(0.32, 0.25, (0, 2.42, 0), M('slate'), n=6, r2=0.05, smooth=False)
    for s in (-1, 1):   # little horns
        B.cyl(0.07, 0.35, (s * 0.24, 2.55, 0), M('cream'), n=6, r2=0.0, rot=(0, 0, -s * 40))
    B.box((0.3, 0.12, 0.03), (0, 0.5, 0.08), GOLD(), bevel=0.0)

@item('t_podium', [[0, 0, 1.5, 0.62, 0, 0.9], [0, 0, 0.38, 0.38, 0.9, 1.95]])
def _(B, P):
    for (x, h, c) in ((-1.0, 0.55, 'stone'), (0, 0.9, 'cream'), (1.0, 0.4, 'stoneD')):
        B.box((1.0, h, 1.15), (x, h / 2, 0), M(c), bevel=0.05)
        B.box((1.0, 0.06, 1.15), (x, h - 0.02, 0), M('red'), bevel=0.02)
    for (x, h, n) in ((-1.0, 0.55, 2), (0, 0.9, 1), (1.0, 0.4, 3)):
        for k in range(n):
            B.box((0.08, 0.25, 0.03), (x - (n - 1) * 0.07 + k * 0.14, h * 0.5, 0.585), GOLD(), bevel=0.0)
    # the cup
    B.cyl(0.2, 0.08, (0, 0.94, 0), GOLD(), n=12)
    B.cyl(0.06, 0.3, (0, 1.12, 0), GOLD(), n=10)
    B.cyl(0.32, 0.5, (0, 1.5, 0), GOLD(), n=16, r2=0.38)
    for s in (-1, 1):
        B.tor(0.17, 0.035, (s * 0.38, 1.55, 0), GOLD(), rot=(90, 0, 0), arc=0.5, scale=(1, 1, 1))
    B.star(0.14, 0.06, 0.03, (0, 1.5, 0.37), M('red'))

@item('t_obelisk', [[0, 0, 0.62, 0.62, 0, 4.3]])
def _(B, P):
    B.box((1.2, 0.3, 1.2), (0, 0.15, 0), M('slate'), bevel=0.04)
    B.cyl(0.55, 3.4, (0, 1.95, 0), mat('HObsidian', 0x2a2f55), n=4, r2=0.3, rot=(0, 45, 0), smooth=False)
    B.cyl(0.42, 0.6, (0, 3.95, 0), mat('HObsidian', 0x2a2f55), n=4, r2=0.0, rot=(0, 45, 0), smooth=False)
    for k in range(7):   # glowing runes climbing the four faces
        y = 0.7 + k * 0.42; w = 0.5 - k * 0.03
        for f in range(4):
            a = f * 90
            r = Euler((0, math.radians(a), 0), 'XYZ').to_matrix()
            o = r @ Vector((0, 0, w * 0.82))
            B.box((0.16, 0.16, 0.02), tuple(Vector((0, y, 0)) + o), mat('GlowHRune', 0x6ff0ff), rot=(0, a, 45 if (k + f) % 2 else 0), bevel=0.0)
    R = P('ring', (0, 3.6, 0))
    R.tor(0.9, 0.05, (0, 3.6, 0), mat('GlowHRune', 0x6ff0ff), rot=(15, 0, 0), seg=28, sides=6)
    for k in range(3):
        a = 2 * math.pi * k / 3
        R.sph(0.1, (0.9 * math.cos(a), 3.6 + 0.9 * math.sin(a) * math.sin(math.radians(15)), 0.9 * math.sin(a)), GOLD(), seg=8, ring=6)

@item('t_sundial', [[0, 0, 0.72, 0.72, 0, 1.35]])
def _(B, P):
    B.cyl(0.7, 0.18, (0, 0.09, 0), M('stoneD'), n=12)
    B.cyl(0.25, 0.75, (0, 0.55, 0), M('stone'), n=10, r2=0.18)
    B.cyl(0.6, 0.12, (0, 0.98, 0), M('stone'), n=24)
    B.cyl(0.52, 0.02, (0, 1.05, 0), M('cream'), n=24)
    for k in range(12):
        a = 2 * math.pi * k / 12
        B.box((0.04, 0.02, 0.12 if k % 3 else 0.2), (0.44 * math.cos(a), 1.065, 0.44 * math.sin(a)), M('navy'), rot=(0, -math.degrees(a) + 90, 0), bevel=0.0)
    B.poly([(0, 0, -0.35), (0, 0, 0.3), (0, 0.42, -0.3)], [(0, 1, 2)], GOLD(), at=(0, 1.06, 0))
    B.poly([(0.02, 0, -0.35), (0.02, 0, 0.3), (0.02, 0.42, -0.3)], [(0, 2, 1)], GOLD(), at=(0, 1.06, 0))
    B.sph(0.12, (0, 1.1, 0.42), M('yellow'), scale=(1, 0.4, 1), seg=12, ring=6)
    for k in range(8):
        a = 2 * math.pi * k / 8
        B.cyl(0.03, 0.1, (0.18 * math.cos(a), 1.1, 0.42 + 0.18 * math.sin(a)), M('orange'), n=4, r2=0.0, rot=(0, -math.degrees(a), 90), smooth=False)

@item('t_playhouse', [[0, 0, 1.15, 0.82, 0, 2.5]])
def _(B, P):
    B.box((2.2, 0.15, 1.5), (0, 0.08, 0), M('woodD'), bevel=0.04)
    B.box((0.95, 0.85, 0.95), (-0.55, 0.58, 0), M('lilac'), bevel=0.05)
    B.box((0.85, 1.4, 0.85), (0.6, 0.85, -0.1), M('teal'), bevel=0.05)
    B.box((0.9, 0.7, 0.9), (-0.3, 1.38, -0.1), M('pink'), bevel=0.05)
    for (x, y, z, r) in ((-0.55, 0.55, 0.48, 0.25), (0.6, 0.65, 0.33, 0.25), (-0.3, 1.38, 0.36, 0.22)):
        B.cyl(r, 0.05, (x, y, z), M('navy'), n=14, rot=(90, 0, 0))
    B.box((0.95, 0.12, 0.95), (0.6, 1.6, -0.1), M('fur'), bevel=0.05)
    B.cyl(0.36, 0.1, (-0.3, 1.78, -0.1), M('fur'), n=14)
    B.box((0.35, 0.05, 1.0), (1.2, 0.5, 0.1), M('woodL'), rot=(0, 0, 50), bevel=0.02)   # a ramp
    for k in range(4):
        B.box((0.36, 0.03, 0.06), (1.2 - 0.13 + k * 0.06, 0.28 + k * 0.15, 0.1), M('woodD'), rot=(0, 0, 50), bevel=0.0)
    B.cyl(0.06, 1.0, (-1.0, 0.65, -0.45), mat('HSisal', 0xe8d0a0), n=8)   # a scratching post
    B.cyl(0.25, 0.08, (-1.0, 1.2, -0.45), M('lilac'), n=12)
    B.tor(0.18, 0.012, (-1.0, 1.5, -0.45), mat('HRope', 0xe8d8b0), rot=(90, 0, 0), arc=0.5, seg=10, sides=4)
    B.sph(0.08, (-1.0, 1.26, -0.27), M('pink'), seg=8, ring=6)
    for k in range(3):   # three paw flags, one per kind of pet
        B.box((0.02, 0.45, 0.02), (-0.6 + k * 0.6, 2.2, -0.1), M('woodD'), bevel=0.0)
        B.poly([(0, 0, 0), (0.3, -0.08, 0), (0, -0.18, 0)], [(0, 1, 2)], [M('pink'), M('teal'), M('yellow')][k], at=(-0.59 + k * 0.6, 2.42, -0.1))
        B.poly([(0, 0, 0.01), (0, -0.18, 0.01), (0.3, -0.08, 0.01)], [(0, 1, 2)], [M('pink'), M('teal'), M('yellow')][k], at=(-0.59 + k * 0.6, 2.42, -0.1))

@item('t_rack', [[0, 0, 1.25, 0.38, 0, 1.85]])
def _(B, P):
    for x in (-1.1, 1.1):
        B.box((0.14, 1.75, 0.14), (x, 0.88, 0), M('woodD'), bevel=0.03)
        B.box((0.5, 0.1, 0.6), (x, 0.05, 0), M('woodD'), bevel=0.03)
    for y in (0.55, 1.15, 1.7):
        B.box((2.35, 0.1, 0.16), (0, y, -0.05), M('wood'), bevel=0.03)
    # stylised weapons resting on the pegs
    B.box((0.7, 0.18, 0.12), (-0.6, 1.32, 0.08), M('blue'), bevel=0.05)                 # zap blaster
    B.box((0.12, 0.25, 0.1), (-0.75, 1.17, 0.08), M('navy'), rot=(0, 0, 15), bevel=0.03)
    B.cyl(0.07, 0.2, (-0.15, 1.32, 0.08), mat('GlowHCyanTip', 0x6fe3ff), n=8, rot=(0, 0, 90))
    B.bone(0.6, 0.06, (0.55, 1.3, 0.08), M('cream'), rot=(0, 0, 0))                    # boomerang bone
    B.sph(0.14, (-0.55, 0.74, 0.1), mat('HBouncy', 0x7fe36a), seg=10, ring=7)           # bouncy ball
    B.cyl(0.12, 0.5, (0.0, 0.74, 0.1), M('orange'), n=10, rot=(0, 0, 90))              # lobber
    B.sph(0.12, (0.25, 0.74, 0.1), M('orange'), seg=8, ring=6)
    B.star(0.16, 0.07, 0.04, (0.7, 0.74, 0.12), M('yellow'))                             # charge cannon star
    B.paw(0.14, (0, 1.88, -0.02), GOLD(), depth=0.03)

@item('t_flag', [[0, 0, 0.55, 0.55, 0, 4.4]])
def _(B, P):
    for k in range(7):
        a = 2 * math.pi * k / 7
        B.sph(0.2, (0.38 * math.cos(a), 0.12, 0.38 * math.sin(a)), M('rock') if k % 2 else M('stoneD'), scale=(1, 0.7, 1), seg=8, ring=6, smooth=False)
    B.cyl(0.32, 0.1, (0, 0.2, 0), M('stone'), n=12)
    B.star(0.26, 0.1, 0.03, (0, 0.26, 0), GOLD(), rot=(90, 0, 0), points=4)            # a compass rose
    B.cyl(0.06, 4.1, (0, 2.3, 0), M('white'), n=10)
    B.sph(0.11, (0, 4.38, 0), GOLD(), seg=10, ring=7)
    # a pennant tapering to a point, in slightly waving strips (it ripples in game)
    F = P('flag', (0, 4.1, 0))
    for i in range(6):
        x = 0.06 + i * 0.27; h = 0.6 - i * 0.085; zz = 0.07 * math.sin(i * 1.1)
        F.box((0.28, h, 0.035), (x + 0.12, 4.1 - 0.3, zz), M('teal') if i % 2 == 0 else mat('HTealL', 0x46d6d0), rot=(0, -14 * math.cos(i * 1.1), 0), bevel=0.01)
    F.paw(0.11, (0.45, 3.8, 0.06), M('white'), depth=0.012)

# ---------------------------------------------------------------- build + export
def build():
    roots = []
    for iid, fn in ITEMS.items():
        root = bpy.data.objects.new('Home_' + iid, None)
        bpy.context.scene.collection.objects.link(root)
        body, moving = Part('Home_%s_body' % iid), []
        def P(name, pivot):
            p = Part('Home_%s_%s' % (iid, name), pivot); moving.append(p); return p
        fn(body, P)
        body.to_object(root)
        for p in moving: p.to_object(root)
        roots.append(root)
    return roots

roots = build()
os.makedirs(OUT, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'home.glb'), export_format='GLB', export_yup=True, export_apply=True,
                          export_materials='EXPORT', export_normals=True, export_animations=False)
json.dump(PARTS, open(os.path.join(OUT, 'home_parts.json'), 'w'), indent=0)
tri = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
print('items', len(ITEMS), 'faces', tri, 'glb', os.path.getsize(os.path.join(OUT, 'home.glb')))
