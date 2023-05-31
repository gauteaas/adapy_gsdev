from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable

import ada
from ada import Units
from ada.base.types import GeomRepr
from ada.config import logger
from ada.visit.colors import Color

if TYPE_CHECKING:
    from OCC.Core.TopoDS import TopoDS_Shape

    from ada.base.physical_objects import BackendGeom
    from ada.cadit.step.store import StepStore
    from ada.cadit.step.write.writer import StepWriter


class OCCStore:
    @staticmethod
    def get_step_writer() -> StepWriter:
        from ada.cadit.step.write.writer import StepWriter

        return StepWriter("AdaStep")

    @staticmethod
    def get_reader(step_filepath) -> StepStore:
        from ada.cadit.step.store import StepStore

        return StepStore(step_filepath)

    @staticmethod
    def shape_iterator(
        part: ada.Part | BackendGeom | StepStore, geom_repr: GeomRepr = GeomRepr.SOLID
    ) -> tuple[BackendGeom, TopoDS_Shape]:
        from ada.cadit.step.store import StepStore

        if isinstance(geom_repr, str):
            geom_repr = GeomRepr.from_str(geom_repr)

        def safe_geom(obj_):
            try:
                if geom_repr == GeomRepr.SOLID:
                    return obj_.solid()
                elif geom_repr == GeomRepr.SHELL:
                    return obj_.shell()
            except RuntimeError as e:
                logger.warning(f"Failed to add shape {obj.name} due to {e}")
                return None

        if isinstance(part, StepStore):
            for shape in part.iter_all_shapes(include_colors=True):
                yield shape

        if isinstance(part, (ada.Part, ada.Assembly)):
            for obj in part.get_all_physical_objects(pipe_to_segments=True):
                if isinstance(geom_repr, str):
                    geom_repr = GeomRepr.from_str(geom_repr)

                if issubclass(type(obj), ada.Shape):
                    geom = safe_geom(obj)
                elif isinstance(obj, (ada.Beam, ada.Plate, ada.Wall)):
                    geom = safe_geom(obj)
                elif isinstance(obj, (ada.PipeSegStraight, ada.PipeSegElbow)):
                    geom = safe_geom(obj)
                else:
                    logger.error(f"Geometry type {type(obj)} not yet implemented")
                    geom = None

                if geom is None:
                    continue

                yield obj, geom

        else:
            yield part, safe_geom(part)

    @staticmethod
    def to_gltf(
        gltf_file_path,
        occ_shape_iterable: Iterable[OccShape],
        line_defl: float = None,
        angle_def: float = None,
        export_units: Units | str = Units.M,
        progress_callback: Callable[[int, int], None] = None,
        source_units: Units | str = Units.M,
    ):
        from .gltf_writer import to_gltf

        to_gltf(
            gltf_file_path,
            occ_shape_iterable,
            line_defl,
            angle_def,
            export_units,
            progress_callback,
            source_units=source_units,
        )


@dataclass
class OccShape:
    shape: TopoDS_Shape
    color: Color | None = None
    num_tot_entities: int = 0
    name: str | None = None
