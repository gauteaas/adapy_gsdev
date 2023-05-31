from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable

from ada.base.root import Root
from ada.base.types import GeomRepr
from ada.base.units import Units
from ada.concepts.transforms import Placement
from ada.visit.colors import Color, color_dict
from ada.visit.config import ExportConfig

if TYPE_CHECKING:
    from ada import FEM, Penetration
    from ada.cadit.ifc.store import IfcStore
    from ada.fem import Elem
    from ada.fem.meshing import GmshOptions
    from ada.geom import Geometry


# TODO: Consider storing primitive geometry definitions as an attribute in the BackendGeom class to simplify subclasses.
class BackendGeom(Root):
    """The backend of all physical components (Beam, Plate, etc.) or aggregate of components (Part, Assembly)"""

    def __init__(
        self,
        name,
        guid=None,
        metadata=None,
        units=Units.M,
        parent=None,
        color: Color | Iterable[float, float, float] | str | None = None,
        placement=Placement(),
        ifc_store: IfcStore = None,
        opacity=1.0,
    ):
        super().__init__(name, guid, metadata, units, parent, ifc_store=ifc_store)
        self._penetrations = []

        self._placement = placement
        placement.parent = self
        if isinstance(color, str):
            color = Color.from_str(color, opacity=opacity)
        elif isinstance(color, Iterable):
            color = list(color)
            if len(color) == 3:
                color = Color(*color, opacity=opacity)
            else:
                color = Color(*color)
        elif color is None:
            color = Color(*color_dict["gray"], opacity=opacity)
        self.color = color
        self._elem_refs = []

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
        step_writer.add_shape(self.solid(), self.name, rgb_color=self.color.rgb)
        step_writer.export(destination_file)

    def to_obj_mesh(self, geom_repr: str | GeomRepr = GeomRepr.SOLID, export_config: ExportConfig = ExportConfig()):
        from ada.occ.visit_utils import occ_geom_to_poly_mesh

        if isinstance(geom_repr, str):
            geom_repr = GeomRepr.from_str(geom_repr)

        return occ_geom_to_poly_mesh(self, geom_repr=geom_repr, export_config=export_config)

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
        from IPython.display import display
        from ipywidgets import HBox, VBox

        from ada.config import Settings
        from ada.visit.rendering.renderer_pythreejs import MyRenderer

        if Settings.use_new_visualize_api is True:
            from ada.visit.rendering.new_render_api import Visualize

            viz = Visualize(self)
            viz.objects = []
            viz.add_obj(self)
            viz.display(return_viewer=False)
            return ""

        renderer = MyRenderer()

        renderer.DisplayObj(self)
        renderer.build_display()
        display(HBox([VBox([HBox(renderer.controls), renderer.renderer]), renderer.html]))
        return ""

    def solid(self):
        raise NotImplementedError()

    def shell(self):
        raise NotImplementedError()

    def line(self):
        raise NotImplementedError()

    def solid_geom(self) -> Geometry:
        raise NotImplementedError(f"solid_geom not implemented for {self.__class__.__name__}")

    def shell_geom(self) -> Geometry:
        raise NotImplementedError(f"shell_geom not implemented for {self.__class__.__name__}")

    def line_geom(self) -> Geometry:
        raise NotImplementedError(f"line_geom not implemented for {self.__class__.__name__}")
