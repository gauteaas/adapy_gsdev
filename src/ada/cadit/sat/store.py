from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from ada.api.primitives import RationalBSplineSurfaceWithKnots, BSplineSurfaceWithKnots
from ada.geom.curves import RationalBSplineCurveWithKnots, BSplineCurveWithKnots
from ada.cadit.sat.read.bsplinesurface import create_bsplinesurface_from_sat, create_bspline_from_sat, \
    add_bsplinesurface_to_ifc
from ada.cadit.sat.read.face import PlateFactory, CurvedPlateFactory

if TYPE_CHECKING:
    from ada import Plate


class SatReader:
    def __init__(self, sat_file):
        self.f = open(sat_file, "r")
        self.lineno = 0
        self.header = ""

    def _read_line(self):
        try:
            self.lineno += 1
            return next(self.f)
        except StopIteration:
            self.f.close()
            raise StopIteration

    def __next__(self):
        line = self._read_line()

        if self.lineno == 1:
            header = line
            while self.lineno <= 2:
                header += self._read_line()
            return header

        if "#" in line:
            return line

        while True:
            line += self._read_line()
            if "#" in line:
                break

        return line

    def __iter__(self):
        return self


class SatStore:
    def __init__(self):
        self.sat_data = dict()

    def add(self, sat_id: int | str, sat_object_data: str):
        if isinstance(sat_id, str):
            sat_id = float(int(sat_id))
        self.sat_data[sat_id] = sat_object_data

    def get(self, sat_id: int | str, split_lines=False) -> list[str]:
        if isinstance(sat_id, str):
            if sat_id.startswith("$"):
                sat_id = sat_id.replace("$", "")
            if sat_id.startswith('-'):
                # It's probably produced by Abaqus CAE
                sat_id = sat_id[1:]
            sat_id = float(int(sat_id))
        if split_lines:
            return self.sat_data[sat_id].splitlines()
        return self.sat_data[sat_id].split()

    def get_name(self, sat_id: int | str) -> str:
        res = self.get(sat_id)
        ref_type = res[1]
        if ref_type.startswith("string"):
            return res[-2]
        elif ref_type.startswith("position"):
            return self.get_name(res[4])
        else:
            return res[1]
            raise NotImplementedError(f"Unknown reference type: {ref_type}")

    def iter(self):
        for sat_id in sorted(self.sat_data.keys()):
            yield self.sat_data[sat_id]


class SatReaderFactory:
    def __init__(self, sat_file):
        self.sat_file = sat_file
        self.entities = dict()
        self.sat_store = SatStore()
        self.plate_factory = PlateFactory(self.sat_store)
        self.curved_plate_factory = CurvedPlateFactory(self.sat_store)
        self.header = ""

    def interpret_sat_object_data(self, sat_object_data: str):
        geom_id, sat_type = sat_object_data.split()[0:2]
        geom_id = geom_id.replace("-", "")

        base_sat_entity = sat_type.split("-")[-1]

        if sat_type == "spline-surface":
            self.entities[geom_id] = create_bsplinesurface_from_sat(sat_object_data)
            # self.entities[geom_id] = self.curved_plate_factory.get_face_name_and_points(sat_object_data)
        elif sat_type == "face":
            self.entities[geom_id] = self.plate_factory.get_face_name_and_points(sat_object_data)
        elif base_sat_entity == "curve":
            self.entities[geom_id] = create_bspline_from_sat(sat_object_data)
        else:
            self.entities[geom_id] = sat_object_data

    def store_sat_object_data(self):
        sat_reader = SatReader(self.sat_file)
        self.header = next(sat_reader)
        for sat_object_str in sat_reader:
            geom_id, sat_type = sat_object_str.split()[0:2]
            geom_id = geom_id.replace("-", "")
            self.sat_store.add(geom_id, sat_object_str)

    def iter_faces(self):
        if len(self.sat_store.sat_data) == 0:
            self.store_sat_object_data()

        for sat_object_data in self.sat_store.iter():
            geom_id, sat_type = sat_object_data.split()[0:2]
            if "face" == sat_type:
                yield sat_object_data
            # elif "spline-surface" == sat_type:
            #     yield sat_object_data

    def iter_curves(self):
        if len(self.sat_store.sat_data) == 0:
            self.store_sat_object_data()

        for sat_object_data in self.sat_store.iter():
            geom_id, sat_type = sat_object_data.split()[0:2]
            if "curve" == sat_type.split("-")[-1]:
                yield sat_object_data

    def iter_flat_plates(self) -> Iterable[tuple[str, list[tuple[float, float, float]]]]:
        for face_data in self.iter_faces():
            if 'spline-surface' in face_data:
                continue
            pl = self.plate_factory.get_face_name_and_points(face_data)
            if pl is None:
                continue
            yield pl

    def iter_plate_objects(self) -> Iterable[Plate]:
        from ada import Plate
        for plate_data in self.iter_flat_plates():
            name, points = plate_data
            yield Plate(name, points, )

    def iter_bspline_objects(self) -> Iterable[BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots]:
        for face_data in self.iter_faces():
            if 'spline-surface' not in face_data:
                continue
            yield create_bsplinesurface_from_sat(face_data)

    def iter_bspline_curve_objects(self) -> Iterable[RationalBSplineSurfaceWithKnots | BSplineSurfaceWithKnots]:
        temp_iter_curves = self.iter_curves()
        for curve_data in self.iter_curves():
            if 'curve' not in curve_data:
                continue
            yield create_bspline_from_sat(curve_data)

    def iter_curved_plate_objects_org(self) -> Iterable[BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots]:
        for face_data in self.iter_faces():
            # if 'spline-surface' not in face_data:
            #     continue
            pl = self.curved_plate_factory.get_face_name_and_points(face_data)
            if pl is None:
                continue
            yield pl

    def iter_curved_plate_objects(self) -> Iterable[BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots]:
        for face_data in self.iter_faces():
            # if 'spline-surface' not in face_data:
            #     continue
            face_name = self.curved_plate_factory.get_face_name(face_data)
            coedges = self.curved_plate_factory.get_face_edges(face_data)
            edges, curves, points, orient = self.curved_plate_factory.get_edge_curves(coedges)

            curve_entities = [create_bspline_from_sat(curve) for curve in curves]
            surface_ref = face_data.split()[10][-1]
            surface_data = self.sat_store.get(surface_ref, split_lines=True)
            surface_data_str = '\n'.join(surface_data)
            surface = create_bsplinesurface_from_sat(surface_data_str)
            yield add_bsplinesurface_to_ifc(surface, edge_curves=edges, points=points, curves=curve_entities, orient=orient)
            break
            # pl = self.curved_plate_factory.get_face_name_and_points(face_data)
            # if pl is None:
            #     continue
            # yield pl

    def iter_curved_plate_objects_org(self) -> Iterable[BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots]:
        for face_data in self.iter_faces():
            if 'spline-surface' not in face_data:
                continue
            pl = self.curved_plate_factory.get_face_name_and_points(face_data)
            if pl is None:
                continue
            yield pl


    def read_data(self):
        self.store_sat_object_data()
        for sat_object in self.sat_store.iter():
            self.interpret_sat_object_data(sat_object)
