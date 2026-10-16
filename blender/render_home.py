"""Render review previews of every Home_* item in home.glb (Cycles, CPU) and tile them into labelled contact sheets:
    blender -b --factory-startup --python blender/render_home.py -- <glb> <out_dir>
Env: ONLY=id,id,... (just those items / variants), SHEET=name (sheet file prefix, default 'home'), COLS / ROWS (tiles per
sheet, default 6 x 5), SIZE (tile px, default 300), KEEP=1 (keep the per-item PNGs; by default they are deleted after
tiling). Colour variants come from home_variants.json next to the glb (materials recoloured by name, as the game does).
Headless EEVEE crashed in the NVIDIA driver on 2026-10-15, hence Cycles on the CPU."""
import bpy, sys, os, math, json
import numpy as np
from mathutils import Vector
GLB, OUT = os.path.abspath(sys.argv[-2]), os.path.abspath(sys.argv[-1])   # absolute: Blender's image save reads relative paths against the .blend
only = set(os.environ['ONLY'].split(',')) if os.environ.get('ONLY') else None
SHEET, COLS, ROWS, SIZE = os.environ.get('SHEET', 'home'), int(os.environ.get('COLS', 6)), int(os.environ.get('ROWS', 5)), int(os.environ.get('SIZE', 300))
vpath = os.path.join(os.path.dirname(GLB), 'home_variants.json')
VARIANTS = json.load(open(vpath)) if os.path.exists(vpath) else {}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 20; sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = SIZE; sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.32, 0.36, 0.5, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.9
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 3.2; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50
bpy.ops.mesh.primitive_circle_add(vertices=48, radius=6, fill_type='NGON'); g = bpy.context.active_object
gm = bpy.data.materials.new('ground'); gm.use_nodes = True; gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.09, 0.2, 0.15, 1); g.data.materials.append(gm)
# the label: a text object fixed in front of the camera, so it sits at the bottom of every frame
tc = bpy.data.curves.new('label', 'FONT'); tc.align_x = 'CENTER'; tc.size = 0.045
label = bpy.data.objects.new('label', tc); sc.collection.objects.link(label); label.parent = cam
label.location = (0, -0.33, -1.0); label.visible_shadow = False
lm = bpy.data.materials.new('labelm'); lm.use_nodes = True
lp = lm.node_tree.nodes['Principled BSDF']; lp.inputs['Base Color'].default_value = (1, 1, 1, 1)
lp.inputs['Emission Color'].default_value = (1, 1, 1, 1); lp.inputs['Emission Strength'].default_value = 4.0
tc.materials.append(lm)

def lin(hexs):
    h = int(hexs.lstrip('#'), 16)
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in (((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255)) + (1.0,)

def recolour(tint):
    """set materials by name (as the game's tint does); returns the old colours to put back"""
    old = []
    for name, hexs in tint.items():
        m = bpy.data.materials.get(name)
        if not m or not m.use_nodes: continue
        p = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not p: continue
        old.append((p, tuple(p.inputs['Base Color'].default_value), tuple(p.inputs['Emission Color'].default_value)))
        p.inputs['Base Color'].default_value = lin(hexs)
        if name.startswith('Glow'): p.inputs['Emission Color'].default_value = lin(hexs)
    return old

roots = [o for o in sc.objects if o.name.startswith('Home_') and o.parent is None]
by = {r.name[5:]: r for r in roots}
jobs = []   # (tile id, model id, tint)
for iid in by:
    jobs.append((iid, iid, {}))
    for vid, v in VARIANTS.items():
        if v['model'] == iid: jobs.append((vid, iid, v['tint']))
if only: jobs = [j for j in jobs if j[0] in only]
os.makedirs(OUT, exist_ok=True)
done = []
for (tid, iid, tint) in jobs:
    r = by[iid]
    for o in roots:
        hide = o is not r
        for c in [o] + list(o.children_recursive): c.hide_render = hide
    pts = [c.matrix_world @ Vector(v) for c in r.children_recursive if c.type == 'MESH' for v in c.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (lo + hi) / 2; size = (hi - lo).length
    d = Vector((0.75, -1.25, 0.8)).normalized() * size * 1.45
    cam.location = ctr + d
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    g.location = (ctr.x, ctr.y, 0)
    tc.body = tid
    old = recolour(tint)
    sc.render.filepath = os.path.join(OUT, tid + '.png')
    bpy.ops.render.render(write_still=True)
    for (p, bc, ec) in old:
        p.inputs['Base Color'].default_value = bc; p.inputs['Emission Color'].default_value = ec
    done.append(tid)
    print('rendered', tid)

# tile into contact sheets (COLS x ROWS per sheet), then drop the per-item PNGs
per = COLS * ROWS
for s in range(0, len(done), per):
    ids = done[s:s + per]
    sheet = np.full((ROWS * SIZE, COLS * SIZE, 4), 1.0, dtype=np.float32)
    for k, tid in enumerate(ids):
        im = bpy.data.images.load(os.path.join(OUT, tid + '.png'))
        px = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        row, col = k // COLS, k % COLS
        y0 = (ROWS - 1 - row) * SIZE   # image rows start at the bottom
        sheet[y0:y0 + SIZE, col * SIZE:(col + 1) * SIZE] = px
        bpy.data.images.remove(im)
    img = bpy.data.images.new('sheet', COLS * SIZE, ROWS * SIZE, alpha=True)
    img.pixels = sheet.ravel()
    img.filepath_raw = os.path.join(OUT, '%s_sheet%d.png' % (SHEET, s // per + 1)); img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img)
    print('sheet', s // per + 1, len(ids))
if not os.environ.get('KEEP'):
    for tid in done:
        try: os.remove(os.path.join(OUT, tid + '.png'))
        except OSError: pass
