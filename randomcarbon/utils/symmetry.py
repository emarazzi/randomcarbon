from typing import Tuple, List, Optional, Union
from monty.dev import requires
from pymatgen.core.structure import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.core.operations import SymmOp
from pymatgen.analysis.structure_matcher import StructureMatcher
from randomcarbon.utils.structure import add_new_symmetrized_atom
try:
    import pyxtal
except ImportError:
    pyxtal = None


@requires(pyxtal, "pyxtal should be installed")
def get_subgroup_structure(structure: Structure, spgn: int = None, idx: int = None,
                           eps: float = 1e-5, group_type: str = 't', primitive: bool = False,
                           symprec: float = 0.001, angle_tolerance: float = 5.0,
                           expected_initial_spgn: int = None) -> Tuple[Structure, List[SymmOp]]:
    """
    Uses the pyxtal module to generate an equivalent of the input structure but belonging
    to the subgroup and the corresponding symmetry operations. This is done by breaking
    the symmetry by an amount specified by eps. eps can be exactly 0.0 only if "primitive"
    is False and the subgroup has a different lattice than the original one. In the
    latter case no error will be raised but the list of SymmOp will generate structures
    belonging to the original group.
    Note that since the structure is generated with some randomic process inside pyxtal
    the generation may sometimes fail. Simply rerunning could fix the issue.

    Args:
        structure: the original structure from which to extract the subgroup and
            symmetry operations.
        spgn: the target spacegroup number. Should be one of the maximum subgroups of
            the original structure.
        idx: specify the index of the spacegroup in the list provided by pyxtal.
            Useful in case of different ways to transform from one group to the same
            subgroup.
        eps: the amount by which the symmetry will be broken. Both the atomic positions
            and lattice parameters.
        group_type: the type of subgroup. Should be "t" or "k".
        primitive: if True the primitive will be returned instead of the conventional.
        symprec: spglib symprec. Used to identify the symmetry of the initial structure.
        angle_tolerance: spglib angle_tolerance. Used to identify the symmetry of the
.            initial structure
        expected_initial_spgn: if not None it will be used to check that the space group
            of the initial structure has been identified correctly.

    Returns:
        a tuple with the conventional/primitive structure with the subgroup symmetry and
        the corresponding list of SymmOp.
    """
    if primitive and eps == 0.0:
        raise ValueError("to determine the primitive structure eps should be greater than 0")

    if idx is not None:
        idx = [idx]

    c = pyxtal.pyxtal()
    c.from_seed(structure, tol=symprec, a_tol=angle_tolerance)
    if expected_initial_spgn is not None and c.group.number != expected_initial_spgn:
        raise RuntimeError(f"pyxtal identified the space group {c.group.number}. "
                           f"Try to tune the value of symprec.")

    c_sub = c.subgroup(H=spgn, idx=idx, eps=eps, group_type=group_type)[0]
    sub_struct = c_sub.to_pymatgen()
    if spgn is None:
        spgn = c_sub.group.number

    if primitive:
        for i in range(1, 9):
            symprec_sub = eps * 2**i / 16
            spga = SpacegroupAnalyzer(sub_struct, symprec=symprec_sub)
            try:
                tmp_spgn = spga.get_space_group_number()
                if tmp_spgn is not None and tmp_spgn == spgn:
                    sub_struct = spga.get_primitive_standard_structure()
                    spga = SpacegroupAnalyzer(sub_struct, symprec=symprec_sub)
                    assert spga.get_space_group_number() == spgn
                    break
            except ValueError:
                # the spga can raise an exception if spglib fails to retrieve the number.
                pass
        else:
            raise RuntimeError("Could not find a value of symprec that matches the original space group")
    else:
        spga = SpacegroupAnalyzer(sub_struct, symprec=symprec)

    sym_ops = spga.get_symmetry_operations()

    return sub_struct, sym_ops


def validate_subgroup(structure_orig: Structure, structure_sub: Structure, symm_ops: List[SymmOp],
                      sub_spgn: int, ltol: float = 0.001, stol: float = 0.001,
                      angle_tol: float = 1, symprec: float = 0.001) -> Optional[str]:
    """
    Helper function to validate the structure and list of SymmOp generated by the get_subgroup_structure
    function. Checks if the original structure and the generated structure match with the
    StructureMatcher and that when generating new structures with add_new_symmetrized_atom
    they will belong to the subgroup.

    Args:
        structure_orig: the original structure used to generate the subgroup structure.
        structure_sub: the structure belonging to the subgroup.
        symm_ops: the symmetry operations to generate a structure belonging to the subgroup.
        sub_spgn: the space group number of the subgroup.
        ltol: ltol value passed to the StructureMatcher.
        stol: stol value passed to the StructureMatcher.
        angle_tol: angle_tol value passed to the StructureMatcher.
        symprec: symprec value used in the SpacegroupAnalyzer to identify the space group
            of the test structures generated internally.

    Returns:
        a string with the error encountered, if any, None otherwise.
    """
    sm = StructureMatcher(ltol=ltol, angle_tol=angle_tol, stol=stol, primitive_cell=True)
    if not sm.fit(structure_orig, structure_sub):
        return "structures do not fit"

    for i in range(10):
        s = add_new_symmetrized_atom(template=structure_sub, symm_ops=symm_ops)
        spga = SpacegroupAnalyzer(s, symprec=symprec)
        if spga.get_space_group_number() == sub_spgn:
            break
    else:
        return f"generated structures do not belong to the spacegroup {sub_spgn}"

    return None


@requires(pyxtal, "pyxtal should be installed")
def get_subgroups(spgn: int, recursive: bool = False, group_type: str = 't') -> Union[List, dict]:
    """
    Gives the maximum subgroups for a specific group or a structure as provided by pyxtal.
    If recursive a nested dictionary with the recursive subgroups is returned.

    Args:
        spgn: the space group number.
        recursive: if True the recursive dict is returned.
        group_type: the type of subgroup. Should be "t" or "k".

    Returns:
        list of maximal subgroups or dictionary with all subgroups.
    """

    group = pyxtal.symmetry.Group(spgn)

    if group_type == "t":
        subgroups = group.get_max_t_subgroup()["subgroup"]
    elif group_type == "k":
        subgroups = group.get_max_k_subgroup()["subgroup"]
    else:
        raise ValueError("group_type should be either 't' or 'k'")

    if recursive:
        subgroups_dict = {}
        for sg in subgroups:
            # some subgroups can be listed more than once.
            if sg not in subgroups_dict:
                subgroups_dict[sg] = get_subgroups(spgn=sg, recursive=True, group_type=group_type)

        return subgroups_dict
    else:
        return subgroups
