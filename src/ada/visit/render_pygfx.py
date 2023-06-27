# pip install -U pygfx glfw

import numpy as np
import pathlib
import trimesh
import trimesh.visual.material
from typing import Callable, Iterable

from ada import Part
from ada.base.types import GeomRepr
from ada.config import logger
from ada.core.utils import create_guid
from ada.geom import Geometry
from ada.occ.tessellating import BatchTessellator
from ada.visit.colors import Color

try:
    import pygfx as gfx

    import ada.visit.render_pygfx_helpers as gfx_utils
except ImportError:
    raise ImportError("Please install pygfx to use this renderer -> 'pip install pygfx'.")
try:
    from wgpu.gui.auto import WgpuCanvas
except ImportError:
    raise ImportError("Please install wgpu to use this renderer -> 'pip install wgpu'.")

from ada.visit.render_backend import MeshInfo, RenderBackend

BG_GRAY = Color(57, 57, 57)
PICKED_COLOR = Color(0, 123, 255)


class RendererPyGFX:
    def __init__(self, render_backend: RenderBackend, canvas_title: str = "PyGFX Renderer"):
        self.backend = render_backend

        self._mesh_map = {}
        self._selected_mat = gfx.MeshPhongMaterial(color=PICKED_COLOR, flat_shading=True)
        self.selected_mesh = None
        self._original_geometry = None
        self._original_mesh = None
        self.scene = gfx.Scene()
        self.scene.add(gfx.Background(None, gfx.BackgroundMaterial(BG_GRAY.hex)))
        self._scene_objects = gfx.Group()
        self._scene_objects.receive_shadow = True
        self._scene_objects.cast_shadow = True
        self.scene.add(self._scene_objects)

        canvas = WgpuCanvas(title=canvas_title, max_fps=60)
        renderer = gfx.renderers.WgpuRenderer(canvas, show_fps=False)
        # window = glfw.create_window(int(600), int(400), "GlfW", None, None)
        # glfw.make_context_current(window)
        self.display = gfx.Display(canvas=canvas, renderer=renderer)
        self.on_click_pre: Callable[[gfx.PointerEvent], None] | None = None
        self.on_click_post: Callable[[gfx.PointerEvent, MeshInfo], None] | None = None
        self._init_scene()

    def _init_scene(self):
        scene = self.scene
        dir_light = gfx.DirectionalLight()
        camera = gfx.PerspectiveCamera(70, 1, 0.1, 1000)
        scene.add(camera)
        scene.add(dir_light)
        camera.add(dir_light)
        scene.add(gfx.AmbientLight())
        scene.add(gfx_utils.AxesHelper())

    def _get_scene_meshes(self, scene: trimesh.Scene, tag: str) -> Iterable[gfx.Mesh]:
        for key, m in scene.geometry.items():
            mesh = gfx_utils.gfx_mesh_from_mesh(m)
            buffer_id = int(float(key.replace("node", "")))
            self._mesh_map[mesh.id] = (tag, buffer_id)
            yield mesh

    def add_geom(self, geom: Geometry, name: str, guid: str, tag=create_guid(), metadata=None):
        bt = BatchTessellator()

        geom_mesh = bt.tessellate_geom(geom)
        mat = gfx.MeshPhongMaterial(color=geom.color.rgb, flat_shading=True)
        mesh = gfx.Mesh(gfx_utils.geometry_from_mesh(geom_mesh), material=mat)

        metadata = metadata if metadata else {}
        metadata["meta"] = {guid: (name, "*")}
        metadata["idsequence0"] = {guid: (0, len(geom_mesh.position))}
        self._mesh_map[mesh.id] = (tag, 0)
        self._scene_objects.add(mesh)
        self.backend.add_metadata(metadata, tag)
        # raise NotImplementedError()

    def add_part(self, part: Part, render_override: dict[str, GeomRepr] = None):
        bt = BatchTessellator()
        scene = bt.tessellate_part(part, render_override=render_override)
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
        if self.on_click_pre is not None:
            self.on_click_pre(event)

        info = event.pick_info

        if event.button != 1:
            return

        obj = info.get("world_object", None)
        if isinstance(obj, gfx.Mesh):
            dim = 3
            mesh: gfx.Mesh = event.target
            geom_index = info.get("face_index", None) * dim  # Backend uses a flat array of indices
        elif isinstance(obj, gfx.Line):
            dim = 2
            geom_index = info.get("vertex_index", None) * dim  # Backend uses a flat array of indices
            mesh: gfx.Line = event.target
        elif isinstance(obj, gfx.Points):
            dim = 3
            geom_index = info.get("vertex_index", None)
            mesh: gfx.Points = event.target
        else:
            logger.debug("No mesh selected")
            return

        if self.selected_mesh is not None:
            self.scene.remove(self.selected_mesh)

        # Get what face was clicked
        res = self._mesh_map.get(mesh.id, None)
        if res is None:
            print("Could not find mesh id in map")
            return

        glb_fname, buffer_id = res

        mesh_data = self.backend.get_mesh_data_from_face_index(geom_index, buffer_id, glb_fname)

        if mesh_data is None:
            logger.error(f"Could not find data for {mesh} with {geom_index=}, {buffer_id=} and {glb_fname=}")
            return

        if self.selected_mesh is not None:
            self.scene.remove(self.selected_mesh)

        if isinstance(mesh, gfx.Mesh):
            s = mesh_data.start // dim
            e = mesh_data.end // dim + 1

            if self._original_geometry is not None:
                self._original_mesh.geometry = self._original_geometry

            self._original_geometry = mesh.geometry.clone()

            self.selected_mesh = highlight_clicked_mesh(mesh, [s, e], self._selected_mat)
            # Copy the old mesh map entry to the new mesh

        elif isinstance(mesh, gfx.Line):
            self.selected_mesh = highlight_clicked_line(mesh, self._selected_mat.color)
        elif isinstance(mesh, gfx.Points):
            self.selected_mesh = highlight_clicked_points(mesh, mesh_data, self._selected_mat.color)
        else:
            raise NotImplementedError()

        self.scene.add(self.selected_mesh)

        if self.on_click_post is not None:
            self.on_click_post(event, mesh_data)
        else:
            coord = np.array(event.pick_info["face_coord"])
            print(mesh_data, coord)

    def _add_event_handlers(self):
        ob = self._scene_objects
        ob.add_event_handler(self.on_click, "pointer_down")

    def show(self):
        bbox = self.scene.get_world_bounding_box()
        grid_scale = 1.5 * max(bbox[1] - bbox[0])
        grid = gfx.GridHelper(grid_scale, 10)
        self.scene.add(grid)
        self._add_event_handlers()
        self.display.show(self.scene)


def highlight_clicked_mesh(mesh: gfx.Mesh, indices, material: gfx.MeshPhongMaterial) -> gfx.Group:
    mesh_verts = mesh.geometry.positions.data
    mesh_index = mesh.geometry.indices.data
    new_mesh_indices = [mesh_index[x] for x in range(*indices)]
    trim = trimesh.Trimesh(vertices=mesh_verts, faces=new_mesh_indices)
    geom = gfx.Geometry(
        positions=np.ascontiguousarray(trim.vertices, dtype="f4"),
        indices=np.ascontiguousarray(trim.faces, dtype="i4"),
    )
    selected_mesh = gfx.Mesh(geom, material=material)

    # Remove the selected faces from the cube (which is a numpy array located cube.geometry.indices.data)
    cube_cut_data = np.delete(mesh_index, indices, axis=0)
    geom = gfx.Geometry(
        positions=np.ascontiguousarray(mesh_verts, dtype="f4"),
        indices=np.ascontiguousarray(cube_cut_data, dtype="i4"),
    )
    mesh.geometry = geom

    return selected_mesh


def highlight_clicked_line(mesh: gfx.Line, color: gfx.Color) -> gfx.Line:
    c_mesh = gfx.Line(mesh.geometry, gfx.LineSegmentMaterial(thickness=3, color=color))
    return c_mesh


def highlight_clicked_points(mesh: gfx.Points, mesh_data: MeshInfo, color: gfx.Color) -> gfx.Points:
    s = mesh_data.start
    e = mesh_data.end + 1
    selected_positions = mesh.geometry.positions.data[s:e]

    c_mesh = gfx.Points(
        gfx.Geometry(positions=selected_positions),
        gfx.PointsMaterial(size=15, color=color),
    )
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
