from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.GC import GC_MakeArcOfCircle
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Wire
from OCC.Core.gp import gp_Pnt

from ada.geom.curves import IndexedPolyCurve, Line, ArcLine


def segments_to_edges(segments: list[Line | ArcLine]) -> list[TopoDS_Edge]:
    edges = []
    for seg in segments:
        if isinstance(seg, ArcLine):
            a_arc_of_circle = GC_MakeArcOfCircle(gp_Pnt(*seg.start), gp_Pnt(*seg.center), gp_Pnt(*seg.end))
            a_edge2 = BRepBuilderAPI_MakeEdge(a_arc_of_circle.Value()).Edge()
            edges.append(a_edge2)
        else:
            edge = BRepBuilderAPI_MakeEdge(gp_Pnt(*seg.start), gp_Pnt(*seg.end)).Edge()
            edges.append(edge)

    return edges


def make_indexed_poly_curve_from_geom(curve: IndexedPolyCurve) -> TopoDS_Wire:
    wire = BRepBuilderAPI_MakeWire()
    for seg in segments_to_edges(curve.segments):
        wire.Add(seg)
    wire.Build()
    return wire.Wire()
    face = BRepBuilderAPI_MakeFace([wire])

