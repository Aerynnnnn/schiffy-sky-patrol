"""Render a preview of every Home_* item in home.glb (Cycles, CPU) for review: python render_home.py <glb> <out_dir> [ids]"""
import bpy, sys, os, math
from mathutils import Vector
GLB, OUT = sys.argv[-2], sys.argv[-1]   # set ONLY=id,id,... to render just those items
only = os.environ.get('ONLY', '').split(',') if os.environ.get('ONLY') else None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 24; sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = 360; sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.32, 0.36, 0.5, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.9
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 3.2; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50
# ground disc
bpy.ops.mesh.primitive_circle_add(vertices=48, radius=6, fill_type='NGON'); g = bpy.context.active_object
gm = bpy.data.materials.new('ground'); gm.use_nodes = True; gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.09, 0.2, 0.15, 1); g.data.materials.append(gm)
roots = [o for o in sc.objects if o.name.startswith('Home_') and o.parent is None]
os.makedirs(OUT, exist_ok=True)
for r in roots:
    iid = r.name[5:]
    if only and iid not in only: continue
    for o in roots:
        hide = o is not r
        for c in [o] + list(o.children_recursive): c.hide_render = hide
    pts = [c.matrix_world @ Vector(v) for c in r.children_recursive if c.type == 'MESH' for v in c.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    ctr = (lo + hi) / 2; size = (hi - lo).length
    d = Vector((0.75, -1.25, 0.8)).normalized() * size * 1.35
    cam.location = ctr + d
    cam.rotation_euler = (ctr - cam.location).to_track_quat('-Z', 'Y').to_euler()
    g.location = (ctr.x, ctr.y, 0)
    sc.render.filepath = os.path.join(OUT, iid + '.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', iid)
