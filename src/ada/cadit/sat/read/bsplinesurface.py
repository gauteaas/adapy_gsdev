from __future__ import annotations

from ada.api.primitives import (
    BSplineSurfaceWithKnots,
    IfcBSplineSurfaceForm,
    RationalBSplineSurfaceWithKnots,
    IfcEdgeLoop,
    IfcAdvancedFace,
    IfcEdge,
    IfcVertex,
    IfcVertexPoint,
    IfcCartesianPoint,
    IfcEdgeCurve,
    IfcOrientedEdge,
    IfcPolyline
)
from ada.core.utils import create_guid
import ada.core.constants as ifco
from ada.cadit.ifc.utils import to_real

from ada.geom.curves import (
    BSplineCurveWithKnots,
    RationalBSplineCurveWithKnots,
    BSplineCurveFormEnum,
    BsplineKnotSpecEnum
)
from ada.config import logger

from ada.cadit.ifc.store import IfcStore

from typing import Optional

import re


def split_subtypes(input_string) -> list[str]:
    # Find the indices of the curly brackets
    open_brace_indices = []
    close_brace_indices = []

    for i in range(len(input_string)):
        if input_string[i] == '{':
            open_brace_indices.append(i)
        elif input_string[i] == '}':
            close_brace_indices.append(i)

    # If no opening brace is found, return the original string
    if len(open_brace_indices) == 0:
        return input_string

    head = input_string[:open_brace_indices[0]]
    sub_types = []
    for i in range(len(open_brace_indices)):
        sub_type =input_string[open_brace_indices[-1-i]+1:close_brace_indices[i]-1]
        sub_type_filtered = process_multiline_string(sub_type)
        sub_types.append(sub_type_filtered)
        input_string_1 = input_string[:open_brace_indices[-1-i]-1]
        input_string_2a = input_string[close_brace_indices[i] + 1:]
        input_string_2 = input_string[close_brace_indices[i]+1:].split('\n')[1:]
        input_string = input_string_1 + '\n'.join(input_string_2)

    return head, sub_types[-1]


def process_multiline_string(input_string):
    lines = input_string.split("\n")
    words = lines[0].split()
    if len(words) > 1 and words[1] != "full" or len(words)<2:
        if len(lines) > 2:
            # lines[3] = lines[3].split("full", 1)[-1]
            lines[3] = lines[3][lines[3].find("full"):]
            return lines[0]  + "\n".join(lines[3:])
        else:
            return lines[0]
    return input_string

def extract_control_points(data_lines) -> list[list[float]]:
    res = []
    for line in data_lines:
        if len(line.split()) >= 3:
            res.append([float(i) for i in line.split()])
        else:
            break
    return res
    # return [[float(i) for i in x.split()] for x in data_lines[3 : 3 + v_degree * 4]]

def create_bsplinesurface_from_sat(spline_data_str: str) -> BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots:
    # split_data = split_subtypes(spline_data_str)
    # no_splits = len(spline_data_str.split("{"))
    # split_data = spline_data_str.split("{")
    # head, data = spline_data_str.split("{")
    head, data = split_subtypes(spline_data_str)

    data_lines = [x.strip() for x in data.splitlines()]
    dline = data_lines[0].split()
    u_degree, v_degree = [int(float(x)) for x in dline[3:5]]
    surf_form = IfcBSplineSurfaceForm.UNSPECIFIED
    uknots_in = [float(x) for x in data_lines[1].split()]
    uknots = uknots_in[0::2]
    uMult = [int(x) for x in uknots_in[1::2]]
    uMult[0] = u_degree + 1
    uMult[-1] = u_degree + 1

    vknots_in = [float(x) for x in data_lines[2].split()]
    vknots = vknots_in[0::2]

    vMult = [int(x) for x in vknots_in[1::2]]
    vMult[0] = v_degree + 1
    vMult[-1] = v_degree + 1

    res = extract_control_points(data_lines[3:])
    # res = [[float(i) for i in x.split()] for x in data_lines[3 : 3 + v_degree * 4]]
    control_points = []
    # control_points = res
    for i in range(0, v_degree):
        control_points += [res[i::3]]
        # control_points += [res[i*3:4+i*3]]

    weights = None
    if len(control_points[0]) == 4:
        weights = [[i[-1] for i in x] for x in control_points]
        control_points = [[i[:-1] for i in x] for x in control_points]

    if dline[0] == "exactsur":
        logger.info("Exact surface")

    props = dict(
        uDegree=u_degree,
        vDegree=v_degree,
        controlPointsList=control_points,
        surfaceForm=surf_form,
        uKnots=uknots,
        vKnots=vknots,
        uMultiplicities=uMult,
        vMultiplicities=vMult,
    )

    if weights is not None:
        surface = RationalBSplineSurfaceWithKnots(**props, weightsData=weights)
    else:
        surface = BSplineSurfaceWithKnots(**props)

    return surface

def get_key_of_existing_point(point_vertex_dict: dict, point: list) -> Optional[int]:
    for key, subdict in point_vertex_dict.items():
        is_point_in_subdict = point == subdict["point"]
        if point == subdict["point"]:
            return key
    return None


def add_bsplinesurface_to_ifc(
        surface: BSplineSurfaceWithKnots | RationalBSplineSurfaceWithKnots,
        points: list[float],
        edge_curves: list[IfcEdgeCurve],
        curves: list[IfcEdgeCurve],
        orient: list[bool],

        parent_guid: str = None
):
    """A temporary function to add a B-Spline surface to an IFC file. To be integrated into ifcstore.sync()"""
    ifc_store = IfcStore()
    f = ifc_store.f
    context = ifc_store.get_context("Body")

    ifc_surface = surface.to_ifcopenshell(f)

    # IfcPolyLine
    # p11 = ifc_p(f, (0, 0, 0))
    # p21 = ifc_p(f, (0, 0, 1))
    # poly_line = f.create_entity("IFCPOLYLINE", (p11, p21))
    #
    # # List of vertex points
    # p1 = ifc_p(f, (0, 0, 0))
    # p2 = ifc_p(f, (0, 0, 1))
    # vp1 = f.create_entity("IfcVertexPoint", p1)
    # vp2 = f.create_entity("IfcVertexPoint", p2)

    # List of edge curves
    # curve_entities = [curve.to_ifcopenshell(f) for curve in curves]
    curve_entities = []

    for i, curve in enumerate(curves):
        if isinstance(curve, IfcPolyline):
            # coor = curve.points
            coor = points[i]
            p1 = IfcCartesianPoint(coordinates=coor[0]) #if orient[i] else IfcCartesianPoint(coordinates=coor[1])
            p2 = IfcCartesianPoint(coordinates=coor[1]) #if orient[i] else IfcCartesianPoint(coordinates=coor[0])
            p1_entity = p1.to_ifcopenshell(f)
            p2_entity = p2.to_ifcopenshell(f)
            curve_new = IfcPolyline(points=[p1_entity, p2_entity])
            curve_entities.append(curve_new.to_ifcopenshell(f))
        else:
            curve_entities.append(curve.to_ifcopenshell(f))


    ifc_edge_curve = []
    edge_curve_entities = []
    point_vertex_dict = {}

    for i, edge in enumerate(edge_curves):
        current_vps = []
        for p in points[i]:
            existing_key = get_key_of_existing_point(point_vertex_dict, p)
            if existing_key is None:
                ifc_p = IfcCartesianPoint(coordinates=p)
                ifc_p_ent = ifc_p.to_ifcopenshell(f)
                vp = IfcVertexPoint(vertex_geometry=ifc_p_ent)
                vp_ent = vp.to_ifcopenshell(f)
                point_vertex_dict[len(point_vertex_dict)] = {"point":p,"entity":vp_ent}

            else:
                vp_ent = point_vertex_dict[existing_key]["entity"]

            current_vps.append(vp_ent)

        # p1 = IfcCartesianPoint(coordinates=points[i][0])
        # p2 = IfcCartesianPoint(coordinates=points[i][1])
        #
        # p1_entity = p1.to_ifcopenshell(f)
        # p2_entity = p2.to_ifcopenshell(f)
        #
        # vp1 = IfcVertexPoint(vertex_geometry=p1_entity)
        # vp2 = IfcVertexPoint(vertex_geometry=p2_entity)
        #
        # vp1_entity = vp1.to_ifcopenshell(f)
        # vp2_entity = vp2.to_ifcopenshell(f)

        # ifcedge curve samesense=True implies edge and curve definitions are in the same direction
        # edge_curve_entities.append(f.create_entity("IFCEDGECURVE", EdgeStart=vp1_entity,
        #                                        EdgeEnd=vp2_entity,
        #                                        EdgeGeometry=curve_entities[i],
        #                                        SameSense=True))

        edge_curve_entities.append(f.create_entity("IFCEDGECURVE", EdgeStart=current_vps[0],
                                                   EdgeEnd=current_vps[1],
                                                   EdgeGeometry=curve_entities[i],
                                                   SameSense=True))

    # ifc_edge_curve = [IfcEdgeCurve(edge_start=IfcVertexPoint(vertex_geometry=IfcPoint(coordinates=points[i][0]).to_ifcopenshell(f)).to_ifcopenshell(f),
    #                                edge_stop=IfcVertexPoint(vertex_geometry=IfcPoint(coordinates=points[i][0]).to_ifcopenshell(f)).to_ifcopenshell(f),
    #                                edge_geometry=curve_entities[i],
    #                                same_sense=True) for i,edge in enumerate(edge_curves)]
    # edge_curve_entity_1 =  ifc_edge_curve[0].to_ifcopenshell(f)
    # edge_curve_entities = [edge.to_ifcopenshell(f) for edge in ifc_edge_curve]


    # List of orient edges
    oriented_edges = [IfcOrientedEdge(edge_element=edge_curve, orientation=orient[i]) for i, edge_curve in enumerate(edge_curve_entities) ]
    oriented_edge_entities = [o_edge.to_ifcopenshell(f) for o_edge in oriented_edges]

    edge_loop = IfcEdgeLoop(edge_list=oriented_edge_entities)

    edge_loop_entity = edge_loop.to_ifcopenshell(f)
    outer_bound_entity = f.create_entity("IFCFACEOUTERBOUND", edge_loop_entity, True)
    advanced_face = IfcAdvancedFace(faceSurface=ifc_surface, bounds=[outer_bound_entity], sameSense=True)

    advanced_face_entity = advanced_face.to_ifcopenshell(f)
    closed_shell = f.create_entity("IFCOPENSHELL", (advanced_face_entity,))
    # advanced_brep = f.create_entity("IFCADVANCEDBREP", closed_shell)
    advanced_brep = f.create_entity("IFCSHELLBASEDSURFACEMODEL", (closed_shell,))
    shape_rep = f.create_entity("IFCSHAPEREPRESENTATION", context, "Body", "IfcShellBasedSurfaceModel", (advanced_brep,))
    prod_def_shape = f.create_entity("IFCPRODUCTDEFINITIONSHAPE", None, None, (shape_rep,))

    ifc_loc_z = f.create_entity("IfcDirection", to_real(ifco.Z))
    ifc_loc_x = f.create_entity("IfcDirection", to_real(ifco.X))
    ifc_origin = f.create_entity("IfcCartesianPoint", to_real(ifco.O))
    axis2placement = f.create_entity("IfcAxis2Placement3D", ifc_origin, ifc_loc_z, ifc_loc_x)

    ifclocalplacement = f.create_entity("IfcLocalPlacement",
                                        PlacementRelTo=None,
                                        RelativePlacement=axis2placement
                                        )

    # local_place = create_local_placement(f)
    bldg_el_proxy = f.create_entity(
        "IFCBUILDINGELEMENTPROXY",
        create_guid(),
        ifc_store.owner_history,
        "BuildingElementProxy",
        None,
        None,
        ifclocalplacement,
        prod_def_shape,
        None,
        "NOTDEFINED",
    )
    # parent_guid=None
    # ifc_store.writer.add_related_elements_to_spatial_container([bldg_el_proxy], parent_guid)
    return ifc_store



def create_bspline_from_sat(spline_data_str: str) -> BSplineCurveWithKnots:
    split_data = spline_data_str.split("{")
    # head, data = spline_data_str.split("{")
    head = split_data[0]
    data = split_data[1]

    data_lines = [x.strip() for x in data.splitlines()]
    dline = data_lines[0].split()
    degree = int(dline[3])
    curve_form = BSplineCurveFormEnum.UNSPECIFIED
    closed_curve = False if dline[4] == 'open' else True
    knots_in = [float(x) for x in data_lines[1].split()]
    knots = knots_in[0::2]
    mult = [int(x) for x in knots_in[1::2]]
    # ctrl_p = data_lines[2 : 2 + (degree + 1)]

    control_points = [[float(i) for i in x.split()] for x in data_lines[2 : 2 + (degree + 1)]]

    weights = None
    if len(control_points[0]) == 4:
        weights = [x[-1] for x in control_points]
        control_points = [x[:3] for x in control_points]

    if dline[0] == "exactcur":
        logger.info("Exact curve")

    props = dict(
        degree=degree,
        control_points_list=control_points,
        curve_form=curve_form,
        closed_curve=closed_curve,
        self_intersect = False,
        knots=knots,
        knot_multiplicities=mult,
        knot_spec=BsplineKnotSpecEnum.UNSPECIFIED
    )

    if weights is not None:
        curve = RationalBSplineCurveWithKnots(**props, weightsData=weights)
    else:
        curve = BSplineCurveWithKnots(**props)

    return curve

def create_bspline_from_sat(edge_data_str: str) -> BSplineCurveWithKnots:
    split_data = edge_data_str.split("{")
    # head, data = spline_data_str.split("{")
    head = split_data[0]
    if "straight-curve" in head:
        return IfcPolyline(points=[])
    data = split_data[1]

    data_lines = [x.strip() for x in data.splitlines()]
    dline = data_lines[0].split()
    degree = int(dline[3])
    curve_form = BSplineCurveFormEnum.UNSPECIFIED
    closed_curve = False if dline[4] == 'open' else True
    knots_in = [float(x) for x in data_lines[1].split()]
    knots = knots_in[0::2]
    mult = [int(x) for x in knots_in[1::2]]
    # adjust first and las mult as degree +1, not sure if this is correct, but is what I found as pattern in error messages
    mult[0] = degree + 1
    mult[-1] = degree + 1
    # ctrl_p = data_lines[2 : 2 + (degree + 1)]

    # control_points = [[float(i) for i in x.split()] for x in data_lines[2 : 2 + (degree + 1)]]
    control_points = extract_control_points(data_lines[2:])
    weights = None
    if len(control_points[0]) == 4:
        weights = [x[-1] for x in control_points]
        control_points = [x[:3] for x in control_points]

    if dline[0] == "exactcur":
        logger.info("Exact curve")

    props = dict(
        degree=degree,
        control_points_list=control_points,
        curve_form=curve_form,
        closed_curve=closed_curve,
        self_intersect = False,
        knots=knots,
        knot_multiplicities=mult,
        knot_spec=BsplineKnotSpecEnum.UNSPECIFIED
    )

    if weights is not None:
        curve = RationalBSplineCurveWithKnots(**props, weightsData=weights)
    else:
        curve = BSplineCurveWithKnots(**props)
    if props['degree'] == 1:
        # curve = IfcPolyline(points=[IfcCartesianPoint(coordinates=p) for p in control_points])
        print("")
        # curve = IfcPolyline(points=control_points)
        curve = IfcPolyline(points=[])

    return curve
