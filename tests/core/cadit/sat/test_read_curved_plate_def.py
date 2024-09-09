import logging
import os

import ifcopenshell.validate

from ada.api.primitives import RationalBSplineSurfaceWithKnots
from ada.geom.curves import RationalBSplineCurveWithKnots, BSplineCurveWithKnots
from ada.cadit.ifc.utils import ifc_p
from ada.cadit.sat.store import SatReaderFactory
from ada.cadit.ifc.store import IfcStore
from ada.config import logger


def test_read_a_curved_plate():
    file = r'C:\AibelProgs\code\adapy_gsdev_2\tests\core\cadit\sat\curved_plate.sat'
    sat_reader = SatReaderFactory(file)
    # sat_reader = SatReaderFactory('curved_plate_2.SAT')
    bsplines= list(sat_reader.iter_bspline_objects())
    print(bsplines)
    assert len(bsplines) == 1

    bspline = bsplines[0]
    assert isinstance(bspline, RationalBSplineSurfaceWithKnots)

    # IFC export
    ifc_store = IfcStore()
    ifc: ifcopenshell.file = ifc_store.f
    # https://standards.buildingsmart.org/IFC/RELEASE/IFC4_1/FINAL/HTML/schema/ifcgeometryresource/lexical/ifcrationalbsplinesurfacewithknots.htm
    cplist = bspline.controlPointsList
    type_check = type(cplist[0][0][0])
    list_check = [[[j if i<3 else 3.0 for i,j in enumerate(y)] for y in x] for x in bspline.controlPointsList]
    # ctrl_p = [[ifc_p(ifc, [j for j in y[0:3]]) for y in x] for x in bspline.controlPointsList]
    ctrl_p = [[ifc_p(ifc, y) for y in x] for x in bspline.controlPointsList]
    weightsdata=bspline.weightsData
    ifc.add(ifc.create_entity('IfcRationalBSplineSurfaceWithKnots',
                              UDegree=bspline.uDegree,
                              VDegree=bspline.vDegree,
                              ControlPointsList=ctrl_p,
                              SurfaceForm=bspline.surfaceForm.value,
                              UClosed=False,
                              VClosed=False,
                              UKnots=bspline.uKnots,
                              VKnots=bspline.vKnots,
                              SelfIntersect=False,
                              UMultiplicities=bspline.uMultiplicities,
                              VMultiplicities=bspline.vMultiplicities,
                              WeightsData=bspline.weightsData,
                              KnotSpec='UNSPECIFIED'))

    os.makedirs('temp', exist_ok=True)

    # Sjekk hva som er galt her
    # ifcopenshell.validate.validate(ifc, logger)
    ifc_store.save_to_file('temp/curved_plate.ifc')



# def test_read_bspline_curve_from_sat():
#     file = r'C:\AibelProgs\code\adapy_gsdev_2\tests\core\cadit\sat\curved_plate.sat'
#     sat_reader = SatReaderFactory(file)
#     bsplines = list(sat_reader.iter_bspline_curve_objects())
#     print(bsplines)
#     assert len(bsplines) == 4
#
#     bspline = bsplines[0]
#     assert isinstance(bspline, RationalBSplineCurveWithKnots)
#
#     # IFC export
#     ifc_store = IfcStore()
#     ifc: ifcopenshell.file = ifc_store.f
#     # https://standards.buildingsmart.org/IFC/RELEASE/IFC4_1/FINAL/HTML/schema/ifcgeometryresource/lexical/ifcrationalbsplinesurfacewithknots.htm
#     cplist = bspline.control_points_list
#     # type_check = type(cplist[0][0][0])
#     # list_check = [[[j if i<3 else 3.0 for i,j in enumerate(y)] for y in x] for x in bspline.controlPointsList]
#     # ctrl_p = [[ifc_p(ifc, [j for j in y[0:3]]) for y in x] for x in bspline.controlPointsList]
#     for bspline in bsplines:
#         ctrl_p = [ifc_p(ifc, x) for x in bspline.control_points_list]
#         if isinstance(bspline, RationalBSplineCurveWithKnots):
#             ifc_type = 'IfcRationalBSplineCurveWithKnots'
#             ifc.add(ifc.create_entity(ifc_type,
#                                       Degree=bspline.degree,
#                                       ControlPointsList=ctrl_p,
#                                       CurveForm=bspline.curve_form.value,
#                                       ClosedCurve=bspline.closed_curve,
#                                       SelfIntersect=bspline.self_intersect,
#                                       Knots=bspline.knots,
#                                       KnotMultiplicities=bspline.knot_multiplicities,
#                                       KnotSpec=bspline.knot_spec.value,
#                                       WeightsData=bspline.weightsData))
#         elif isinstance(bspline, BSplineCurveWithKnots):
#             ifc_type = 'IfcBSplineCurveWithKnots'
#             ifc.add(ifc.create_entity(ifc_type,
#                                       Degree=bspline.degree,
#                                       ControlPointsList=ctrl_p,
#                                       CurveForm=bspline.curve_form.value,
#                                       ClosedCurve=bspline.closed_curve,
#                                       SelfIntersect=bspline.self_intersect,
#                                       Knots=bspline.knots,
#                                       KnotMultiplicities=bspline.knot_multiplicities,
#                                       KnotSpec=bspline.knot_spec.value))
#
#     os.makedirs('temp', exist_ok=True)
#
#     # Sjekk hva som er galt her
#     # ifcopenshell.validate.validate(ifc, logger)
#     ifc_store.save_to_file('temp/curved_plate_bsplines.ifc')

# def test_create_bounded_surf_enitity():
#     ifc_store = IfcStore()
#     ifc: ifcopenshell.file = ifc_store.f
#
#     ifc.add(ifc.create_entity('IfcBoundedSurface'))
#
#     os.makedirs('temp', exist_ok=True)
#
#     # Sjekk hva som er galt her
#     # ifcopenshell.validate.validate(ifc, logger)
#     ifc_store.save_to_file('temp/bounded_surface.ifc')
#
#
# def test_write_ifc_plate_from_sat():
#     file = r'C:\AibelProgs\code\adapy_gsdev_2\tests\core\cadit\sat\curved_plate.sat'
#     sat_reader = SatReaderFactory(file)
#     bsplines = list(sat_reader.iter_bspline_curve_objects())
#
#
#
#
#     a = plate.get_assembly()
#     ifc_store = a.ifc_store
#     owner_history = ifc_store.owner_history
#     f = ifc_store.f
#
#     ori = plate.placement.to_axis2placement3d()
#     axis2placement = ifc_placement_from_axis3d(ori, f)
#
#     plate_placement = f.create_entity("IfcLocalPlacement", PlacementRelTo=None, RelativePlacement=axis2placement)
#     representations = []
#
#     solid = extruded_area_solid(plate.solid_geom().geometry, f)
#     body = f.createIfcShapeRepresentation(ifc_store.get_context("Body"), "Body", "SolidModel", [solid])
#     representations.append(body)
#
#     product_shape = f.create_entity("IfcProductDefinitionShape", None, None, representations)
#
#     ifc_plate = f.create_entity(
#         "IfcPlate",
#         plate.guid,
#         owner_history,
#         plate.name,
#         plate.name,
#         None,
#         plate_placement,
#         product_shape,
#         None,
#     )
#
#     # Add colour
#     if plate.color is not None:
#         add_colour(f, solid, str(plate.color), plate.color)
#
#     # Material
#     ifc_store.writer.associate_elem_with_material(plate.material, ifc_plate)
#
#     return ifc_plate