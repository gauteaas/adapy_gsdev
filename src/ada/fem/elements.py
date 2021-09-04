from __future__ import annotations

import logging

import numpy as np

from ada.concepts.points import Node

from .common import Csys, FemBase
from .sections import FemSection
from .shapes import ElemShapes


class Elem(FemBase):
    """"""

    def __init__(
        self,
        el_id,
        nodes,
        el_type,
        elset=None,
        fem_sec=None,
        mass_props=None,
        parent=None,
        metadata=None,
    ):
        """:type fem_sec: ada.fem.FemSection"""
        super(Elem, self).__init__(el_id, metadata, parent)
        self.type = el_type.upper()
        self._el_id = el_id
        self._shape = None

        if type(nodes[0]) is Node:
            for node in nodes:
                node.refs.append(self)

        self._nodes = nodes
        self._elset = elset
        self._fem_sec = fem_sec
        self._mass_props = mass_props
        self._refs = []

    @property
    def type(self):
        """Element type"""
        return self._el_type

    @type.setter
    def type(self, value):
        from .shapes import ElemShapes

        if ElemShapes.is_valid_elem(value) is False:
            raise ValueError(f'Currently unsupported element type "{value}".')
        self._el_type = value.upper()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def id(self):
        return self._el_id

    @id.setter
    def id(self, value):
        if type(value) not in (np.int32, int, np.uint64) and issubclass(type(self), Connector) is False:
            raise ValueError(f'Element ID "{type(value)}" must be numeric')
        self._el_id = value

    @property
    def nodes(self):
        return self._nodes

    @property
    def elset(self):
        return self._elset

    @property
    def fem_sec(self) -> FemSection:
        return self._fem_sec

    @fem_sec.setter
    def fem_sec(self, value):
        self._fem_sec = value

    @property
    def mass_props(self):
        """

        :return:
        :rtype: ada.fem.Mass
        """
        return self._mass_props

    @mass_props.setter
    def mass_props(self, value):
        self._mass_props = value

    @property
    def shape(self) -> ElemShapes:

        if self._shape is None:
            self._shape = ElemShapes(self.type, self.nodes)
        return self._shape

    @property
    def refs(self):
        return self._refs

    def update(self):
        from toolz import unique

        self._nodes = list(unique(self.nodes))
        if len(self.nodes) <= 1:
            self._el_id = None
        else:
            self._shape = None

    def __repr__(self):
        return f'Elem(ID: {self._el_id}, Type: {self.type}, NodeIds: "{self.nodes}")'


class Connector(Elem):
    """
    A Connector Element

    :param name:
    :param con_type:
    :param con_sec:
    :param el_id:
    :param n1:
    :param n2:
    :param csys:

    :type n1: ada.Node
    :type n2: ada.Node
    :type con_sec: ConnectorSection
    :type csys: Csys
    """

    def __init__(
        self,
        name,
        el_id,
        n1,
        n2,
        con_type,
        con_sec,
        preload=None,
        csys=None,
        metadata=None,
        parent=None,
    ):
        from ada import Node

        if type(n1) is not Node or type(n2) is not Node:
            raise ValueError("Connector Start\\end must be nodes")
        super(Connector, self).__init__(el_id, [n1, n2], "CONNECTOR")
        super(Elem, self).__init__(name, metadata, parent)
        self._n1 = n1
        self._n2 = n2
        self._con_type = con_type
        self._con_sec = con_sec
        self._preload = preload
        self._csys = csys if csys is not None else Csys(f"{name}_csys")

    @property
    def con_type(self):
        return self._con_type

    @property
    def con_sec(self):
        """

        :return:
        :rtype: ConnectorSection
        """
        return self._con_sec

    @property
    def n1(self):
        """

        :return:
        :rtype: ada.Node
        """
        return self._n1

    @property
    def n2(self):
        """

        :return:
        :rtype: ada.Node
        """
        return self._n2

    @property
    def csys(self):
        """

        :return:
        :rtype: Csys
        """
        return self._csys

    def __repr__(self):
        return f'ConnectorElem(ID: {self.id}, Type: {self.type}, End1: "{self.n1}", End2: "{self.n2}")'


class Spring(Elem):
    """

    :param name:
    :param el_id:
    :param el_type:
    :param stiff:
    :param n1:
    :param n2:
    :param metadata:
    :param parent:
    """

    def __init__(self, name, el_id, el_type, stiff, n1, n2=None, metadata=None, parent=None):
        from .sets import FemSet

        nids = [n1]
        if n2 is not None:
            nids += [n2]
        super(Spring, self).__init__(el_id, nids, el_type)
        super(Elem, self).__init__(name, metadata, parent)
        self._stiff = stiff
        self._n1 = n1
        self._n2 = n2
        self._fem_set = FemSet(self.name + "_set", [el_id], "elset")
        if self.parent is not None:
            self.parent.sets.add(self._fem_set)

    @property
    def fem_set(self):
        return self._fem_set

    @property
    def stiff(self):
        return self._stiff

    def __repr__(self):
        return f'Spring("{self.name}", type="{self._stiff}")'


class Mass(FemBase):
    """

    :param name: Name of set
    :param fem_set: Fem Set (of element or nodal type)
    :type fem_set: FemSet
    :param mass: Mass magnitude
    :param mass_type: Type of mass. See _valid_types. Default is 'MASS'
    :param ptype: Point mass type. Can be None, 'Isotropic' or 'Anisotropic'
    :param units:
    :param metadata:
    :param parent:

    """

    _valid_types = ["MASS", "NONSTRUCTURAL MASS", "ROTARY INERTIA"]
    _valid_ptypes = [None, "ISOTROPIC", "ANISOTROPIC"]

    def __init__(
        self,
        name,
        fem_set,
        mass,
        mass_type=None,
        ptype=None,
        units=None,
        metadata=None,
        parent=None,
    ):
        super().__init__(name, metadata, parent)
        self._fem_set = fem_set
        if mass is None:
            raise ValueError("Mass cannot be None")
        if type(mass) not in (list, tuple):
            logging.info(f"Mass {type(mass)} converted to list of len=1. Assume equal mass in all 3 transl. DOFs.")
            mass = [mass]
        self._mass = mass
        self._mass_type = mass_type if mass_type is not None else "MASS"
        if self.type not in Mass._valid_types:
            raise ValueError(f'Mass type "{self.type}" is not in list of supported types {self._valid_types}')
        if ptype not in self._valid_ptypes:
            raise ValueError(f'Mass point type "{ptype}" is not in list of supported types {self._valid_ptypes}')
        self.point_mass_type = ptype
        self._units = units

    @property
    def type(self):
        return self._mass_type.upper()

    @property
    def fem_set(self):
        """
        :rtype: FemSet
        """
        return self._fem_set

    @property
    def mass(self):
        if self.point_mass_type is None:
            if self.type == "MASS":
                if type(self._mass) in (list, tuple):
                    raise ValueError("Mass can only be a scalar number for Isotropic mass")
                return float(self._mass[0])
            elif self.type == "NONSTRUCTURAL MASS":
                return self._mass
            else:
                return float(self._mass)
        elif self.point_mass_type == "ISOTROPIC":
            if (len(self._mass) == 1) is False:
                raise ValueError("Mass can only be a scalar number for Isotropic mass")
            return self._mass[0]
        elif self.point_mass_type == "ANISOTROPIC":
            if (len(self._mass) == 3) is False:
                raise ValueError("Mass must be specified for 3 dofs for Anisotropic mass")
            return self._mass
        else:
            raise ValueError(f'Unknown mass input "{self.type}"')

    @property
    def units(self):
        return self._units

    @property
    def point_mass_type(self):
        return self._ptype

    @point_mass_type.setter
    def point_mass_type(self, value):
        self._ptype = value

    def __repr__(self):
        return f"Mass({self.name}, {self.point_mass_type}, [{self.mass}])"
