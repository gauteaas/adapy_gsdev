import logging
import os

import ifcopenshell.validate

from ada.api.primitives import RationalBSplineSurfaceWithKnots
from ada.cadit.ifc.utils import ifc_p
from ada.cadit.sat.store import SatReaderFactory
from ada.cadit.ifc.store import IfcStore
from ada.config import logger


def test_read_a_curved_plate_2():
    file = r'C:\AibelProgs\code\adapy_gsdev_2\tests\core\cadit\sat\curved_plate.sat'
    # file= r'C:\DNV\Workspaces\GeniE\test_plate\test_plateT1_abq.SAT'
    # file = r'C:\AibelProgs\projects\ifc_curved_plate\wcs_transition_plate\wc_transition_pl.SAT'
    sat_reader = SatReaderFactory(file)
    ifc_store = list(sat_reader.iter_curved_plate_objects())

    os.makedirs('temp', exist_ok=True)

    # Sjekk hva som er galt her
    store: IfcStore = ifc_store[0]
    ifc_logger = logging.getLogger("validate")
    ifc_logger.setLevel(logging.DEBUG)
    ifcopenshell.validate.validate(store.f, ifc_logger, express_rules=True)
    # ifc_store[0].save_to_file('temp/curved_plate_2.ifc')
    ifc_store[0].save_to_file(f'{file[:-4]}.ifc')
    # ifcopenshell.validate.validate(r'C:\AibelProgs\code\adapy_gsdev_2\tests\temp\curved_plate_2_mod3.ifc', ifc_logger)
