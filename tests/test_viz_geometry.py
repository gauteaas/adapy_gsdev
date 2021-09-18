import unittest

from common import build_test_simplestru_fem, dummy_display

from ada import Assembly, Beam, Plate


class VisualizeTests(unittest.TestCase):
    def test_viz(self):
        a = Assembly("my_test_assembly")
        a.add_beam(Beam("bm1", n1=[0, 0, 0], n2=[2, 0, 0], sec="IPE220", colour="red"))
        a.add_beam(Beam("bm2", n1=[0, 0, 1], n2=[2, 0, 1], sec="HP220x10", colour="blue"))
        a.add_beam(Beam("bm3", n1=[0, 0, 2], n2=[2, 0, 2], sec="BG800x400x20x40", colour="green"))
        a.add_beam(Beam("bm4", n1=[0, 0, 3], n2=[2, 0, 3], sec="CIRC200", colour="green"))
        a.add_beam(Beam("bm5", n1=[0, 0, 4], n2=[2, 0, 4], sec="TUB200x10", colour="green"))
        a.add_plate(
            Plate(
                "pl1",
                [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
                0.01,
                use3dnodes=True,
            )
        )
        dummy_display(a)

    def test_module(self):
        param_model = build_test_simplestru_fem()
        a = Assembly("ParametricSite") / param_model
        dummy_display(a)


if __name__ == "__main__":
    unittest.main()
