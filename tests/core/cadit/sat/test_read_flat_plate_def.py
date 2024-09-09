import ada
from ada.cadit.sat.store import SatReaderFactory


def test_read_a_flat_plate(example_files):
    sat_reader = SatReaderFactory(example_files / "sat_files/flat_plate_abaqus_1x1.sat")
    faces = list(sat_reader.iter_flat_plates())
    print(faces)
    assert len(faces) == 1
    name, points = faces[0]
    pl = ada.Plate(name, points, 0.01)

    a = ada.Assembly() / pl
    a.to_ifc('temp/my_flat_plate.ifc')
