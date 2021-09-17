import datetime
import logging
from operator import attrgetter
from typing import List, Tuple

import numpy as np

from ada.concepts.levels import FEM, Part
from ada.concepts.structural import Beam
from ada.core.utils import Counter, get_current_user, make_name_fem_ready
from ada.fem import Elem, FemSection, Load, Step
from ada.fem.exceptions.element_support import IncompatibleElements
from ada.fem.shapes import ElemType

from .templates import sestra_eig_inp_str, top_level_fem_str


def to_fem(
    assembly,
    name,
    analysis_dir=None,
    metadata=None,
    execute=False,
    run_ext=False,
    cpus=2,
    gpus=None,
    overwrite=False,
    exit_on_complete=False,
):
    if metadata is None:
        metadata = dict()

    if "control_file" not in metadata.keys():
        metadata["control_file"] = None

    parts = list(filter(lambda x: len(x.fem.nodes) > 0, assembly.get_all_subparts()))
    if len(parts) != 1:
        raise ValueError("Sesam writer currently only works for a single part")

    if len(assembly.fem.steps) > 1:
        logging.error("Sesam writer currently only supports 1 step. Will only use 1st step")

    part = parts[0]

    thick_map = dict()

    now = datetime.datetime.now()
    date_str = now.strftime("%d-%b-%Y")
    clock_str = now.strftime("%H:%M:%S")
    user = get_current_user()

    units = "UNITS     5.00000000E+00  1.00000000E+00  1.00000000E+00  1.00000000E+00\n          1.00000000E+00\n"

    inp_file_path = (analysis_dir / f"{name}T1").with_suffix(".FEM")
    if len(assembly.fem.steps) > 0:
        step = assembly.fem.steps[0]
        with open(analysis_dir / "sestra.inp", "w") as f:
            f.write(write_sestra_inp(name, step))

    with open(inp_file_path, "w") as d:
        d.write(top_level_fem_str.format(date_str=date_str, clock_str=clock_str, user=user))
        d.write(units)
        d.write(materials_str(part))
        d.write(sections_str(part.fem, thick_map))
        d.write(univec_str(part.fem))
        d.write(nodes_str(part.fem))
        d.write(mass_str(part.fem))
        d.write(bc_str(part.fem) + bc_str(assembly.fem))
        d.write(hinges_str(part.fem))
        d.write(elem_str(part.fem, thick_map))
        d.write(loads_str(part.fem))
        d.write("IEND                0.00            0.00            0.00            0.00")

    print(f'Created an Sesam input deck at "{analysis_dir}"')


def materials_str(part: Part):
    """

    'TDMATER', 'nfield', 'geo_no', 'codnam', 'codtxt', 'name'
    'MISOSEL', 'matno', 'young', 'poiss', 'rho', 'damp', 'alpha', 'iyield', 'yield'

    :type part: ada.Part
    :return:
    """

    out_str = "".join(
        [write_ff("TDMATER", [(4, mat.id, 100 + len(mat.name), 0), (mat.name,)]) for mat in part.materials]
    )

    out_str += "".join(
        [
            write_ff(
                "MISOSEL",
                [
                    (mat.id, mat.model.E, mat.model.v, mat.model.rho),
                    (mat.model.zeta, mat.model.alpha, 1, mat.model.sig_y),
                ],
            )
            for mat in part.materials
        ]
    )
    return out_str


def sections_str(fem: FEM, thick_map) -> str:
    """

    'TDSECT', 'nfield', 'geono', 'codnam', 'codtxt', 'set_name'
    'GIORH ', 'geono', 'hz', 'ty', 'bt', 'tt', 'bb', 'tb', 'sfy', 'sfz', 'NLOBYT|', 'NLOBYB|', 'NLOBZ|'

    :return:
    """
    from .write_sections import write_bm_section

    sec_str = ""
    sec_ids = []
    names_str = ""
    concept_str = ""
    tdsconc_str, sconcept_str, scon_mesh = "", "", ""
    shid = Counter(1)
    bmid = Counter(1)

    sec_n = Counter(1, "_V")
    sec_names = []
    for fem_sec in fem.sections:
        if fem_sec.type == ElemType.LINE:
            sec = fem_sec.section
            if sec not in sec_ids:
                secid = next(bmid)
                sec_name = make_name_fem_ready(fem_sec.section.name, no_dot=True)
                if sec_name not in sec_names:
                    sec_names.append(sec_name)
                else:
                    sec_name += next(sec_n)
                sec.metadata["numid"] = secid
                names_str += write_ff(
                    "TDSECT",
                    [
                        (4, secid, 100 + len(sec_name), 0),
                        (sec_name,),
                    ],
                )
                sec_ids.append(fem_sec.section)
                sec_str += write_bm_section(sec, secid)

                tdsconc_str_in, sconcept_str_in, scon_mesh_in = write_sconcept(fem_sec)
                tdsconc_str += tdsconc_str_in
                sconcept_str += sconcept_str_in
                scon_mesh += scon_mesh_in
            else:
                logging.info(f'Skipping already included section "{sec}"')
        elif fem_sec.type == ElemType.SHELL:
            if fem_sec.thickness not in thick_map.keys():
                sh_id = next(shid)
                thick_map[fem_sec.thickness] = sh_id
            else:
                sh_id = thick_map[fem_sec.thickness]
            sec_str += write_ff("GELTH", [(sh_id, fem_sec.thickness, 5)])
        else:
            raise IncompatibleElements(f"Solid element type {fem_sec.type} is not yet supported for writing to Sesam")

    return names_str + sec_str + concept_str + tdsconc_str + sconcept_str + scon_mesh


def elem_str(fem: FEM, thick_map) -> str:
    """

    'GELREF1',  ('elno', 'matno', 'addno', 'intno'), ('mintno', 'strano', 'streno', 'strepono'), ('geono', 'fixno',
                'eccno', 'transno'), 'members|'

    'GELMNT1', 'elnox', 'elno', 'eltyp', 'eltyad', 'nids'

    :type fem: ada.fem.FEM
    :param thick_map:

    :return:
    """
    from .reader import eltype_2_sesam

    def write_nodal_data(el: Elem) -> List[Tuple[int]]:
        if len(el.nodes) <= 4:
            return [tuple([e.id for e in el.nodes])]

        nodes = []
        curr_tup = []
        counter = 0
        for n in el.nodes:
            curr_tup.append(n.id)
            counter += 1
            if counter == 4:
                counter = 0
                nodes.append(tuple(curr_tup))
                curr_tup = []

        return nodes + [tuple(curr_tup)]

    out_str = "".join(
        [
            write_ff(
                "GELMNT1",
                [(el.id, el.id, eltype_2_sesam(el.type), 0)] + write_nodal_data(el),
            )
            for el in fem.elements
        ]
    )

    def write_elem(el: Elem) -> str:
        fem_sec = el.fem_sec
        if fem_sec.type == ElemType.LINE:
            sec_id = fem_sec.section.metadata["numid"]
        elif fem_sec.type == ElemType.SHELL:
            sec_id = thick_map[fem_sec.thickness]
        else:
            raise ValueError(f'Unsupported elem type "{fem_sec.type}"')

        fixno = el.metadata.get("fixno", None)
        transno = el.metadata.get("transno")
        if fixno is None:
            last_tuples = [(sec_id, 0, 0, transno)]
        else:
            h1_fix, h2_fix = fixno
            last_tuples = [(sec_id, -1, 0, transno), (h1_fix, h2_fix)]

        return write_ff(
            "GELREF1",
            [
                (el.id, el.fem_sec.material.id, 0, 0),
                (0, 0, 0, 0),
            ]
            + last_tuples,
        )

    for el in fem.elements:
        out_str += write_elem(el)

    return out_str


def nodes_str(fem: FEM) -> str:
    nodes = sorted(fem.nodes, key=attrgetter("id"))

    nids = []
    for n in nodes:
        if n.id not in nids:
            nids.append(n.id)
        else:
            raise Exception('Doubly defined node id "{}". TODO: Make necessary code updates'.format(n[0]))
    if len(nodes) == 0:
        return "** No Nodes"
    else:

        out_str = "".join([write_ff("GNODE", [(no.id, no.id, 6, 123456)]) for no in nodes])
        out_str += "".join([write_ff("GCOORD", [(no.id, no[0], no[1], no[2])]) for no in nodes])
        return out_str


def mass_str(fem: FEM) -> str:
    out_str = ""

    for mass in fem.masses.values():
        for m in mass.fem_set.members:
            if type(mass.mass) in (int, float, np.float64):
                masses = [mass.mass for _ in range(0, 3)] + [0, 0, 0]
            else:
                raise NotImplementedError()
            data = (tuple([m.id, 6] + masses[:2]), tuple(masses[2:]))
            out_str += write_ff("BNMASS", data)
    return out_str


def bc_str(fem: FEM) -> str:
    out_str = ""
    for bc in fem.bcs:
        for m in bc.fem_set.members:
            dofs = [1 if i in bc.dofs else 0 for i in range(1, 7)]
            data = [tuple([m.id, 6] + dofs[:2]), tuple(dofs[2:])]
            out_str += write_ff("BNBCD", data)
    return out_str


def hinges_str(fem: FEM) -> str:
    out_str = ""
    h = Counter(1)

    def write_hinge(hinge):
        dofs = [0 if i in hinge else 1 for i in range(1, 7)]
        fix_id = next(h)
        data = [tuple([fix_id, 3, 0, 0]), tuple(dofs[:4]), tuple(dofs[4:])]
        return fix_id, write_ff("BELFIX", data)

    for el in fem.elements:
        h1, h2 = el.metadata.get("h1", None), el.metadata.get("h2", None)
        if h2 is None and h1 is None:
            continue
        h1_fix, h2_fix = 0, 0
        if h1 is not None:
            h1_fix, res_str = write_hinge(h1)
            out_str += res_str
        if h2 is not None:
            h2_fix, res_str = write_hinge(h2)
            out_str += res_str
        el.metadata["fixno"] = h1_fix, h2_fix

    return out_str


def univec_str(fem: FEM) -> str:
    out_str = ""
    uvec_id = Counter(1)

    unit_vecs = dict()

    def write_local_z(vec):
        tvec = tuple(vec)
        if tvec in unit_vecs.keys():
            return unit_vecs[tvec], None
        trans_no = next(uvec_id)
        data = [tuple([trans_no, *vec])]
        unit_vecs[tvec] = trans_no
        return trans_no, write_ff("GUNIVEC", data)

    for el in fem.elements:
        local_z = el.fem_sec.local_z
        transno, res_str = write_local_z(local_z)
        if res_str is None:
            el.metadata["transno"] = transno
            continue
        out_str += res_str
        el.metadata["transno"] = transno

    return out_str


def loads_str(fem: FEM) -> str:
    loads = fem.steps[0].loads if len(fem.steps) > 0 else []
    out_str = ""
    for i, l in enumerate(loads):
        assert isinstance(l, Load)
        lid = i + 1
        out_str += write_ff("TDLOAD", [(4, lid, 100 + len(l.name), 0), (l.name,)])
        if l.type in ["acc", "grav"]:
            out_str += write_ff(
                "BGRAV",
                [(lid, 0, 0, 0), tuple([x * l.magnitude for x in l.acc_vector])],
            )
    return out_str


def write_ff(flag, data):
    """
    flag = NCOD
    data = [(int, float, int, float), (float, int)]

    ->> NCOD    INT     FLOAT       INT     FLOAT
                FLOAT   INT

    :param flag:
    :param data:
    :return:
    """

    def write_data(d):
        if type(d) in (np.float64, float, int, np.uint64, np.int32) and d >= 0:
            return f"  {d:<14.8E}"
        elif type(d) in (np.float64, float, int, np.uint64, np.int32) and d < 0:
            return f" {d:<15.8E}"
        elif type(d) is str:
            return d
        else:
            raise ValueError(f"Unknown input {type(d)} {d}")

    out_str = f"{flag:<8}"
    for row in data:
        v = [write_data(x) for x in row]
        if row == data[-1]:
            out_str += "".join(v) + "\n"
        else:
            out_str += "".join(v) + "\n" + 8 * " "
    return out_str


def write_sestra_inp(name, step: Step):
    step_map = {Step.TYPES.EIGEN: write_sestra_eig_str}
    step_str_writer = step_map.get(step.type, None)
    if step_str_writer is None:
        raise ValueError(f'Step type "{step.type}" is not supported yet for Ada-Sestra ')
    return step_str_writer(name, step)


def write_sestra_eig_str(name: str, step: Step):
    now = datetime.datetime.now()
    date_str = now.strftime("%d-%b-%Y")
    clock_str = now.strftime("%H:%M:%S")
    user = get_current_user()
    return sestra_eig_inp_str.format(
        name=name, modes=step.eigenmodes, date_str=date_str, clock_str=clock_str, user=user
    )


concept = Counter(1)
concept_ircon = Counter(1)


def write_sconcept(fem_sec: FemSection) -> Tuple[str, str, str]:
    sconcept_str = ""
    # Give concept relationship based on inputted values
    beams = [x for x in fem_sec.refs if type(x) is Beam]
    if len(beams) != 1:
        raise ValueError("A FemSection cannot be sourced from multiple beams")
    beam = beams[0]

    fem_sec.metadata["ircon"] = next(concept_ircon)
    bm_name = make_name_fem_ready(beam.name, no_dot=True)
    tdsconc_str = write_ff(
        "TDSCONC",
        [(4, fem_sec.metadata["ircon"], 100 + len(bm_name), 0), (bm_name,)],
    )
    sconcept_str += write_ff("SCONCEPT", [(8, next(concept), 7, 0), (0, 1, 0, 2)])
    sconc_ref = next(concept)
    sconcept_str += write_ff("SCONCEPT", [(5, sconc_ref, 2, 4), (1,)])
    elids: List[tuple] = []
    i = 0

    numel = len(beam.elem_refs)
    elid_bulk = [numel]
    for el in fem_sec.elset.members:
        if i == 3:
            elids.append(tuple(elid_bulk))
            elid_bulk = []
            i = -1
        elid_bulk.append(el.id)
        i += 1
    if len(elid_bulk) != 0:
        elids.append(tuple(elid_bulk))

    mesh_args = [(5 + numel, sconc_ref, 1, 2)] + elids
    scon_mesh = write_ff("SCONMESH", mesh_args)
    return tdsconc_str, sconcept_str, scon_mesh
