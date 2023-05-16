from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING, Callable

from ada.base.root import Root
from ada.base.types import GeomRepr
from ada.base.units import Units
from ada.concepts.transforms import Placement
from ada.core.constants import color_map as _cmap
from ada.visit.config import ExportConfig

if TYPE_CHECKING:
    from ada import FEM, Penetration
    from ada.cadit.ifc.store import IfcStore
    from ada.fem import Elem
    from ada.fem.meshing import GmshOptions


# TODO: Consider storing primitive geometry definitions as an attribute in the BackendGeom class to simplify subclasses.
class BackendGeom(Root):
    """The backend of all physical components (Beam, Plate, etc.) or aggregate of components (Part, Assembly)"""

    _renderer = None

    def __init__(
        self,
        name,
        guid=None,
        metadata=None,
        units=Units.M,
        parent=None,
        colour=None,
        placement=Placement(),
        ifc_store: IfcStore = None,
        opacity=1.0,
    ):
        super().__init__(name, guid, metadata, units, parent, ifc_store=ifc_store)
        from ada.visit.rendering.new_render_api import Visualize

        self._penetrations = []
        self._placement = placement
        placement.parent = self
        self.colour = colour
        self.opacity = opacity
        self._elem_refs = []
        self._viz = Visualize(self)

    def add_penetration(self, pen, add_to_layer: str = None):
        from ada import Penetration, Shape
        from ada.base.changes import ChangeAction

        pen.parent = self

        if issubclass(type(pen), Shape) is True:
            pen = Penetration(pen, parent=self)
            self._penetrations.append(pen)
        elif type(pen) is Penetration:
            self._penetrations.append(pen)
        else:
            raise ValueError("")

        if self.change_type in (ChangeAction.NOCHANGE, ChangeAction.NOTDEFINED):
            self.change_type = ChangeAction.MODIFIED

        if add_to_layer is not None:
            a = self.get_assembly()
            a.presentation_layers.add_object(pen, add_to_layer)

        return pen

    def to_fem_obj(
        self,
        mesh_size,
        geom_repr: str | GeomRepr,
        options: GmshOptions = None,
        silent=True,
        use_quads=False,
        use_hex=False,
        name="AdaFEM",
        interactive=False,
    ) -> FEM:
        from ada.fem.meshing import GmshOptions, GmshSession

        if isinstance(geom_repr, str):
            geom_repr = GeomRepr.from_str(geom_repr)

        options = GmshOptions(Mesh_Algorithm=8) if options is None else options
        with GmshSession(silent=silent, options=options) as gs:
            gs.add_obj(self, geom_repr=geom_repr)
            gs.mesh(mesh_size, use_quads=use_quads, use_hex=use_hex)
            if interactive:
                gs.open_gui()
            return gs.get_fem(name)

    def to_fem(
        self,
        mesh_size,
        geom_repr,
        name: str,
        fem_format: str,
        options: GmshOptions = None,
        silent=True,
        use_quads=False,
        use_hex=False,
        return_assembly=False,
        **kwargs,
    ):
        from ada import Assembly, Part

        p = Part(name)
        p.fem = self.to_fem_obj(mesh_size, geom_repr, options, silent, use_quads, use_hex, name)
        a = Assembly() / (p / self)
        if return_assembly:
            return a
        a.to_fem(name, fem_format, **kwargs)

    def to_stp(self, destination_file, geom_repr: GeomRepr = GeomRepr.SOLID, progress_callback: Callable = None):
        from ada.occ.store import OCCStore

        step_writer = OCCStore.get_step_writer()
        step_writer.add_shape(self.solid(), self.name, rgb_color=self.colour_norm)
        step_writer.export(destination_file)

    def to_obj_mesh(self, geom_repr: str | GeomRepr = GeomRepr.SOLID, export_config: ExportConfig = ExportConfig()):
        from ada.occ.visit_utils import occ_geom_to_poly_mesh

        if isinstance(geom_repr, str):
            geom_repr = GeomRepr.from_str(geom_repr)
        return occ_geom_to_poly_mesh(self, geom_repr=geom_repr, export_config=export_config)

    @property
    def colour(self):
        return self._colour

    @colour.setter
    def colour(self, value):
        if type(value) is str:
            if value.lower() not in _cmap.keys():
                raise ValueError("Currently unsupported")
            self._colour = _cmap[value.lower()]
        else:
            self._colour = value

    @property
    def colour_norm(self):
        if self._colour is None:
            self.colour = "white"
        return [x / 255 for x in self.colour] if any(i > 1 for i in self.colour) else self.colour

    @property
    def colour_webgl(self):
        from OCC.Display.WebGl.jupyter_renderer import format_color

        if self.colour is None:
            return None
        if self.colour[0] == -1 and self.colour[1] == -1 and self.colour[2] == -1:
            return None

        if self.colour[0] <= 1.0:
            colour = [int(x * 255) for x in self.colour]
        else:
            colour = [int(x) for x in self.colour]

        colour_formatted = format_color(*colour)
        return colour_formatted

    @property
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        if (0.0 <= value <= 1.0) is False:
            raise ValueError(f'Opacity is only valid between 1 and 0. "{value}" was passed in')

        self._opacity = value

    @property
    def transparent(self):
        return False if self.opacity == 1.0 else True

    @property
    def penetrations(self) -> list[Penetration]:
        return self._penetrations

    @property
    def elem_refs(self) -> list[Elem]:
        return self._elem_refs

    @elem_refs.setter
    def elem_refs(self, value):
        self._elem_refs = value

    @property
    def placement(self) -> Placement:
        return self._placement

    @placement.setter
    def placement(self, value: Placement):
        self._placement = value

    def _repr_html_(self):
        from ada.config import Settings

        if Settings.use_new_visualize_api is True:
            self._viz.objects = []
            self._viz.add_obj(self)
            self._viz.display(return_viewer=False)
            return ""

        from IPython.display import display
        from ipywidgets import HBox, VBox

        from ada.visit.rendering.renderer_pythreejs import MyRenderer

        renderer = MyRenderer()

        renderer.DisplayObj(self)
        renderer.build_display()
        self._renderer = renderer
        display(HBox([VBox([HBox(renderer.controls), renderer.renderer]), renderer.html]))
        return ""

    def solid(self):
        raise NotImplementedError()

    def shell(self):
        raise NotImplementedError()

    def line(self):
        raise NotImplementedError()
