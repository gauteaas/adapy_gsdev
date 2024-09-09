import logging
import os

import ifcopenshell.validate

from ada.api.primitives import RationalBSplineSurfaceWithKnots
from ada.cadit.ifc.utils import ifc_p
from ada.cadit.sat.store import SatReaderFactory
from ada.cadit.ifc.store import IfcStore
from ada.config import logger


def test_read_a_bspline():
    sat_reader = SatReaderFactory('bspline_2.sat')
    bsplines = list(sat_reader.iter_bspline_objects())
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
    ctrl_p = [[ifc_p(ifc, [j for j in y[0:3]]) for y in x] for x in bspline.controlPointsList]
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
