from itertools import groupby
from operator import attrgetter
from typing import Iterable

from ada.fem import Elem, FemSection
from ada.fem.containers import FemElements
from ada.fem.formats.abaqus.write.write_elements import write_elem
from ada.fem.shapes import ElemShape
from ada.sections import SectionCat as Sc


def elements_str(fem_elements: FemElements) -> str:
    if len(fem_elements) == 0:
        return "** No elements"

    el_str = ""
    for (el_type, fem_sec), elements in groupby(fem_elements, key=attrgetter("type", "fem_sec")):
        el_str += elwriter(el_type, fem_sec, elements)

    return el_str


def elwriter(eltype, fem_sec: FemSection, elements: Iterable[Elem]):

    if "connector" in eltype:
        return None

    sub_eltype = el_type_sub(eltype, fem_sec)
    el_set_str = f", ELSET={fem_sec.elset.name}" if fem_sec.elset is not None else ""
    el_str = "\n".join((write_elem(el, True) for el in elements))

    return f"""*ELEMENT, type={sub_eltype}{el_set_str}\n{el_str}\n"""


def el_type_sub(el_type, fem_sec: FemSection) -> str:
    """Substitute Element types specifically Calculix"""

    if el_type in ElemShape.TYPES.lines.all:
        if must_be_converted_to_general_section(fem_sec.section.type):
            return "U1"
    if el_type == ElemShape.TYPES.shell.TRI6:
        return "S6"
    fem = fem_sec.parent
    return fem.options.ABAQUS.default_elements.get_element_type(el_type)


def must_be_converted_to_general_section(sec_type):
    if sec_type in Sc.circular + Sc.igirders + Sc.iprofiles + Sc.general + Sc.angular:
        return True
    else:
        return False
