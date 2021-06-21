"""
Tools to analyse the generation of the structures
"""
import traceback
import logging
import cProfile
import pstats
import io
from pstats import SortKey
import tqdm
import numpy as np
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.outputs import Chgcar
from pymatgen.io.vasp.inputs import Poscar
from monty.dev import requires
from randomcarbon.evolution.core import Evolver

try:
    from pymatgen.analysis.diffusion.aimd.pathway import ProbabilityDensityAnalysis
except ImportError:
    ProbabilityDensityAnalysis = None

logger = logging.getLogger(__name__)


@requires(ProbabilityDensityAnalysis, "the pymatgen diffusion plugin is required: https://github.com/materialsvirtuallab/pymatgen-diffusion")
def distribution_density(evolver: Evolver, template: Structure, current: Structure = None,
                         n_generated: int = 300, interval: float = 0.5, filepath: str = "CHGCAR",
                         profile=False) -> Chgcar:
    """
    Utility function that uses the evolver to generate several new atoms, starting from the same initial structure,
    and generates a CHGCAR file that contains the probability distribution of the generated atoms.
    Useful to inspect where the atoms are being generated.

    The CHGCAR will use as a base structure the "current", if not None, else the template.

    Args:
        evolver: The Evolver used to generate the new structures. It is expected to add new atoms and that
            the new atoms will be the last sites in the structure.
        template: a pymatgen Structure defining the template.
        current: a Structure to which the new atoms will be added. If None a new structure will be
            generated.
        n_generated: the number of times the evolver is called to generate new points.
        interval: the interval between two nearest grid points (in Angstrom), used to generate the
            density grid. Passed to ProbabilityDensityAnalysis.
        filepath: the path where the CHGCAR should be written. If None, no file will be written
        profile: if True a profile of the run time will be written in the log with level INFO.

    Returns:
        the instance of the Chgcar generated.
    """

    if profile:
        pr = cProfile.Profile()
        pr.enable()

    fcoords = []
    for i in tqdm.tqdm(range(n_generated)):

        try:
            new_s = evolver.evolve(current)

            if not new_s:
                logger.warning(f"at iteration {i} no structure was generated")
                continue

            if current is not None:
                for s in new_s:
                    fcoords.extend(s.frac_coords[len(current):])
            else:
                for s in new_s:
                    fcoords.extend(s.frac_coords)

        except:
            logger.warning(f"error {i}: ", traceback.format_exc())

    if profile:
        pr.disable()
        str_stats = io.StringIO()
        sortby = SortKey.CUMULATIVE
        ps = pstats.Stats(pr, stream=str_stats).sort_stats(sortby)
        ps.print_stats()
        logger.info(str_stats.getvalue())

    fcoords = np.reshape(fcoords, (len(fcoords), 1, 3))

    # the object is generated with just one atom. Create a fake structure
    tmp_s = Structure(lattice=template.lattice, coords=fcoords[0], species=["C"], coords_are_cartesian=False)
    pda = ProbabilityDensityAnalysis(structure=tmp_s, trajectories=fcoords, species=["C"], interval=interval)

    # generate a Chgcar object since :
    # 1) the CHGCAR generated by pda does not seem to be fully compatible with a real CHGCAR
    # 2) it is easier to directly add the full structure
    s_init = current if current is not None else template
    chgcar = Chgcar(Poscar(s_init), {"total": pda.Pr})
    chgcar.write_file(filepath)

    return chgcar
