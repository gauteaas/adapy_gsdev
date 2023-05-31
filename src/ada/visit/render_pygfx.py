# pip install -U pygfx glfw

import pathlib
from itertools import groupby
from typing import Iterable

import numpy as np
import trimesh.visual.material
from trimesh import Trimesh  # noqa

from ada import Part
from ada.cadit.ifc.utils import create_guid
from ada.geom import Geometry
from ada.occ.tessellating import BatchTessellator
from ada.visit.gltf.meshes import MeshStore
from ada.visit.gltf.optimize import concatenate_stores
from ada.visit.gltf.store import merged_mesh_to_trimesh_scene
from ada.visit.render_pygfx_helpers import AxesHelper

try:
    import pygfx as gfx
except ImportError:
    raise ImportError("Please install pygfx to use this renderer -> 'pip install pygfx'.")
try:
    from wgpu.gui.auto import WgpuCanvas
    from wgpu.gui.jupyter import JupyterWgpuCanvas
except ImportError:
    raise ImportError("Please install wgpu to use this renderer -> 'pip install wgpu'.")

from ada.visit.render_backend import RenderBackend

BACKGROUND_GRAY = (57, 57, 57)
PICKED_COLOR = (0, 123, 255)


def tri_mat_to_gfx_mat(tri_mat: trimesh.visual.material.PBRMaterial) -> gfx.MeshPhongMaterial | gfx.MeshBasicMaterial:
    color = gfx.Color(*[x / 255 for x in tri_mat.baseColorFactor[:3]])

    return gfx.MeshPhongMaterial(color=color, flat_shading=True)


def geometry_from_mesh(mesh: trimesh.Trimesh | MeshStore) -> gfx.Geometry:
    """Convert a Trimesh geometry object to pygfx geometry."""

    if isinstance(mesh, MeshStore):
        kwargs = dict(
            positions=np.ascontiguousarray(mesh.get_position3(), dtype="f4"),
            indices=np.ascontiguousarray(mesh.get_indices3(), dtype="i4"),
        )
    else:
        kwargs = dict(
            positions=np.ascontiguousarray(mesh.vertices, dtype="f4"),
            indices=np.ascontiguousarray(mesh.faces, dtype="i4"),
        )
        if mesh.visual.kind == "texture" and mesh.visual.uv is not None and len(mesh.visual.uv) > 0:
            # convert the uv coordinates from opengl to wgpu conventions.
            # wgpu uses the D3D and Metal coordinate systems.
            # the coordinate origin is in the upper left corner, while the opengl coordinate
            # origin is in the lower left corner.
            # trimesh loads textures according to the opengl coordinate system.
            wgpu_uv = mesh.visual.uv * np.array([1, -1]) + np.array([0, 1])  # uv.y = 1 - uv.y
            kwargs["texcoords"] = np.ascontiguousarray(wgpu_uv, dtype="f4")
        elif mesh.visual.kind == "vertex":
            kwargs["colors"] = np.ascontiguousarray(mesh.visual.vertex_colors, dtype="f4")

    return gfx.Geometry(**kwargs)


class RendererPyGFX:
    def __init__(self, render_backend: RenderBackend, canvas_title: str = "PyGFX Renderer"):
        self.backend = render_backend

        self._mesh_map = {}
        self._selected_mat = gfx.MeshPhongMaterial(color=PICKED_COLOR, flat_shading=True)
        self.selected_mesh = None
        self.scene = gfx.Scene()

        self.scene.add(gfx.Background(None, gfx.BackgroundMaterial("#393939")))
        self._scene_objects = gfx.Group()
        self.scene.add(self._scene_objects)

        canvas = WgpuCanvas(title=canvas_title, max_fps=60)
        renderer = gfx.renderers.WgpuRenderer(canvas, show_fps=False)
        self.display = gfx.Display(canvas=canvas, renderer=renderer)

        self._init_scene()

    def _init_scene(self):
        scene = self.scene
        scene.add(gfx.DirectionalLight())
        scene.add(gfx.AmbientLight())
        scene.add(gfx.GridHelper())
        scene.add(AxesHelper())

    def _get_scene_meshes(self, scene: trimesh.Scene, tag: str) -> Iterable[gfx.Mesh]:
        for key, m in scene.geometry.items():
            mesh = gfx.Mesh(geometry_from_mesh(m), material=tri_mat_to_gfx_mat(m.visual.material))
            buffer_id = int(float(key.replace("node", "")))
            self._mesh_map[mesh.id] = (tag, buffer_id)
            yield mesh

    def add_geom(self, geom: Geometry, name: str, guid: str, tag=create_guid(), metadata=None):
        bt = BatchTessellator()

        geom_mesh = bt.tessellate_geom(geom)
        mat = gfx.MeshPhongMaterial(color=geom.color.rgb, flat_shading=True)
        mesh = gfx.Mesh(geometry_from_mesh(geom_mesh), material=mat)

        metadata = metadata if metadata else {}
        metadata["meta"] = {guid: (name, "*")}
        metadata["idsequence0"] = {guid: (0, len(geom_mesh.position))}
        self._mesh_map[mesh.id] = (tag, 0)
        self._scene_objects.add(mesh)
        self.backend.add_metadata(metadata, tag)
        raise NotImplementedError()

    def add_part(self, part: Part):
        graph = part.get_graph_store()
        scene = trimesh.Scene(base_frame=graph.top_level.name)
        scene.metadata["meta"] = graph.create_meta(suffix="")
        bt = BatchTessellator()
        all_shapes = sorted(bt.batch_tessellate(part.get_all_physical_objects()), key=lambda x: x.material)
        for mat_id, meshes in groupby(all_shapes, lambda x: x.material):
            merged_store = concatenate_stores(meshes)
            merged_mesh_to_trimesh_scene(scene, merged_store, bt.get_mat_by_id(mat_id), mat_id, graph)

        self.add_trimesh_scene(scene, part.name, commit=True)

    def add_trimesh_scene(self, trimesh_scene: trimesh.Scene, tag: str, commit: bool = False):
        meshes = self._get_scene_meshes(trimesh_scene, tag)
        self._scene_objects.add(*meshes)
        self.backend.add_metadata(trimesh_scene.metadata, tag)
        if commit:
            self.backend.commit()

    def load_glb_files_into_scene(self, glb_files: Iterable[pathlib.Path]):
        num_scenes = 0
        start_meshes = len(self._scene_objects.children)

        for glb_file in glb_files:
            num_scenes += 1
            scene = self.backend.glb_to_trimesh_scene(glb_file)
            self.add_trimesh_scene(scene, glb_file.stem, False)
            self.backend.commit()

        num_meshes = len(self._scene_objects.children) - start_meshes
        print(f"Loaded {num_meshes} meshes from {num_scenes} glb files")
        self.backend.commit()

    def on_click(self, event: gfx.PointerEvent):
        info = event.pick_info

        if event.button != 1:
            return
        if "face_index" not in info:
            if self.selected_mesh is not None:
                self.scene.remove(self.selected_mesh)
            return

        face_index = info["face_index"] * 3  # Backend uses a flat array of indices
        mesh: gfx.Mesh = event.target

        # Get what face was clicked
        res = self._mesh_map.get(mesh.id, None)
        if res is None:
            print("Could not find mesh id in map")
            return
        glb_fname, buffer_id = res

        mesh_data = self.backend.get_mesh_data_from_face_index(face_index, buffer_id, glb_fname)

        if self.selected_mesh is not None:
            self.scene.remove(self.selected_mesh)

        s = mesh_data.start // 3
        e = mesh_data.end // 3 + 1
        indices = mesh.geometry.indices.data[s:e]
        self.selected_mesh = clicked_mesh(mesh, indices, self._selected_mat)

        self.scene.add(self.selected_mesh)
        print(mesh_data)

    def _add_event_handlers(self):
        ob = self._scene_objects
        ob.add_event_handler(self.on_click, "pointer_down")

    def show(self):
        self._add_event_handlers()
        self.display.show(self.scene)


def clicked_mesh(mesh: gfx.Mesh, indices, material, sfac=1.01) -> gfx.Mesh:
    trim = trimesh.Trimesh(vertices=mesh.geometry.positions.data, faces=indices)
    scale_tri_mesh(trim, sfac)

    geom = gfx.Geometry(
        positions=np.ascontiguousarray(trim.vertices, dtype="f4"),
        indices=np.ascontiguousarray(trim.faces, dtype="i4"),
    )

    c_mesh = gfx.Mesh(geom, material)
    c_mesh.scale.set(sfac, sfac, sfac)
    return c_mesh


def scale_tri_mesh(mesh: trimesh.Trimesh, sfac: float):
    # Calculate volumetric center
    center = mesh.center_mass

    # Create translation matrices
    translate_to_origin = trimesh.transformations.translation_matrix(-center)
    translate_back = trimesh.transformations.translation_matrix(center)

    # Create scale matrix
    scale_matrix = trimesh.transformations.scale_matrix(sfac, center)

    # Combine transformations
    transform = translate_back @ scale_matrix @ translate_to_origin

    # Apply the transformation
    mesh.apply_transform(transform)
