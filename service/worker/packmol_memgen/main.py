#!/usr/bin/env python

import argparse
import atexit
import json
import logging
import math
import os
import random
import shutil
import signal
import string
import subprocess
import sys
import tarfile

import pandas as pd

script_path = os.path.abspath(os.path.dirname(__file__))+os.path.sep
from argparse import RawDescriptionHelpFormatter

# Use package-relative imports when available (installed package or web app),
# fall back to bare imports for standalone script execution.
try:
    from .lib.amber import (
        HMassRepartition, amber_ion_dict, amber_minimize, exe_suffix,
        prepare_leap, reduce_protonate, reduce_trim, sirah_cgconv,
    )
    from .lib.charmmlipid2amber.amberlipid2charmm import amberlipid2charmm
    from .lib.pdbremix import pdbatoms
    from .lib.pdbremix.lib.docopt import docopt
    from .lib.pdbremix.rmsd import rmsd_of_pdbs
    from .lib.pdbremix.volume import volume
    from .lib.utils import (
        GG_res, MGG_ring_probe, DGG_ring_probe, PI_ring_probe, PI_res,
        MembraneParams, VCH, VCH2, avogadro, cif_to_pdb,
        distribute_integer, find_piercing_lipids, is_number,
        pdb_parse, pdb_parse_TER, pdb_write, pdb2pqr_protonate,
        pdb2pqr as pdb2pqr_exe,
        remove_piercing_lipids, ring_lipid_endings, rotate_pdb,
        sphere_dist, sphere_integral, sphere_integral_square,
        sphere_rectangle_area, gauss_integral_square, gauss_rectangle_area,
        sterols_rings, superimpose_pdb, translate_pdb,
    )
    from .lib import tqdm
except ImportError:
    sys.path.append(script_path)
    from lib.amber import (
        HMassRepartition, amber_ion_dict, amber_minimize, exe_suffix,
        prepare_leap, reduce_protonate, reduce_trim, sirah_cgconv,
    )
    from lib.charmmlipid2amber.amberlipid2charmm import amberlipid2charmm
    from lib.pdbremix import pdbatoms
    from lib.pdbremix.lib.docopt import docopt
    from lib.pdbremix.rmsd import rmsd_of_pdbs
    from lib.pdbremix.volume import volume
    from lib.utils import (
        GG_res, MGG_ring_probe, DGG_ring_probe, PI_ring_probe, PI_res,
        MembraneParams, VCH, VCH2, avogadro, cif_to_pdb,
        distribute_integer, find_piercing_lipids, is_number,
        pdb_parse, pdb_parse_TER, pdb_write, pdb2pqr_protonate,
        pdb2pqr as pdb2pqr_exe,
        remove_piercing_lipids, ring_lipid_endings, rotate_pdb,
        sphere_dist, sphere_integral, sphere_integral_square,
        sphere_rectangle_area, gauss_integral_square, gauss_rectangle_area,
        sterols_rings, superimpose_pdb, translate_pdb,
    )
    from lib import tqdm

#CHECK CHANGELOG IN README.rst

logger = logging.getLogger("pmmg_log")


def build_parser(short_help=False):
    """Build and return the argument parser for packmol-memgen.

    Args:
        short_help: If True, suppress advanced arguments (shown with -h).
                    If False, show all arguments (shown with --help).

    Returns:
        argparse.ArgumentParser: Configured parser with all arguments.
    """
    try:
        columns = str(shutil.get_terminal_size()[0])
    except Exception:
        try:
            from backports.shutil_get_terminal_size import get_terminal_size
            columns = str(get_terminal_size()[0])
        except ImportError:
            columns = "80"

    explanation = """The script creates an input file for PACKMOL for creating a bilayer system with a protein inserted in it. The input pdb file will be protonated and oriented by default by using reduce and MEMEMBED; the user is encouraged to check the input and output files carefully!  If the protein is preoriented, for example by using PPM webserver from OPM (http://opm.phar.umich.edu/server.php), be sure to set the corresponding flag (--preoriented).  In some cases the packed system might crash during the first MD step, specially when the system is minimized by using pmemd GPU code (cudaFree Memory allocation error). It's highly recommended that the minimization steps are performed on cpus (--minimize), but also changes in the box boundaries or repacking with --random as an argument might help.

 If you use this script, please cite:

    **Schott-Verdugo, S and Gohlke, H, PACKMOL-Memgen: A Simple-To-Use, Generalized Workflow for Membrane-Protein-Lipid-Bilayer System Building, Journal of Chemical Information and Modeling,  59, 6, 2522-2528., 2019

    depending on the options used, you should also cite and/or acknowledge:

    PACKMOL:    **Leandro Martinez (L. Martinez, R. Andrade, E. G. Birgin, J. M. Martinez. Packmol: A package for building initial configurations for molecular dynamics simulations. Journal of Computational Chemistry, 30(13):2157-2164, 2009.)
    MEMEMBED:   **Tim Nugent (Nugent T, Jones DT. Membrane protein orientation and refinement using a knowledge-based statistical potential. BMC Bioinformatics. 2013 Sep 18;14:276.)
    PPM3:       **Andrei Lomize (Lomize, A. L., Todd, S. C., & Pogozheva, I. D. Spatial arrangement of proteins in planar and curved membranes by PPM 3.0. Protein Science, 31(1), 209-220, 2022.)
    **Bosco K. Ho (http://boscoh.com/ ; https://github.com/boscoh/pdbremix)
    **Benjamin D. Madej (charmmlipid2amber.py)

"""

    explanation = explanation+"-"*int(columns)

    parser = argparse.ArgumentParser(prog="packmol-memgen", description = explanation, add_help=False, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument("-h",     action="help", help="prints this help message and exits" if short_help else "prints a short help message and exits")
    parser.add_argument("--help", action="help", help="prints an extended help message and exits" if short_help else "prints this help message and exits")
    parser.add_argument("--available_lipids",action="store_true",     help="list of available lipids and corresponding charges")
    parser.add_argument("--available_lipids_all",action="store_true", help="list all lipids including experimental. Huge output (>4000 lines)! Think about grepping the lipid you want (packmol-memgen --available_lipids_all | grep YOUR_LIPID_PATTERN)")
    parser.add_argument("--available_solvents",action="store_true",     help="list of available solvents and corresponding charges")
    parser.add_argument("--available_ions",action="store_true",     help="list of available ions and corresponding charges")
    parser.add_argument("-l","--lipids",action="append",metavar="LIP1:LIP2//LIP3",help="Lipid(s) to be used for embeding the protein. It should be a single string separated by ':' . If different composition is used in leaflets, add '//' as a separator.[ex. CHL1:DOPC//DOPE for a lower leaflet with CHL1+DOPC and an upper leaflet with DOPE]. Can be defined multiple times for multi-bilayer systems (stacks 'up' or 'outside')")
    parser.add_argument("-r","--ratio",action="append",metavar="R1:R2//R3", help="mixture ratio (set to 1 if only one lipid required). Must be in the same order and syntax as in lipids, and defined once per bilayer [ex. 1:2//1] ")
    parser.add_argument("-n","--lipnum",action="append",metavar="R1:R2//R3",help="number of lipids instead of ratio. Must be in the same order and syntax as in lipids, and defined once per bilayer [ex. 1:2//1] ")
    parser.add_argument("--solvents",type=str,    metavar="SOL1:SOL2",help="Solvent(s) to be used for the packing. As lipids, it should be a single string separated by ':'. Water by default.")
    parser.add_argument("--solvent_ratio",type=str,metavar="SR1:SR2", help="mixture ratio (set to 1 if only one solvent required). Must be in the same order and syntax as in solvents")
    parser.add_argument("--dist",         type=float, default=15.0,   help=argparse.SUPPRESS if short_help else "specify the minimum distance between the maxmin values for x y and z to the box boundaries. Default = 15 A. Worst case scenario is considered, so real distance could be larger")
    parser.add_argument("--dist_wat", type=float, default=17.5,       help=argparse.SUPPRESS if short_help else "specify the width of the water layer over the membrane or protein in the z axis. Default = 17.5")
    parser.add_argument("--distxy_fix",   type=float,                 help="specify the membrane patch side length in the x and y axis. Useful when only lipids are packed! By default is calculated flexibly depending on the protein")
    parser.add_argument("--watorient", action="store_true",           help=argparse.SUPPRESS if short_help else "use 1.5 radius in packmol for water oxygen, to foster water orientation. Might help for packing particularly big water systems")
    parser.add_argument("--noxy_cen",     action="store_false",       help=argparse.SUPPRESS if short_help else "disable default centering in the xy plane that ensures symmetric membrane building. Not recommended!")
    parser.add_argument("--channel_plug",  type=float,                help=argparse.SUPPRESS if short_help else "establishes a cylindrical restraint on the lipids using the protein z height and the input value as xy radius. A value of 0 will use half of the protein radius. By default, no restraint is imposed.")
    parser.add_argument("--self_assembly",      action="store_true",  help=argparse.SUPPRESS if short_help else "places lipids all over the packed box, and not in a bilayer.")
    parser.add_argument("--xygauss",nargs=3,metavar=("C","D","H"),    help=argparse.SUPPRESS if short_help else "set parameters for a curved 2d gaussian in the xy plane. Parameters are uncertainty in x, uncertainty in y and gaussian height. By default, membranes are flat.")
    parser.add_argument("--curvature",    type=float, default=None,   help=argparse.SUPPRESS if short_help else "set the curvature of the membrane patch. By default, membranes are flat.")
    parser.add_argument("--curv_radius",  type=float, default=None,   help=argparse.SUPPRESS if short_help else "inverse of curvature. Set the curvature as if on a vesicle with the provided radius.")
    parser.add_argument("--dims", nargs=3,metavar=("X","Y","Z"),      type=float,default=[0,0,0], help=argparse.SUPPRESS if short_help else "box dimensions vector for the  x y z  axes. Be sure to use dimensions that cover the complete protein to be packed!!")
    parser.add_argument("--solvate",      action="store_true",        help=argparse.SUPPRESS if short_help else "solvate the system without adding lipids. Disables the flag --dist_wat, using only --dist to set the box size. Under development!")
    parser.add_argument("--pbc",          action="store_true",        help=argparse.SUPPRESS if short_help else "use PBC option in packmol, and adapt constraints accordingly.")
    parser.add_argument("--cubic",        action="store_true",        help=argparse.SUPPRESS if short_help else "cube shaped box. Only works with --solvate")
    parser.add_argument("--vol",          action="store_true",        help=argparse.SUPPRESS if short_help else "do the lipid number estimation based on the volume occupied by the leaflet instead of APL. This might cause a great overestimation of the number of lipid molecules!")
    parser.add_argument("--leaflet",      type=float, default=23.0,   help=argparse.SUPPRESS if short_help else "set desired leaflet width. 23 by default.")
    parser.add_argument("--lip_offset",   type=float, default=1.0,    help=argparse.SUPPRESS if short_help else "factor that multiplies the x/y sizes for the lipid membrane segment. Might improve packing and handling by AMBER")
    parser.add_argument("--apl_offset",   action="append",            help=argparse.SUPPRESS if short_help else "factor that multiplies the default APL values. Helpful if packing stretched membranes.")
    parser.add_argument("--tailplane",    type=float,                 help=argparse.SUPPRESS if short_help else "sets the position BELOW which the CH3 carbon atoms in the tail should be. By default defined in parameter file")
    parser.add_argument("--headplane",    type=float,                 help=argparse.SUPPRESS if short_help else "sets the position ABOVE which the PO4 phosphorus and N atoms in the polar head group should be.By default defined in parameter file")
    parser.add_argument("--plot",         action="store_true",        help=argparse.SUPPRESS if short_help else "makes a simple plot of loop number vs GENCAN optimization function value, and outputs the values to GENCAN.dat")
    parser.add_argument("--traj",         action="store_true",        help=argparse.SUPPRESS if short_help else "saves all intermediate steps into separate pdb files")
    parser.add_argument("--keep",         action="store_true",       help=argparse.SUPPRESS if short_help else "skips deleting temporary files")
    parser.add_argument("--noprogress",   action="store_true",        help=argparse.SUPPRESS if short_help else "avoids the printing of progress bar with time estimation in the final stage. Recommended if the job is piped into a file")
    parser.add_argument("--apl_exp",      action="store_true",        help=argparse.SUPPRESS if short_help else "use experimental APL where available, like AmberTools18 release. Kept for consistency with older versions. By default, terms estimated with Lipid17 are used")
    parser.add_argument("--memgen_parm", type=str,                    help=argparse.SUPPRESS if short_help else "load custom memgen.parm file with APL and VOL values. Extends and overwrites default values")
    parser.add_argument("--pdbtar",      type=str,                    help=argparse.SUPPRESS if short_help else "use custom and replaces included pdb tar file")
    parser.add_argument("--solvent_parm", type=str,                   help=argparse.SUPPRESS if short_help else "load custom solvent.parm file with densities and molecular weights. Extends and overwrites default values")
    parser.add_argument("--overwrite",    action="store_true",        help=argparse.SUPPRESS if short_help else "overwrite, even if files are present")
    parser.add_argument("--log",type=str,default="packmol-memgen.log",help=argparse.SUPPRESS if short_help else "log file name where detailed information is to be written")
    parser.add_argument("-o","--output",type=str,                     help=argparse.SUPPRESS if short_help else "name of the PACKMOL generated PDB file")
    parser.add_argument("--charmm",     action="store_true",          help=argparse.SUPPRESS if short_help else "the output will be in CHARMM format instead of AMBER. Works only for small subset of lipids (see --available_lipids)")
    parser.add_argument("--translate", nargs=3, type=float, default=[0,0,0], help=argparse.SUPPRESS if short_help else "pass a vector as  x y z  to translate the oriented pdb. Ex. ' 0 0 4 '")
    parser.add_argument("--sirah", action="store_true",               help=argparse.SUPPRESS if short_help else "use SIRAH lipids, and corase-grain protein input. Will adapt tolerance accordingly. Only small subset of lipids available!")
    parser.add_argument("--verbose",    action="store_true",          help=argparse.SUPPRESS if short_help else "verbose mode")

    parser.add_argument("--pdb2pqr",      action="store_true", default=True, help=argparse.SUPPRESS if short_help else "deprecated: pdb2pqr is now the default protonation tool. This flag is kept for backward compatibility")
    parser.add_argument("--pdb2pqr_pH",   type=float, default=7.0,    help=argparse.SUPPRESS if short_help else "pH to be used by pdb2pqr to protonate the structure (default: 7.0)")
    parser.add_argument("--reduce",       action="store_true",        help=argparse.SUPPRESS if short_help else "use AMBER's reduce instead of pdb2pqr for protonation (legacy)")
    parser.add_argument("--notprotonate", action="store_true",       help=argparse.SUPPRESS if short_help else "skips protonation")
    parser.add_argument("--reducebuild",  action="store_true",        help=argparse.SUPPRESS if short_help else "build step by reduce (protonation of His and side-chain flips). Implies --reduce. Use with care if parametrizing with the script!")
    parser.add_argument("--nottrim",      action="store_false",       help=argparse.SUPPRESS if short_help else "doesn't trim preexisting hydrogens in the structure (only applies when using reduce)")

    inputs = parser.add_argument_group('Inputs')
    inputs.add_argument("-p","--pdb",           action="append",       help="Protein structure file(s) to embed (PDB, PQR, CIF, or mmCIF format). If many bilayers, it has to be specified once for each bilayer. 'None' can be specified and a bilayer without protein will be generated [ex. --pdb PDB1.pdb --pdb None --pdb PDB2.cif (3 bilayers without protein in the middle)]. If no PDB is provided, the bilayer(s) will be membrane only (--distxy_fix has to be defined).")
    inputs.add_argument("--solute",        action="append",            help=argparse.SUPPRESS if short_help else "adds pdb as solute into the water. Concentration has to be specified")
    inputs.add_argument("--solute_con",    action="append",            help=argparse.SUPPRESS if short_help else "number of molecules/concentration to be used. Concentrations are specified in Molar by adding an 'M' as a suffix (Ex. 0.15M). If not added, a number of molecules is assumed.")
    inputs.add_argument("--solute_charge", action="append",            help=argparse.SUPPRESS if short_help else "absolute charge of the included solute (Ex. -2). To be considered in the system neutralization")
    inputs.add_argument("--solute_inmem",  action="store_true",        help=argparse.SUPPRESS if short_help else "solute should be added to membrane fraction")
    inputs.add_argument("--solute_prot_dist",  type=float,             help=argparse.SUPPRESS if short_help else "establishes a cylindrical restraint using the protein xy radius and z height + the input value. A value of 0 will use the protein radius. By default, no restraint is imposed.")

    embedopt = parser.add_argument_group('Orientation options')
    embedopt.add_argument("--preoriented",  action="store_true",          help="use this flag if the protein has been previosuly oriented and you want to avoid running MEMEMBED (i.e. from OPM)")
    embedopt.add_argument("--ppm",          action="store_true",          help="use PPM code instead of MEMEMBED")
    embedopt.add_argument("--classic_memembed", action="store_true",      help="use the C++ MEMEMBED binary instead of the default Python implementation (pymemembed)")
    embedopt.add_argument("--double_span",  action="store_true",          help=argparse.SUPPRESS) #"orient protein twice, assuming it spans two membrane bilayer")
    embedopt.add_argument("--n_ter",        action="append",              help=argparse.SUPPRESS if short_help else "'in' or 'out'. By default proteins are oriented with the n_ter oriented 'in' (or 'down'). relevant for multi layer system. If defined for one protein, it has to be defined for all of them, following previous order")
    embedopt.add_argument("--barrel",       action="store_true",          help=argparse.SUPPRESS if short_help else "use MEMEMBED in beta barrel mode")
    embedopt.add_argument("--keepligs",     action="store_true",          help=argparse.SUPPRESS if short_help else "MEMEMBED by default cleans the PDB. Use this flag to keep the ligands on the original PDB")
    embedopt.add_argument("--mem_opt",type=str,default="3",choices=["0","1","2","3"],help=argparse.SUPPRESS if short_help else "MEMEMBED optimization algorithm. 0 = Genetic algorithm, 1 = Grid, 2 = Direct, 3 = GA five times")
    embedopt.add_argument("--memembed",type=str,                          help=argparse.SUPPRESS)
    embedopt.add_argument("--ppm3",type=str,                              help=argparse.SUPPRESS)
    embedopt.add_argument("--cpus", type=int, default=1,                  help=argparse.SUPPRESS if short_help else "number of CPU threads for pymemembed and MC volume calculation (default: 1)")

    packmolopt = parser.add_argument_group('PACKMOL options')
    packmolopt.add_argument("--nloop",       type=int,default=20,         help=argparse.SUPPRESS if short_help else "number of nloops for GENCAN routine in PACKMOL. PACKMOL MEMGEN uses 20 by default; you might consider increasing the number to improve packing. Increasing the number of components requires more GENCAN loops.")
    packmolopt.add_argument("--nloop_all",   type=int,default=100,        help=argparse.SUPPRESS if short_help else "number of nloops for all-together packing. PACKMOL MEMGEN uses 100 by default.")
    packmolopt.add_argument("--tolerance",   type=float,default=2.0,      help=argparse.SUPPRESS if short_help else "tolerance for detecting clashes between molecules in PACKMOL (defined as radius1+radius2). PACKMOL uses 2.0 by default.")
    packmolopt.add_argument("--prot_rad",   type=float,default=1.5,       help=argparse.SUPPRESS if short_help else "radius considered for protein atoms to establish the tolerance for detecting clashes. PACKMOL MEMGEN uses 1.5 by default.")
    packmolopt.add_argument("--writeout",                                 help=argparse.SUPPRESS if short_help else "frequency for writing intermediate results. PACKMOL uses 10 by default.")
    packmolopt.add_argument("--notrun",       action="store_true",        help=argparse.SUPPRESS if short_help else "will not run PACKMOL, even if it's available")
    packmolopt.add_argument("--random",       action="store_true",        help=argparse.SUPPRESS if short_help else "turns PACKMOL random seed generator on. If a previous packing failed in the minimization problem, repacking with this feature on might solve the problem.")
    packmolopt.add_argument("--packall",  action="store_true",            help=argparse.SUPPRESS if short_help else "skips initial individual packing steps")
    packmolopt.add_argument("--short_penalty",  action="store_true",      help=argparse.SUPPRESS if short_help else "add a short range penalty for heavily overlapping atoms with default PACKMOL options")
    packmolopt.add_argument("--movebadrandom", action="store_true",       help=argparse.SUPPRESS if short_help else "randomizes positions of badly placed molecules in initial guess")
    packmolopt.add_argument("--maxit",       type=int,default=20,         help=argparse.SUPPRESS if short_help else "number of GENCAN iterations per loop. 20 by default.")
    packmolopt.add_argument("--movefrac",    type=float,default=0.05,     help=argparse.SUPPRESS if short_help else "fraction of molecules to be moved. 0.05 by default.")
    packmolopt.add_argument("--packlog",type=str,default="packmol",       help=argparse.SUPPRESS if short_help else "prefix for generated PACKMOL input and log files")
    packmolopt.add_argument("--packmol",type=str,                         help=argparse.SUPPRESS)

    saltopt = parser.add_argument_group('Salts and charges')
    saltopt.add_argument("--salt",        action="store_true",         help=argparse.SUPPRESS if short_help else "adds salt at a concentration of 0.15M by default. Salt is always added considering estimated charges for the system.")
    saltopt.add_argument("--salt_c",default="K+",                      help=argparse.SUPPRESS if short_help else "cation to add. (K+ by default)")
    saltopt.add_argument("--salt_a",default="Cl-",                     help=argparse.SUPPRESS if short_help else "anion to add. (Cl- by default)")
    saltopt.add_argument("--saltcon", type=float, default=0.15,        help=argparse.SUPPRESS if short_help else "modifies the default concentration for KCl. [M]")
    saltopt.add_argument("--salt_override",action="store_true",        help=argparse.SUPPRESS if short_help else "if the concentration of salt specified is less than the required to neutralize, will try to continue omitting the warning")
    saltopt.add_argument("--nocounter",action="store_true",            help=argparse.SUPPRESS if short_help else "no counterions are added. Will depend on pmemd 'plasma' neutralization")
    saltopt.add_argument("--charge_pdb_delta", action="append",        help=argparse.SUPPRESS if short_help else "add a given formal charge value per pdb. Might be useful to compensate for charges of non-standard residues not accounted by the script. If many pdbs, it has to be specified once for each pdb.")

    amberopt = parser.add_argument_group('AMBER options')
    amberopt.add_argument("--minimize",     action="store_true",        help="performs minimization by using pmemd.")
    amberopt.add_argument("--cg_steps", type=int, default = 250, help=argparse.SUPPRESS if short_help else "in case of minimizing, number of conjugated gradient steps (250 by default)")
    amberopt.add_argument("--sd_steps", type=int, default = 250, help=argparse.SUPPRESS if short_help else "in case of minimizing, number of steepest descent steps (250 by default)")
    amberopt.add_argument("--ligand_param",default=None,action="append",help=argparse.SUPPRESS if short_help else "in case of parametrizing or minimizing the system with non-canonical molecules. Give frcmod and lib filenames separated by ':' [ex. --ligand_param FRCMOD:LIB].")
    amberopt.add_argument("--gaff2",     action="store_true",           help=argparse.SUPPRESS if short_help else "if ligand parameters are included, use GAFF2 during parametrization (GAFF is used by default)")
    amberopt.add_argument("--leapline",default=None,action="append",    help=argparse.SUPPRESS if short_help else "extra lines added to the leap parametrization process. Delimit the line with quotes. The system is called SYS into leap [ex. --leapline 'bond SYS.4.SG SYS.122.SG' to form SS bond between SG atoms of residues 4 and 122]")
    amberopt.add_argument("--engine",default="pmemd.cuda",choices=["sander","pmemd","pmemd.cuda"], help=argparse.SUPPRESS if short_help else "AMBER MD program to use")
    amberopt.add_argument("--onlyleapin",   action="store_true",            help="creates leap input script but does NOT run it")
    amberopt.add_argument("--parametrize",   action="store_true",       help="parametrizes the system by using tleap. Uses LIPID21, ff14SB and TIP3P by default (check --ffwat and --ffprot)")
    amberopt.add_argument("--ffwat",default=None,choices=["tip3p","tip4pd","tip4pew", "opc3", "opc", "spce", "spceb", "fb3"], help=argparse.SUPPRESS if short_help else "water model to be used during parametrization.If not set explicitly, will change depending on the protein ff (--ffprot)")
    amberopt.add_argument("--ffprot",default="ff14SB",choices=["ff14SB","ff15ipq","ff19SB"], help=argparse.SUPPRESS if short_help else "protein ff to be used during parametrization.")
    amberopt.add_argument("--fflip",default="lipid21",choices=["lipid21","lipid17"], help=argparse.SUPPRESS if short_help else "lipid ff to be used during parametrization.If Lipid21 is available, will be selected by default.")
    amberopt.add_argument("--tight_box",     action="store_true",       help=argparse.SUPPRESS if short_help else "sets box dimension according to restraints used during the packing. The default uses a vdW distance to the boundary")
    amberopt.add_argument("--HMR", action="store_true",                 help=argparse.SUPPRESS if short_help else "uses Parmed hydrogen mass repartitioning routine if --parametrize is used")


    compel = parser.add_argument_group('Computational electophysiology')
    compel.add_argument("--double",       action="store_true",        help=argparse.SUPPRESS if short_help else "asumes a stacked double bilayer system for CompEL. The composition in --lipids will be used for both bilayers flipping the leaflets")
    compel.add_argument("--charge_imbalance", type=int, default=0,    help=argparse.SUPPRESS if short_help else "sets a charge imbalance between compartments (in electron charge units). A positive imbalance implies an increase (decrease) in cations (anions) in the central compartment.")
    compel.add_argument("--imbalance_ion", type=str, default="cat", choices=["cat","an"], help=argparse.SUPPRESS if short_help else "sets if cations or anions are used to imbalance the system charges. ('cat' by default)")

    parser.add_argument("--json", type=str, metavar="FILE",            help="load configuration from a previously saved JSON file to replicate a run exactly. On every run the configuration is saved to <log_basename>.json (default: packmol-memgen.json)")

    return parser

class PACKMOLMemgen(object):
    """Membrane-protein-lipid bilayer system builder for AMBER MD simulations.

    Orchestrates PACKMOL packing, protein orientation (MEMEMBED/PPM3),
    CHARMM-to-AMBER conversion, and optional LEaP parametrization and
    minimization to produce ready-to-simulate membrane systems.

    Typical usage:
        >>> pmg = PACKMOLMemgen()
        >>> pmg.run_all()

    Attributes:
        contents: PACKMOL input script string, populated by prepare().
        outfile: Path to the output PDB file.
        parameters: Lipid parameter dictionary loaded from memgen.parm.
        sparameters: Solvent parameter dictionary loaded from solvent.parm.
    """

    def __init__(self, args=None):
        """Initialize PACKMOLMemgen from parsed or default CLI arguments.

        Args:
            args: argparse.Namespace with configuration options. If None,
                arguments are parsed from sys.argv via the module-level parser.
        """
        logger = logging.getLogger("pmmg_log")
        if args is None:
            args = build_parser().parse_args()

        #Get args in self 
        for key, value in args.__dict__.items():
            setattr(self, key, value)

    def _load_parameters(self):
        """Load PACKMOL path, lipid/solvent parameters, and PDB tar archive.

        Locates the PACKMOL executable (bundled or from AMBERHOME), reads
        memgen.parm and solvent.parm into self.parameters and self.sparameters,
        and opens the PDB tar archive containing pre-built lipid structures.

        Returns:
            tarfile.TarFile: Opened tar archive of lipid PDB structures.
        """

        # Initialize file tracking lists for cleanup
        self.created        = []
        self.created_notrun = []

        #Path to local Packmol installation (http://www.ime.unicamp.br/~martinez/packmol/home.shtml)
        self._rep = "data"
        self._lib = "lib"
        self._pid = None
        self.run = not self.notrun
        if self.apl_exp:
            self._apl = "APL_EXP"
        else:
            self._apl = "APL_FF"
        packmol_inc = os.path.join(script_path, self._lib, "packmol", "packmol" + exe_suffix)
        if self.packmol is None:
            try:
                amberhome = os.environ['AMBERHOME']
                packmol_amb = os.path.join(amberhome, "bin", "packmol" + exe_suffix)
            except KeyError:
                packmol_amb = ""

            if os.path.exists(packmol_inc):
                self.packmol = packmol_inc
            elif os.path.exists(packmol_amb):
                self.packmol = packmol_amb
            else:
                self.packmol = ""

        if (self.packmol is not None or self.packmol != "") and not os.path.exists(self.packmol):
            miss = f"Packmol path defined but not found on {self.packmol}"
            logger.info("\n"+len(miss)*"#"+"\n"+miss+"\n"+len(miss)*"#"+"\n")
            self.run = False
        elif self.packmol is None or self.packmol == "":
            miss = "Packmol path not defined. Execution will only create the packmol input script."
            logger.info("\n"+len(miss)*"#"+"\n"+miss+"\n"+len(miss)*"#"+"\n")
            self.run = False


        ############## PARSE PARAMS FROM REP #########

        if self.pdbtar:
            if not os.path.exists(self.pdbtar):
                logger.critical("CRITICAL: PDBTAR path does not exist")
            pdbtar = tarfile.open(self.pdbtar,"r:gz")
        else:
            pdbtar = tarfile.open(os.path.join(script_path, self._rep,"pdbs.tar.gz"),"r:gz")
        parms = open(os.path.join(script_path, self._rep, "memgen.parm"), "r")
        parmlines = parms.readlines()
        parms.close()
        if self.memgen_parm is not None:
            logger.debug(f"Loading custom memgen.parm:     {self.memgen_parm}")
            logger.debug("Parameters will be extended or overwritten over default values")
            parms = open(self.memgen_parm, "r")
            parmlines += parms.readlines()
            parms.close()
        self.parameters = {}
        ext_par = False
        for line in parmlines:
            if line[0] == "#":
                if line.startswith("#EXTENDED LIPIDS"):
                    ext_par = True
                continue
            else:
                values = line.split()
                self.parameters[values[0]]  = {}
                self.parameters[values[0]].update({
                                         "p_atm":values[1],
                                         "t_atm":values[2],
                                         "APL_FF":values[3],
                                         "APL_EXP":values[4],
                                         "V":values[5],
                                         "charge":values[6],
                                         "h_bound":values[7],
                                         "t_bound":values[8],
                                         "C":values[9],
                                         "VH":values[10],
                                         "charmm":values[11],
                                         "name":values[12],
                                         "ext":ext_par
                                         })

        if self.available_lipids or self.available_lipids_all:
            if self.memgen_parm is not None:
                logger.debug(f"List will include parameters in the parsed parameter file!: {self.memgen_parm}")
            if self.available_lipids:
                pformat = "{:<9}{:>6}{:>70}"
            else:
                pformat = "{:<9}{:>6}{:>130}"
            table_header= (pformat+"{:>15}").format("Lipid","Charge","Full-name","Comment")
            print("\n"+table_header, file=sys.stderr)
            print("-"*len(table_header), file=sys.stderr)
            for key in sorted(self.parameters):
                if not self.available_lipids_all and self.parameters[key]["ext"]:
                    continue
                elif is_number(key[0]) or key[-2:]=="CL" or "PI" in key or self.parameters[key]["ext"]:
                    print((pformat+" ***Parameters from PACKMOL-Memgen Lipid_ext").format(key,self.parameters[key]["charge"],self.parameters[key]["name"]))
                elif key[-2:] == "SM":
                    print((pformat+" ***Only available with Lipid21").format(key,self.parameters[key]["charge"],self.parameters[key]["name"]))
                elif key.startswith("si"):
                    print((pformat+" ***Only available with SIRAH").format(key,self.parameters[key]["charge"],self.parameters[key]["name"]))
                else:
                    print(pformat.format(key,self.parameters[key]["charge"],self.parameters[key]["name"]))
            sys.exit(1)


        solvent_parms = open(os.path.join(script_path, self._rep, "solvent.parm"), "r")
        sparmlines = solvent_parms.readlines()
        solvent_parms.close()
        if self.solvent_parm is not None:
            logger.debug(f"Loading custom solvent.parm:     {self.solvent_parm}")
            solvent_parms = open(self.solvent_parm, "r")
            sparmlines += solvent_parms.readlines()
            solvent_parms.close()
        self.sparameters = {}
        for line in sparmlines:
            if line[0] == "#":
                continue
            values = line.split()
            self.sparameters[values[0]]  = {}
            self.sparameters[values[0]].update({
                                     "density":values[1],
                                     "MW":values[2],
                                     "charge":values[3],
                                     "name":values[4],
                                     "source":values[5].replace("_"," ") if len(values) == 6 else "-"
                                     })

        if self.available_solvents:
            pformat = "{:<9}{:>15}{:>15}{:>15}{:>40}{:>80}"
            table_header= pformat.format("Solvent","Density [g/cm3]","MW [g/mol]","Charge","Full-name","Comments")
            print("\n"+table_header, file=sys.stderr)
            print("-"*len(table_header), file=sys.stderr)
            for key in sorted(self.sparameters):
                print(pformat.format(key,self.sparameters[key]["density"],self.sparameters[key]["MW"],self.sparameters[key]["charge"],self.sparameters[key]["name"],self.sparameters[key]["source"]))
            sys.exit(1)

        if self.available_ions:
            pformat = "{:<9}{:>15}"
            table_header= pformat.format("Ion","Charge")
            print("\n"+table_header, file=sys.stderr)
            print("-"*len(table_header), file=sys.stderr)
            for key in sorted(amber_ion_dict):
                print(pformat.format(key,amber_ion_dict[key][1]))
            sys.exit(1)

        return pdbtar

    def _validate_arguments(self):
        """Validate and normalize CLI arguments into internal attributes.

        Checks for incompatible flag combinations (e.g. --vol with curvature),
        resolves water model defaults based on force field, normalizes solvent
        and ion settings, and stores validated values as private attributes
        (self._leaflet_z, self._distance, self._cation, etc.).
        """

        if self.curv_radius is not None:
            self.curvature = 1/self.curv_radius

        if self.curvature is not None:
            self._sphere_radius = 1/self.curvature
            if self.vol:
                logger.critical("CRITICAL:\n  --vol and curvature are not compatible!")
                sys.exit(1)
            if self.solvate:
                logger.critical("CRITICAL:\n  --solvate and curvature are not compatible!")
                sys.exit(1)

        if not self.solvate and self.cubic:
            logger.warning("WARNING:--cubic only available with --solvate. Turned off!")
            self.cubic = False

        if self.solvate:
            self.preoriented = True
            self._z_cen = True
            self._pdb_prefix = "solvated"
            self.dist_wat = self.dist
        else:
            self._pdb_prefix = "bilayer"
            self._z_cen = False

        if self.ffwat is None:
            if self.ffprot == "ff15ipq":
                self.ffwat = "spceb"
            elif self.ffprot == "ff19SB":
                self.ffwat = "opc"
            elif self.ffprot == "ff14SB":
                self.ffwat = "tip3p"
            logger.debug(f"Water model was not set. Using {self.ffwat} for {self.ffprot}")

        self._leaflet_z = self.leaflet # leaflet thickness
        self._lip_offset = self.lip_offset
        self._bound_tail = self.tailplane # plane that defines boundary to last carbon in aliphatic chain
        self._bound_head = self.headplane # plane that defines boundary to polar head
        lipids = self.lipids # lipids to be used
        self.extended = False

        self.onlymembrane = False
        if self.pdb is None or self.pdb.count("None") == len(self.pdb):
            self.onlymembrane = True
        else:
            # cif_to_pdb is already imported via: from lib.utils import *
            converted_pdbs = []
            for i, pdb in enumerate(self.pdb):
                if pdb == "None":
                    # Protein-free bilayer
                    converted_pdbs.append(pdb)
                elif pdb.endswith(".cif") or pdb.endswith(".mmcif"):
                    # Convert CIF to PDB
                    try:
                        converted_pdb = cif_to_pdb(pdb)
                        self.created.append(converted_pdb)  # Track for cleanup
                        converted_pdbs.append(converted_pdb)
                        logger.info(f"Using converted PDB from CIF input: {converted_pdb}")
                    except (ImportError, RuntimeError) as e:
                        # Error already logged by cif_to_pdb()
                        exit(1)
                elif pdb.endswith(".pdb") or pdb.endswith(".pqr"):
                    # Standard PDB/PQR input
                    converted_pdbs.append(pdb)
                else:
                    # Unsupported format
                    logger.critical("CRITICAL:\n  The input file must be in PDB, PQR, CIF, or mmCIF format.\n"
                                  f"  Received: {pdb}")
                    exit(1)

            # Replace original list with converted list
            self.pdb = converted_pdbs
        if self.double_span and self.pdb is None:
            logger.critical("CRITICAL:\n  --double_span requires a PDB file as input")
            sys.exit(1)
        elif self.double_span and len(self.pdb) == 1:
            self.pdb.append("None")

        if self.minimize:
            self.parametrize = True

        if self.HMR and not self.parametrize:
            logger.critical("CRITICAL:\n --HMR can only be used if the system is parametrized with --parametrize")
            sys.exit(1)

        self.outfile = self.output
        if self.outfile is not None:
            if not self.outfile.endswith(".pdb"):
                self.outfile = self.outfile+".pdb"
        if not self.output and self.pdb is None:
            self.outfile = self._pdb_prefix+"_only.pdb"
        elif not self.output:
            self.outfile = self._pdb_prefix+"_"+"".join([os.path.basename(pdb)[:-4] for pdb in self.pdb])+".pdb"

        if lipids is not None:
            if any([self.parameters[l]["ext"] for lipid in lipids for leaf in lipid.split("//") for l in leaf.split(":")]):
                logger.info("The Lipid Force Field extension lipid_ext is required for this system! Use --parametrize to get it done for you")
                self.extended = True
        self._saltcon = self.saltcon # salt concentration in M
        if not self.salt:
            if "--saltcon" in sys.argv and (self.distxy_fix is not None or self.pdb is not None):
                logger.error("ERROR:\n    You specified a salt concentration, but not the salt flag. Only neutralizing ions will be added")
            self._saltcon = 0
            if self.charge_imbalance != 0:
                logger.error("ERROR:\n    You specified a charge imbalance, but not the salt flag. No charge imbalance will be applied")
        self._override_salt = self.salt_override
        #Check for cation
        if self.sirah:
            self.ion_dict = {"K+":("siKW",1,"KW"),"Na+":("siNaW",1,"NaW"),"Ca2+":("siCaX",2,"CaX"),"Cl-":("siClW",-1,"ClW")}
        else:
            self.ion_dict = amber_ion_dict
        if self.salt_c not in self.ion_dict:
            logger.error("ERROR:\n    The specified cation option is no available at the moment")
            sys.exit(1)
        else:
            if self.ion_dict[self.salt_c][1] < 0:
                logger.error("ERROR:\n    The specified cation is really an anion")
                sys.exit(1)
            self._cation = self.ion_dict[self.salt_c][0]
        if self.salt_a not in self.ion_dict:
            logger.error("ERROR:\n    The specified cation option is no available at the moment")
            sys.exit(1)
        else:
            if self.ion_dict[self.salt_a][1] > 0:
                logger.error("ERROR:\n    The specified anion is really a cation")
                sys.exit(1)
            self._anion = self.ion_dict[self.salt_a][0] #Maybe more alternatives at some point? ILs?
        self._distance = self.dist # distance from the protein to the box boundaries to XY
        self._distance_wat = self.dist_wat # minimum distance from the surface of the membrane to the box boundary on Z

        if (self.distxy_fix is not None and self.dims != [0,0,0]):
            logger.error("ERROR:\n    --distxy_fix and --dims should not be used together! Use -h for help.")
            sys.exit(1)

        self._asym = False
        if self.distxy_fix is not None and self.dims == [0,0,0]:
            self.dims = [self.distxy_fix,self.distxy_fix,0]
        elif self.lipnum is not None:
            logger.info("Using fixed number of lipids. An initial placeholder of 100 A will be used.")
            self.dims == [100,100,0]
        elif self.dims == [0,0,0]:
            self.dims = None
        else:
            self._asym = True

        if (self.distxy_fix is None and self.dims is None and self.lipnum is None) and self.onlymembrane:
            logger.error("ERROR:\n    No PDB file given or fixed XY dimensions specified. Check --distxy_fix and --dims for help (-h/--help).")
            sys.exit(1)
        if self.writeout is None:
            if int(self.nloop) < 10 or int(self.nloop_all) < 10:
                logger.error("ERROR:\n    nloop and nloop_all have to be bigger than the writeout frequency (every 10 loops by default). You can modify this with --writeout")
                sys.exit(1)
        else:
            if int(self.nloop) < int(self.writeout) or int(self.nloop_all) < int(self.writeout):
                logger.error("ERROR:\n    nloop and nloop_all have to be bigger than the writeout frequency! Modify the used values.")
                sys.exit(1)
        self._protonate = not self.notprotonate
        self._trim = self.nottrim


        # --reducebuild implies --reduce
        if self.reducebuild:
            self.reduce = True
        self.delete = not self.keep

        # JSwails suggestion//Check if in a tty. Turn off progress bar if that's the case.
        if not os.isatty(sys.stdin.fileno()):
            self.noprogress = True

    def _detect_tools(self):
        """Detect AMBER tools, MEMEMBED/PPM3, and validate solvent/lipid inputs.

        Searches for reduce, MEMEMBED, and PPM3 executables. Validates that
        requested solvents exist in solvent.parm. Sets up protein orientation
        tool paths and extended lipid flags.
        """

        ###############################################
        ###############################################
        ###############################################

        ############ SEARCH AMBER, LIBS, PDB, MEMEMBED ###################

        try:
            amberhome = os.environ['AMBERHOME']
            self._reduce = os.path.join(amberhome, "bin", "reduce" + exe_suffix)
            if not os.path.exists(self._reduce):
                logger.warning("WARNING:AMBER path found, but reduce executable is not available")
                self._reduce = None
        except KeyError:
            amberhome = None
            self._reduce = None
            logger.debug("AMBER environment variables not found.")

        # Determine protonation tool (pdb2pqr is default)
        if self._protonate:
            if self.reduce:
                # User explicitly requested reduce
                if not self._reduce:
                    logger.warning("WARNING: --reduce was specified but reduce is not available (AMBERHOME not set or reduce not found). Protonation will be skipped.")
                    self._protonate = False
            else:
                # Default: pdb2pqr
                if not pdb2pqr_exe:
                    if self._reduce:
                        logger.warning("WARNING: pdb2pqr not found in PATH. Falling back to AMBER's reduce for protonation.")
                        self.reduce = True
                    else:
                        logger.warning("WARNING: No protonation tool available (neither pdb2pqr nor reduce found). Protonation will be skipped.")
                        self._protonate = False

        if not os.path.exists(os.path.join(script_path, self._rep)):
            logger.critical("CRITICAL:\n  The data folder for using the script is missing. Check the path for the script!")
            sys.exit(1)

        if self.pdb is not None:
            if self.pdb[0] == "None" and not self.onlymembrane:
                logger.error("ERROR:\n    Please specify first the protein PDB file!")
                sys.exit(1)
            for pdb in self.pdb:
                if not os.path.exists(pdb) and pdb != "None":
                    logger.error(f"ERROR:\n    Either the options were wrongly used or the file {pdb} doesn't exist!")
                    sys.exit(1)

        # Check pymemembed (Python/Numba implementation) availability
        self.pymemembed = False
        try:
            from packmol_memgen.lib.pymemembed import memembed_align as _test_import
            self.pymemembed = True
        except ImportError:
            try:
                from lib.pymemembed import memembed_align as _test_import
                self.pymemembed = True
            except ImportError:
                pass

        memembed_inc = os.path.join(script_path, self._lib, "memembed", "bin", "memembed" + exe_suffix)
        if self.memembed is None:
            try:
                amberhome = os.environ['AMBERHOME']
                memembed_amb = os.path.join(amberhome, "bin", "memembed" + exe_suffix)
            except KeyError:
                memembed_amb = ""

            if os.path.exists(memembed_inc):
                self.memembed = memembed_inc
            elif os.path.exists(memembed_amb):
                self.memembed = memembed_amb
            else:
                self.memembed = ""

        if not os.path.exists(self.memembed):
            if not self.pymemembed:
                miss = "MEMEMBED not found. The system will be built assuming it was preoriented"
                logger.warning("\n" + "#" * len(miss) + "\n" + miss + "\n" + "#" * len(miss))
            self.memembed = False


        ppm3_inc = os.path.join(script_path, self._lib, "ppm3", "immers" + exe_suffix)
        if self.ppm3 is None:
            try:
                amberhome = os.environ['AMBERHOME']
                ppm3_amb = os.path.join(amberhome, "bin", "immers" + exe_suffix)
            except KeyError:
                ppm3_amb = ""

            if os.path.exists(ppm3_inc):
                self.ppm3 = ppm3_inc
            elif os.path.exists(ppm3_amb):
                self.ppm3 = ppm3_amb
            else:
                self.ppm3 = ""

        if not os.path.exists(self.ppm3):
            miss = "OPM/PPM3/IMMERS not found."
            logger.warning("\n"+len(miss)*"#"+"\n"+miss+"\n"+len(miss)*"#"+"\n")
            self.ppm3 = False

        if not os.path.exists(os.path.join(script_path, self._lib, "pdbremix")):
            logger.warning("WARNING:PDBREMIX lib not available. Volume estimation will be done based on estimated density")
        else:
            grid_avail = True

        if self.solvents is None:
            self.solvents = "WAT"
        if len(self.solvents.split(":")) == 1:
            self.solvent_ratio = "1"
        elif len(self.solvents.split(":")) > 1 and self.solvent_ratio is None:
            logger.error("ERROR:\n    If using solvent mixtures, a solvent ratio has to be specified")
            sys.exit(1)
        if len(self.solvents.split(":")) != len(self.solvent_ratio.split(":")):
            logger.error("ERROR:\n    Amount of solvent types and solvent ratios doesn't fit! Check your input")
            sys.exit(1)

        if self.sirah:
            logger.info("Using parameters to pack a SIRAH system")
            self.solvents = "siWT4"
            self.solvent_ratio = "1"
            self.tight_box = True
            if "--prot_rad" not in sys.argv:
                self.prot_rad = 2
            if "--tolerance" not in sys.argv:
                self.tolerance = 3

        for solvent in self.solvents.split(":"):
            if solvent not in self.sparameters:
                logger.error(f"ERROR:\n    Selected solvent {solvent} parameters not available. Check --available_solvents")
                sys.exit(1)

        self._solvent_ratios = [float(ratio) for ratio in self.solvent_ratio.split(":")]
        solvent_density = sum([float(self.sparameters[solvent]["density"])*self._solvent_ratios[i] for i, solvent in enumerate(self.solvents.split(":"))])/sum(self._solvent_ratios)
        self._solvent_con     = sum([(self._solvent_ratios[i]*float(self.sparameters[solvent]["density"])*avogadro)/(float(self.sparameters[solvent]["MW"])*10**24) for i, solvent in enumerate(self.solvents.split(":"))])/sum(self._solvent_ratios)

        lipids = self.lipids
        if lipids is None:
            lipids = ["DOPC"]
        if self.double and len(lipids) == 1:
            lipids = lipids+["//".join(reversed(lipids[0].split("//")))]
        elif self.double and len(lipids) != 1:
            logger.error("ERROR:\n    --double requires a single definition of lipid composition")
            sys.exit(1)
        self.lipids = lipids # Keep the class list up to date
        if self.double_span and len(lipids) != 2:
            logger.error("ERROR:\n    --double_span requires a definition of lipid composition per bilayer")
            sys.exit(1)
        if self.ratio is None:
            logger.info("No ratio provided (--ratio).")
            self.ratio  = ["1"]*len(lipids)
        if self.double and len(lipids) == 2 and len(self.ratio) == 1:
            self.ratio = self.ratio+["//".join(reversed(self.ratio[0].split("//")))]

        if len(lipids) != len(self.ratio):
            logger.error("ERROR:\n    Number of defined bilayer lipids and ratios doesn't fit! Check your input")
            sys.exit(1)

        if self.n_ter is None and self.double:
            self.n_ter = ["in","out"]
        elif self.n_ter is None:
            self.n_ter = ["in"]*len(lipids)

        elif len(self.n_ter) != len(self.pdb):
            logger.error("ERROR:\n    Number of specified orientations and bilayers doesn't fit! Check your input")
            sys.exit(1)
        else:
            for n, pdb in enumerate(self.pdb):
                if pdb != "None" and not (self.n_ter[n] == "in" or self.n_ter[n] == "out"):
                    logger.error("ERROR:\n    The orientation has to be 'in' or 'out' unless pdb is 'None'")
                    sys.exit(1)


        if self.solute_prot_dist is not None and self.onlymembrane:
            logger.error("ERROR:\n    A solute distance can only be specified with respect to an included PDB!")
            sys.exit(1)

        if self.channel_plug is not None and self.onlymembrane:
            logger.error("ERROR:\n    A channel plug can only be specified with respect to an included PDB!")
            sys.exit(1)

        if self.solute_charge is None and self.solute is not None:
            self.solute_charge = [0]*len(self.solute)

        elif self.solute_charge is not None and self.solute is not None:
            if len(self.solute_charge) != len(self.solute):
                logger.error("ERROR:\n    Number of specified solute charges and solutes doesn't fit! Check your input")
                sys.exit(1)
            else:
                for n, solute in enumerate(self.solute):
                    try:
                        self.solute_charge[n] = int(self.solute_charge[n])
                    except (ValueError, TypeError):
                        logger.error("ERROR:\n    Solute charges have to be integers")
                        sys.exit(1)
    def _check_sphingomyelin(self, lipid):
        """Warn and disable AMBER parametrization if sphingomyelin used with Lipid17.

        Args:
            lipid: Lipid name string to check.
        """
        if (lipid == "PSM" or lipid == "SSM") and self.fflip == "lipid17":
            logger.warning("WARNING:LIPID17 doesn't currently support sphingomyelin! AMBER parametrization will be disabled.")
            self.minimize    = False
            self.parametrize = False

    def _get_apl_offsets(self, bilayer, lipids):
        """Get APL offset values for both leaflets of a bilayer.

        Args:
            bilayer: Bilayer index.
            lipids: List of lipid specification strings.

        Returns:
            dict: APL offset values keyed by leaflet index (0 and 1).
        """
        result = {}
        if self.apl_offset is None:
            result[0] = result[1] = 1.0
        elif len(self.apl_offset) != len(lipids):
            logger.error("ERROR:\n    If apl_offset is specified, it has to be set once per bilayer")
        elif "//" in self.apl_offset[bilayer]:
            result[0], result[1] = map(float, self.apl_offset[bilayer].split("//"))
        else:
            result[0] = result[1] = float(self.apl_offset[bilayer])
        return result

    def _parse_composition(self):
        """Parse lipid composition, ratios, and explicit lipid counts.

        Processes the --lipids, --ratio, and --lipnum arguments into per-bilayer,
        per-leaflet composition dictionaries. Handles symmetric and asymmetric
        (lower//upper) leaflet specifications.

        Returns:
            tuple: (composition, apl_offset, lipnum_set) where each is a nested
                dict keyed by bilayer index and leaflet name ('lower'/'upper').
        """
        lipids = self.lipids
        apl_offset   = {}
        composition  = {}
        lipnum_set   = {}
        self.sterols_PI_used = False
        for bilayer in range(len(lipids)):
            apl_offset[bilayer]  = {}
            composition[bilayer] = {}
            lipnum_set[bilayer]  = {}
            #Check if fixed numebr of lipids wants to be used
            if self.lipnum is None:
                if "//" in lipids[bilayer]:
                    if len(lipids[bilayer].split("//")) != 2 or len(self.ratio[bilayer].split("//")) != 2:
                        logger.error("ERROR:\n    If different leaflet compositions used, ratios have to be specified explicitly, and both must be separated by one '//' only!")
                        sys.exit(1)
                    apl_offset[bilayer] = self._get_apl_offsets(bilayer, lipids)
                    for leaflet in range(2):
                        if len(lipids[bilayer].split("//")[leaflet].split(":")) != len(self.ratio[bilayer].split("//")[leaflet].split(":")):
                            logger.error("ERROR:\n    Amount of lipid types and ratios doesn't fit! Check your input")
                            sys.exit(1)
                        composition[bilayer][leaflet]={}
                        ratio_total = sum([float(x) for x in self.ratio[bilayer].split("//")[leaflet].split(":")])
                        for n, lipid in enumerate(lipids[bilayer].split("//")[leaflet].split(":")):
                            self._check_sphingomyelin(lipid)
                            if self.sirah:
                                composition[bilayer][leaflet]["si"+lipid] = float(self.ratio[bilayer].split("//")[leaflet].split(":")[n])/ratio_total
                            else:
                                composition[bilayer][leaflet][lipid] = float(self.ratio[bilayer].split("//")[leaflet].split(":")[n])/ratio_total
                else:
                    if len(lipids[bilayer].split(":")) != len(self.ratio[bilayer].split(":")):
                        logger.error("ERROR:\n    Amount of lipid types and ratios doesn't fit! Check your input")
                        sys.exit(1)
                    apl_offset[bilayer] = self._get_apl_offsets(bilayer, lipids)
                    composition[bilayer][0]={} ; composition[bilayer][1]={}
                    ratio_total = sum([float(x) for x in self.ratio[bilayer].split(":")])
                    for n, lipid in enumerate(lipids[bilayer].split(":")):
                        self._check_sphingomyelin(lipid)
                        if self.sirah:
                            composition[bilayer][0]["si"+lipid] = composition[bilayer][1]["si"+lipid] = float(self.ratio[bilayer].split(":")[n])/ratio_total
                        else:
                            composition[bilayer][0][lipid] = composition[bilayer][1][lipid] = float(self.ratio[bilayer].split(":")[n])/ratio_total

            else:
                if "//" in lipids[bilayer]:
                    if len(lipids[bilayer].split("//")) != 2 or len(self.lipnum[bilayer].split("//")) != 2:
                        logger.error("ERROR:\n    If different leaflet compositions used, lipnum has to be specified explicitly, and both must be separated by one '//' only!")
                        sys.exit(1)
                    apl_offset[bilayer] = self._get_apl_offsets(bilayer, lipids)
                    for leaflet in range(2):
                        if len(lipids[bilayer].split("//")[leaflet].split(":")) != len(self.lipnum[bilayer].split("//")[leaflet].split(":")):
                            logger.error("ERROR:\n    Amount of lipid types and lipnum doesn't fit! Check your input")
                            sys.exit(1)
                        composition[bilayer][leaflet]={}
                        for n, lipid in enumerate(lipids[bilayer].split("//")[leaflet].split(":")):
                            self._check_sphingomyelin(lipid)
                            if self.sirah:
                                composition[bilayer][leaflet]["si"+lipid] = int(self.lipnum[bilayer].split("//")[leaflet].split(":")[n])
                            else:
                                composition[bilayer][leaflet][lipid] = int(self.lipnum[bilayer].split("//")[leaflet].split(":")[n])
                else:
                    if len(lipids[bilayer].split(":")) != len(self.lipnum[bilayer].split(":")):
                        logger.error("ERROR:\n    Amount of lipid types and lipnum doesn't fit! Check your input")
                        sys.exit(1)
                    apl_offset[bilayer] = self._get_apl_offsets(bilayer, lipids)
                    composition[bilayer][0]={} ; composition[bilayer][1]={}
                    for n, lipid in enumerate(lipids[bilayer].split(":")):
                        self._check_sphingomyelin(lipid)
                        if self.sirah:
                            composition[bilayer][0]["si"+lipid] = composition[bilayer][1]["si"+lipid] = int(self.lipnum[bilayer].split(":")[n])
                        else:
                            composition[bilayer][0][lipid] = composition[bilayer][1][lipid] = int(self.lipnum[bilayer].split(":")[n])

        return (composition, apl_offset, lipnum_set)

    def _validate_lipid_parameters(self, composition, pdbtar):
        """Validate that all requested lipids have parameters and PDB structures.

        Args:
            composition: Nested dict of lipid compositions per bilayer/leaflet.
            pdbtar: Opened tarfile containing lipid PDB structures.
        """
        for key in [x for bilayer in composition for leaflet in composition[bilayer] for x in composition[bilayer][leaflet]]:
            if key in sterols_rings:
                self.sterols_PI_used = True
            if key not in self.parameters:
                logger.critical(f"CRITICAL:\n  Parameters missing for {key}. Please check the file memgen.parm")
                sys.exit(1)
            if self.charmm and self.parameters[key]["charmm"] == "N":
                logger.critical(f"CRITICAL:\n  Lipid {key} not available in CHARMM format.")
                sys.exit(1)
            if not os.path.exists(os.path.join(script_path, self._rep, "pdbs", f"{key}.pdb")) and f"{key}.pdb" not in pdbtar.getnames():
                logger.warning(f"WARNING:\n  PDB file for {key} not found in repo!")
                if not os.path.exists(f"{key}.pdb"):
                    logger.critical(f"CRITICAL:\n  PDB file for {key} not found in local folder!")
                    sys.exit(1)
        if not self.onlymembrane:
            if len(composition) != len(self.pdb):
                if self.double and len(composition) == 2 and len(self.pdb) == 1:
                    logger.debug("Using the pdb file for both bilayers")
                    self.pdb = self.pdb*2
                else:
                    logger.critical("CRITICAL:\n  The number of provided PDB files doesnt fit with the number of bilayers. Pass --pdb \"None\" if you want an empty bilayer.")
                    sys.exit(1)
        if self.pdb is not None:
            if self.charge_pdb_delta is None:
                self.charge_pdb_delta = [0]*len(self.pdb)
            elif len(self.charge_pdb_delta) != len(self.pdb):
                logger.error("ERROR:\n    Number of specified charge deltas and pdbs doesn't fit! Check your input")
                sys.exit(1)
            else:
                self.charge_pdb_delta = [int(i) for i in self.charge_pdb_delta]

        if self.solute is not None:
            if self.solute_con is not None:
                if len(self.solute) != len(self.solute_con):
                    logger.critical("CRITICAL:\n  Number of solutes and concentrations/number of molecules is not the same! Please provide a concentration for each solute in the respective order.")
                    sys.exit(1)
            else:
                logger.error("ERROR:\n    Concentrations/number of molecules have to be provided.")
                sys.exit(1)


        if self.ligand_param is not None:
            for param in self.ligand_param:
                files = param.split(":")
                if not os.path.exists(files[0]) or not os.path.exists(files[1]):
                    logger.error("ERROR:\n    Specified parameter files do not exist!")
                    logger.debug("Files: "+" ".join(files))
                    sys.exit(1)


        if self.solute is not None:
            for i, sol in enumerate(self.solute):
                if not os.path.exists(self.solute[i]):
                    logger.error(f"{self.solute[i]} not found!")
                    sys.exit(1)
                logger.info(f"Extra solute PDB         = {self.solute[i]:<9s}")
                logger.info(f"Solute to be added       = {self.solute_con[i]:<9s}")
    
    
    def _build_packmol_header(self):
        """Build the PACKMOL input file header section.

        Generates tolerance, output filename, iteration counts, and optional
        PBC/random seed/short-penalty directives.

        Returns:
            str: PACKMOL header script content.
        """

        ############################### SCRIPT HEADER ################################

        content_header = ""
        content_header += f"tolerance {self.tolerance}\n"
        content_header += "filetype pdb\n"
        content_header += f"output {self.outfile}\n\n"
        if self.writeout is not None:
            content_header += f"writeout {self.writeout}\n"
        if self.traj:
            if self.writeout is None:
                content_header += "writeout 1\n"
            content_header += "writebad\n\n"

        if self.random:
            content_header += "seed -1\n"
        if self.packall:
            content_header += "packall\n"
        if self.maxit != 20:
            content_header += f"maxit {self.maxit}\n"
        if self.movefrac != 0.05:
            content_header += f"movefrac {self.movefrac}\n"
        if self.short_penalty:
            content_header += "use_short_tol\n"
            content_header += f"short_tol_dist {self.tolerance/4}\n"
            content_header += "short_tol_scale 5\n"
        if not self.charmm:
             content_header += "add_amber_ter\n"
        content_header += "amber_ter_preserve\n"
        if self.movebadrandom:
            content_header += "movebadrandom\n"


        content_header += f"nloop {self.nloop_all}\n\n"

        return content_header
    
    def _process_proteins_and_geometry(self, composition, apl_offset, pdbtar):
        """Orient proteins and calculate membrane/box geometry.

        Processes each input PDB through orientation tools (MEMEMBED/PPM3),
        computes protein volume, determines box dimensions, Z-layer boundaries,
        membrane and solvent volumes, and system charges.

        Args:
            composition: Nested dict of lipid compositions per bilayer/leaflet.
            apl_offset: APL scaling factors per bilayer/leaflet.
            pdbtar: Opened tarfile containing lipid PDB structures.

        Returns:
            dict: Geometry parameters including X/Y min/max, Z_dim layers,
                membrane/solvent volumes, charges, and content extras.
                Returns False if the system has no membrane and no solvent.
        """
        leaflet_z = self._leaflet_z
        distance = self._distance
        distance_wat = self._distance_wat
        asym = self._asym

        X_min   = X_max = X_len = Y_min = Y_max = Y_len = 0
        Z_dim   = []
        memvol  = []
        solvol  = []
        charges = []
        minmax = None
        max_rad = None
        z_offset_ds = 0
        if not self.onlymembrane:
            chain_nr = 0
            chain_index = list(string.ascii_uppercase)+list(string.ascii_lowercase)
            for n,pdb in enumerate(self.pdb):
                if pdb != "None":
                    if not self.verbose:
                        logger.info(f"Preprocessing {pdb}. This might take a minute.")
                    if not self.preoriented and (self.pymemembed or self.memembed or self.ppm):
                        if self.double_span:
                            if self.ppm:
                                logger.error("ERROR:\n    --double_span is not supported with --ppm")
                                sys.exit(1)
                            elif self.classic_memembed and self.memembed:
                                logger.debug("Attempting to orient double span protein using MEMEMBED...")
                                pdb, z_offset_ds = self.memembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt, double_span=True)
                            elif self.pymemembed:
                                logger.debug("Attempting to orient double span protein using pymemembed...")
                                pdb, z_offset_ds = self.pymemembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt, double_span=True)
                            elif self.memembed:
                                logger.debug("Attempting to orient double span protein using MEMEMBED...")
                                pdb, z_offset_ds = self.memembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt, double_span=True)
                            z_offset_ds = abs(z_offset_ds)
                            pdb_ds = pdb
                        else:
                            if self.ppm:
                                logger.debug("Orienting the protein using PPM3...")
                                pdb, tmp = self.ppm3_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,n_ter=self.n_ter[n])
                                self.created.append(tmp)
                            elif self.classic_memembed and self.memembed:
                                logger.debug("Orienting the protein using MEMEMBED (C++)...")
                                self.created.append(pdb+"_memembed.log")
                                pdb = self.memembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt)
                            elif self.pymemembed:
                                logger.debug("Orienting the protein using pymemembed...")
                                pdb = self.pymemembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt)
                            elif self.memembed:
                                logger.debug("Orienting the protein using MEMEMBED (C++)...")
                                self.created.append(pdb+"_memembed.log")
                                pdb = self.memembed_align(pdb,keepligs=self.keepligs,verbose=self.verbose,overwrite=self.overwrite,barrel=self.barrel,n_ter=self.n_ter[n],opt=self.mem_opt)
                        self.created.append(pdb)
                    if self._protonate and self.reduce and self._reduce:
                        logger.debug("Using 'reduce' to protonate...")
                        if self._trim:
                            logger.debug("Trimming preexisting protons...")
                            pdb =  reduce_trim(pdb,overwrite=self.overwrite)
                            if pdb == "error":
                                logger.error("ERROR:\n    reduce returned an empty file! Check the used pdb files and reduce_Trim_warn.log")
                                sys.exit(1)
                            self.created.append(pdb)
                            self.created.append("reduce_Trim_warn.log")
                        logger.debug("Adding protons using reduce...")
                        pdb =  reduce_protonate(pdb,overwrite=self.overwrite,build=self.reducebuild)
                        if pdb == "error":
                                logger.error("ERROR:\n    reduce returned an empty file! Check the used pdb files and reduce_warn.log")
                                sys.exit(1)
                        self.created.append(pdb)
                        self.created.append("reduce_warn.log")
                    elif self._protonate:
                        logger.info(f"Adding protons using pdb2pqr at pH {self.pdb2pqr_pH}...")
                        pdb =  pdb2pqr_protonate(pdb,overwrite=self.overwrite,pH=self.pdb2pqr_pH)
                        self.created.append(pdb)
                    elif self.preoriented and self.double_span:
                        ds_oriented = pdb_parse(pdb, onlybb=False)
                        try:
                            z_dist = ds_oriented[('MEM', 1, 'X')][('MEM', 1)][2]+ds_oriented[('MEM', 2, 'X')][('MEM', 2)][2]
                        except KeyError:
                            logger.critical("CRITICAL:\n  If using a preoriented double spanning PDB, it has to include MEM atoms!")
                            sys.exit(1)
                        if z_dist < 0:
                            ds_oriented = translate_pdb(ds_oriented,vec=[0,0,z_dist])
                            z_dist *= -1
                        del ds_oriented[('MEM', 1, 'X')]
                        del ds_oriented[('MEM', 2, 'X')]

                        pdb_write(ds_oriented, outfile="ds_temp.pdb")
                        pdb = pdb_ds = "ds_temp.pdb"

                        z_offset_ds = z_dist


                    ############## FAST VALUE ESTIMATION FROM PDB #####################
                    mem_params = MembraneParams(pdb,leaflet_z,move=True, move_vec=self.translate, xy_cen=self.noxy_cen, z_cen=self._z_cen, outpdb=f"PROT{n}.pdb",chain=chain_index[chain_nr],renumber=True)
                    minmax, max_rad, charge_prot, vol, memvol_up, memvol_down, solvol_up, solvol_down, density, mass, chains = mem_params.measure(threads=getattr(self, 'cpus', 1))
                    if self.sirah:
                        sirah_cgconv(f"PROT{n}.pdb")
                    chain_nr += chains
                    charge_prot += self.charge_pdb_delta[n]
                    charges.append(charge_prot)

                elif pdb == "None" and self.double_span:
                    logger.debug("Estimating for second mem!")
                    mem_params = MembraneParams(pdb_ds,leaflet_z,move=True, move_vec=[0,0,-z_offset_ds], xy_cen=self.noxy_cen, z_cen=self._z_cen, outpdb=f"PROT{n}.pdb",chain=chain_index[chain_nr],renumber=True)
                    minmax, max_rad, charge_prot, vol, memvol_up, memvol_down, solvol_up, solvol_down, density, mass, chains = mem_params.measure(threads=getattr(self, 'cpus', 1))
                    if self.sirah:
                        sirah_cgconv(f"PROT{n}.pdb")


                else:
                    if not self.verbose:
                        logger.debug("Building membrane without protein!")
                    if self.dims is not None:
                        minmax      = [-self.dims[0]/2,-self.dims[1]/2,-leaflet_z,self.dims[0]/2,self.dims[1]/2,leaflet_z]
                    else:
                        minmax      = minmax[0:2]+[-leaflet_z]+minmax[3:5]+[leaflet_z]
                    charge_prot      = 0
                    charges.append(charge_prot)
                    vol              = 0
                    memvol_up        = 0
                    memvol_down      = 0
                    solvol_up        = 0
                    solvol_down      = 0
                    density          = 0
                    mass             = 0

                solvol.append((solvol_down,solvol_up))
                memvol.append((memvol_down,memvol_up))

                if self.double_span and pdb == "None":
                    charges.append(0)
                    Z_dim.append((-z_offset_ds/2,z_max-z_offset_ds,z_max-z_offset_ds/2))
                    continue

                com = [(minmax[0]+minmax[3])/2,(minmax[1]+minmax[4])/2,(minmax[2]+minmax[5])/2]

                if self.dims is not None:
                    pdbx_min     = com[0]-self.dims[0]/2
                    pdbx_max     = com[0]+self.dims[0]/2
                    pdby_min     = com[1]-self.dims[1]/2
                    pdby_max     = com[1]+self.dims[1]/2
                    pdbz_min     = com[2]-self.dims[2]/2
                    pdbz_max     = com[2]+self.dims[2]/2

                else:
                    pdbx_min     = minmax[0]
                    pdbx_max     = minmax[3]
                    pdby_min     = minmax[1]
                    pdby_max     = minmax[4]
                    pdbz_min     = minmax[2]
                    pdbz_max     = minmax[5]

                pdbx_len     = pdbx_max-pdbx_min
                pdby_len     = pdby_max-pdby_min
                pdbz_len     = pdbz_max-pdbz_min

                if not asym:
                    if self.dims is None and pdb is not None:
        #                max_side_len = math.sqrt(pdbx_len**2+pdby_len**2)+2*distance
                        max_side_len = 2*max_rad+2*distance
                    else:
                        max_side_len = max(self.dims[:2])
                    if self.cubic:
                        max_side_len = max(max_side_len,pdbz_len+2*distance)
                    diff_x       = max_side_len - pdbx_len
                    diff_y       = max_side_len - pdby_len
                    diff_z       = max_side_len - pdbz_len
                else:
                    #if setting box dimensions by hand, check that box boundaries leave some space to add water
                    if pdbz_min > -(leaflet_z+5):
                        correct_z = pdbz_min+(leaflet_z+5)
                        pdbz_min = -(leaflet_z+5)
                        pdbz_max = pdbz_max-correct_z
                    if pdbz_max < (leaflet_z+5):
                        correct_z = pdbz_max-(leaflet_z+5)
                        pdbz_max = (leaflet_z+5)
                        pdbz_min = pdbz_min-correct_z
                    if pdbz_max < minmax[5]+(self.dist_wat-5) or pdbz_min > minmax[2]-(self.dist_wat-5):
                        logger.critical("CRITICAL: Set dimensions and protein location don't allow to have a proper water surface on the membrane. Increase the the used dimensions.")
                        sys.exit(1)
                    diff_x = diff_y = diff_z = 0
                x_min        = pdbx_min-diff_x/2
                x_max        = pdbx_max+diff_x/2
                y_min        = pdby_min-diff_y/2
                y_max        = pdby_max+diff_y/2
                z_min        = pdbz_min-diff_z/2
                z_max        = pdbz_max+diff_z/2
                x_len        = x_max-x_min
                y_len        = y_max-y_min
                z_len        = z_max-z_min

                if not self.cubic and not asym:
                    z_min = pdbz_min-distance_wat
                    if z_min > -(leaflet_z+distance_wat):
                        z_min = -(leaflet_z+distance_wat)
                    z_max = pdbz_max+distance_wat
                    if z_max < (leaflet_z+distance_wat):
                        z_max =  (leaflet_z+distance_wat)
                    if self.xygauss:
                        z_max += float(self.xygauss[2])
                    z_len = z_max-z_min

                prot_data2= """
     Estimated values for input protein:

     Input PDB                = %-9s
     Charge                   = %-9s
     Mass                     = %-9s    Da
     Density                  = %-9s    Da/A^3
     Estimated volume         = %-9s    A^3
         in upper leaflet     = %-9s    A^3
         in lower leaflet     = %-9s    A^3
         in upper water box   = %-9s    A^3
         in lower water box   = %-9s    A^3
                """
                logger.debug(prot_data2 % ( pdb, charge_prot, mass, round(density,2), round(vol,2), round(memvol_up,2), round(memvol_down,2), round(solvol_up), round(solvol_down,2)))


                if x_len > X_len:
                    X_min = x_min; X_max = x_max; X_len = x_len
                if y_len > Y_len:
                    Y_min = y_min; Y_max = y_max; Y_len = y_len
                if self.double_span and pdb != "None":
                    Z_dim.append((z_min,z_offset_ds/2,z_offset_ds/2-z_min))
                else:
                    Z_dim.append((z_min,z_max,z_len))

        else:
            if self.dims is not None:
                minmax      = [-self.dims[0]/2,-self.dims[1]/2,-self.dims[2]/2,self.dims[0]/2,self.dims[1]/2,self.dims[2]/2]
                z_min = minmax[2]
                z_max = minmax[5]
            else:
                z_min = minmax[2]-distance_wat
                z_max = minmax[5]+distance_wat

            charge_prot      = 0
            charges          = [charge_prot]*len(composition)
            vol              = 0
            memvol_up        = 0
            memvol_down      = 0
            solvol_up        = 0
            solvol_down      = 0
            density          = 0
            mass             = 0

            memvol = [(memvol_down,memvol_up)]*len(composition)
            solvol = [(solvol_down,solvol_up)]*len(composition)

            pdbx_len     = minmax[3]-minmax[0]
            pdby_len     = minmax[4]-minmax[1]

            if not asym:
                max_side_len = max(pdbx_len,pdby_len)
                diff_x       = max_side_len - pdbx_len
                diff_y       = max_side_len - pdby_len
            else:
                diff_x = diff_y = 0
            x_min        = minmax[0]-diff_x/2
            x_max        = minmax[3]+diff_x/2
            y_min        = minmax[1]-diff_y/2
            y_max        = minmax[4]+diff_y/2
            x_len        = x_max-x_min
            y_len        = y_max-y_min


            if not self.solvate:
                if z_min > -(leaflet_z+distance_wat):
                    z_min = -(leaflet_z+distance_wat)
                if z_max < (leaflet_z+distance_wat):
                    z_max =  (leaflet_z+distance_wat)
                if self.xygauss:
                    z_max += float(self.xygauss[2])
            z_len = z_max-z_min

            if x_len > X_len:
                X_min = x_min; X_max = x_max; X_len = x_len
            if y_len > Y_len:
                Y_min = y_min; Y_max = y_max; Y_len = y_len
            Z_dim = [(z_min,z_max,z_len)]*len(composition)

        content_header_extra = ""
        if X_min < -1000 or X_max > 1000 or Y_min < -1000 or Y_max > 1000 or Z_dim[0][0] < -1000 or Z_dim[0][0]+sum([zdim[2] for zdim in Z_dim]) > 1000:
            logger.warning("WARNING:The size of the system is bigger than the default accepted values for PACKMOL. The flag sidemax will be added.")
            content_header_extra += f"sidemax {max(abs(max(X_max,Y_max,Z_dim[0][0]+sum([zdim[2] for zdim in Z_dim]))),abs(min(X_min,Y_min,Z_dim[0][0])))}\n"

        lipids = self.lipids
        prot_data1 = """
     Information for packing:

     Input PDB(s)                     = %-9s
     Output PDB                       = %-9s
     Packmol output and log prefix    = %-9s
     Lipids                           = %-9s
     Lipid ratio                      = %-9s
     Solvents                         = %-9s
     Solvent ratio                    = %-9s
     Salt concentration            (M)= %-9s
     Distance to boundaries        (A)= %-9s
     Minimum water distance        (A)= %-9s
     Packmol loops                    = %-9s
     Packmol loops for All-together   = %-9s"""

        if not self.solvate:
            logger.info(prot_data1 % ( self.pdb, self.outfile, self.packlog, lipids, self.ratio, self.solvents, self.solvent_ratio, self._saltcon, distance, distance_wat, self.nloop, self.nloop_all))
        else:
            logger.info(prot_data1 % ( self.pdb, self.outfile, self.packlog, "-", "-", self.solvents, self.solvent_ratio, self._saltcon, distance, distance_wat, self.nloop, self.nloop_all))
        if self.curvature is not None:
            logger.info(f" Membrane curvature          (1/A)= {self.curvature:<9s} ")
        elif self.xygauss:
            logger.info(" XY Gauss curvature (s_x,s_y,h)   = %s %s %s " % tuple(self.xygauss))

        box_info = """
     Box information:
     x_min                    = %-9s
     x_max                    = %-9s
     x_len                    = %-9s

     y_min                    = %-9s
     y_max                    = %-9s
     y_len                    = %-9s

     z_min                    = %-9s
     z_max                    = %-9s
     z_len                    = %-9s
     """
        logger.debug(box_info % ( X_min, X_max, X_len, Y_min, Y_max, Y_len, Z_dim[0][0], Z_dim[0][0]+sum([zdim[2] for zdim in Z_dim]), sum([zdim[2] for zdim in Z_dim]) ))
        self.X_len = X_len
        self.Y_len = Y_len
        self.Z_dim = Z_dim

        if os.path.exists(self.outfile) and not self.overwrite:
            logger.info(f"Packed PDB {self.outfile} found. Skipping PACKMOL")
            return False

        return {
            'X_min': X_min, 'X_max': X_max, 'X_len': X_len,
            'Y_min': Y_min, 'Y_max': Y_max, 'Y_len': Y_len,
            'Z_dim': Z_dim, 'memvol': memvol, 'solvol': solvol, 'charges': charges,
            'content_header_extra': content_header_extra,
            'minmax': minmax,
            'max_rad': max_rad,
            'z_offset_ds': z_offset_ds,
        }
    
    def _build_ion_block(self, ion_pdb, count, bilayer, z_offset, leaflet_z,
                         X_min, Y_min, X_max, Y_max, Z_dim, composition,
                         is_upper, sphere_radius=None):
        """Build a PACKMOL constraint block for placing ions in one leaflet region.

        Args:
            ion_pdb: Ion PDB filename (e.g. 'K+.pdb').
            count: Number of ions to place.
            bilayer: Current bilayer index.
            z_offset: Z-axis offset for multi-bilayer stacking.
            leaflet_z: Half-thickness of the membrane leaflet.
            X_min, Y_min, X_max, Y_max: XY box boundaries.
            Z_dim: Z dimension list per bilayer.
            composition: Composition dict (used for boundary checks).
            is_upper: If True, place above membrane; if False, place below.
            sphere_radius: Radius for curved membrane mode, or None.

        Returns:
            str: PACKMOL constraint block string.
        """
        block = f"structure {ion_pdb}\n"
        block += f"  nloop {self.nloop}\n"
        block += f"  number {int(count)}\n"
        if self.curvature is not None:
            if not self.pbc:
                block += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
            if is_upper:
                block += f"  outside sphere 0. 0. {-sphere_radius} {sphere_radius+leaflet_z+z_offset}\n"
            else:
                block += f"  inside sphere 0. 0. {-sphere_radius} {sphere_radius-leaflet_z+z_offset}\n"
        elif self.xygauss:
            if not self.pbc:
                block += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
            if is_upper:
                block += f"  over xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {leaflet_z+z_offset} {self.xygauss[2]}\n"
            else:
                block += f"  below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {-leaflet_z+z_offset} {self.xygauss[2]}\n"
        else:
            if self.pbc:
                if is_upper:
                    block += f"  above plane 0. 0. 1. {leaflet_z+z_offset}\n"
                    if bilayer+1 < len(composition):
                        block += f"  below plane 0. 0. 1. {Z_dim[bilayer][1]+z_offset:.2f}\n"
                else:
                    block += f"  below plane 0. 0. 1. {-leaflet_z+z_offset}\n"
                    if bilayer > 0:
                        block += f"  above plane 0. 0. 1. {Z_dim[bilayer][0]+z_offset:.2f}\n"
            else:
                if is_upper:
                    block += f"  inside box {X_min:.2f} {Y_min:.2f} {leaflet_z+z_offset} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                else:
                    block += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {-leaflet_z+z_offset}\n"
        block += "end structure\n\n"
        return block

    def _build_packmol_input(self, composition, apl_offset, lipnum_set, content_header, geom, pdbtar):
        """Build the complete PACKMOL input script from geometry and composition.

        Generates all PACKMOL constraint blocks for proteins, lipids (per leaflet),
        ions, solvents, and solutes. Calculates lipid counts from APL or explicit
        numbers, determines ion counts for charge neutralization and salt
        concentration, and assembles the final self.contents string.

        Args:
            composition: Nested dict of lipid compositions per bilayer/leaflet.
            apl_offset: APL scaling factors per bilayer/leaflet.
            lipnum_set: Explicit lipid counts (empty if using ratios).
            content_header: PACKMOL header string from _build_packmol_header().
            geom: Geometry dict from _process_proteins_and_geometry().
            pdbtar: Opened tarfile containing lipid PDB structures.

        Returns:
            bool: True on success, sets self.contents with the PACKMOL input.
        """
        leaflet_z = self._leaflet_z
        lip_offset = self._lip_offset
        bound_tail = self._bound_tail
        bound_head = self._bound_head
        saltcon = self._saltcon
        cation = self._cation
        anion = self._anion
        override_salt = self._override_salt
        apl = self._apl
        solvent_ratios = self._solvent_ratios
        solvent_con = self._solvent_con
        lipids = self.lipids

        X_min = geom['X_min']; X_max = geom['X_max']; X_len = geom['X_len']
        Y_min = geom['Y_min']; Y_max = geom['Y_max']; Y_len = geom['Y_len']
        Z_dim = geom['Z_dim']; memvol = geom['memvol']; solvol = geom['solvol']
        charges = geom['charges']
        content_header += geom['content_header_extra']
        minmax = geom['minmax']
        max_rad = geom['max_rad']
        z_offset_ds = geom['z_offset_ds']

        sphere_radius = self._sphere_radius if self.curvature is not None else None

        content_prot = content_lipid = content_solvent = content_ion = content_solute = ""

        pond_lip_vol_dict      = {}
        pond_lip_apl_dict      = {}
        lipnum_dict            = {}
        lipnum_area_dict       = {}

        z_offset = 0

        for n, bilayer in enumerate(composition):
            if bilayer > 0:
                if self.double_span:
                    z_offset = z_offset_ds
                else:
                    z_offset = z_offset+Z_dim[bilayer-1][1]-Z_dim[bilayer][0]

            ################################## PROTEIN ###################################

            if not self.onlymembrane:
                if self.pdb[bilayer] != "None":
                    self.created_notrun.append(f"PROT{bilayer}.pdb")
                    if self.sirah:
                        self.created_notrun.append(f"PROT{bilayer}_cg.pdb")
                        content_prot += f"structure PROT{bilayer}_cg.pdb\n"
                    else:
                        content_prot += f"structure PROT{bilayer}.pdb\n"
                    content_prot += "  number 1\n"
                    content_prot += f"  fixed 0. 0. {z_offset} 0. 0. 0.\n"
                    content_prot += f"  radius {self.prot_rad}\n"
                    content_prot += "end structure\n\n"

            ################################ LIPIDS ######################################

            if self.curvature is not None:
                lipid_vol_up           = sphere_integral_square(X_min,X_max,Y_min,Y_max,r1=sphere_radius+z_offset,r2=sphere_radius+z_offset+leaflet_z,c=-sphere_radius)-memvol[bilayer][1]
                lipid_vol_down         = sphere_integral_square(X_min,X_max,Y_min,Y_max,r1=sphere_radius+z_offset-leaflet_z,r2=sphere_radius+z_offset,c=-sphere_radius)-memvol[bilayer][0]
            elif self.xygauss:
                lipid_vol_up           = gauss_integral_square(X_min,X_max,Y_min,Y_max,*map(float,self.xygauss),g1=z_offset,g2=z_offset+leaflet_z)-memvol[bilayer][1]
                lipid_vol_down         = gauss_integral_square(X_min,X_max,Y_min,Y_max,*map(float,self.xygauss),g1=z_offset-leaflet_z,g2=z_offset)-memvol[bilayer][0]
            else:
                lipid_vol_up           = ((X_len+2*lip_offset)*(Y_len+2*lip_offset)*leaflet_z)-memvol[bilayer][1]
                lipid_vol_down         = ((X_len+2*lip_offset)*(Y_len+2*lip_offset)*leaflet_z)-memvol[bilayer][0]
            lipid_vol              = (lipid_vol_down,lipid_vol_up)
            lipid_area             = X_len*Y_len # if curvature, will be defined in loop
            if self.xygauss:
               lipid_area          = gauss_rectangle_area(X_min,X_max,Y_min,Y_max, *map(float,self.xygauss))
            pond_lip_vol_dict[bilayer]      = {}
            pond_lip_apl_dict[bilayer]      = {}
            lipnum_dict[bilayer]            = {}
            lipnum_area_dict[bilayer]       = {}
            for leaflet in composition[bilayer]:
                if self.curvature is not None:
                    if leaflet < 1:
                        #lipid_area    = sphere_rectangle_area(sphere_radius+z_offset-leaflet_z,sphere_dist(sphere_radius,X_len),sphere_dist(sphere_radius,Y_len))
                        lipid_area    = sphere_rectangle_area(sphere_radius+z_offset-leaflet_z,X_len,Y_len)
                        logger.debug(f"Curvature lower leaflet area:{lipid_area}")
                    else:
                        #lipid_area    = sphere_rectangle_area(sphere_radius+z_offset+leaflet_z,sphere_dist(sphere_radius,X_len),sphere_dist(sphere_radius,Y_len))
                        lipid_area    = sphere_rectangle_area(sphere_radius+z_offset+leaflet_z,X_len,Y_len)
                        logger.debug(f"Curvature upper leaflet area:{lipid_area}")
                pond_lip_vol = 0
                pond_lip_apl = 0
                for lipid in composition[bilayer][leaflet]:
                    if self.parameters[lipid]["V"] == "XXXX":
                        if self.parameters[lipid]["C"] == "X":
                            logger.critical("CRITICAL:\n  Volume not specified and can not be estimated! Check the parameter file")
                            sys.exit(1)
                        nCH3,nCH2,nCH = list(map(int,self.parameters[lipid]["C"].split(":")))
                        self.parameters[lipid]["V"] = str(int(round(float(self.parameters[lipid]["VH"])+nCH3*2*VCH2+nCH2*VCH2+nCH*VCH)))         #doi:10.1016/j.bbamem.2005.07.006
                        logger.debug(f"Experimental value for {lipid} volume not available in parm file. Using estimated {self.parameters[lipid]['V']} A^3 instead...")
                    if self.parameters[lipid][apl] == "XX":
                        try:
                            self.parameters[lipid][apl] = max([float(self.parameters[lip][apl]) for lip in self.parameters if (is_number(self.parameters[lip][apl]) and lip.endswith(lipid[-2:]))])
                            logger.debug("Taking maximal APL of lipids with headgroup "+lipid[-2:])
                        except ValueError:
                            self.parameters[lipid][apl] = "75"
                            logger.debug("No other lipid with same headgroup has APL. Setting APL of 75 to "+lipid[-2:])
                        logger.debug(f"Value for {lipid} area per lipid not available in parm file. Using {self.parameters[lipid][apl]} A^2 instead...")
                    #If lipnum instead of ratio, values will be total volume and area instead of ponderated.
                    pond_lip_vol += composition[bilayer][leaflet][lipid]*int(self.parameters[lipid]["V"])
                    pond_lip_apl += composition[bilayer][leaflet][lipid]*int(self.parameters[lipid][apl])
                pond_lip_apl = pond_lip_apl*apl_offset[bilayer][leaflet]
                pond_lip_vol_dict[bilayer][leaflet]      = pond_lip_vol
                pond_lip_apl_dict[bilayer][leaflet]      = pond_lip_apl
                if self.lipnum is None:
                    lipnum = lipid_vol[leaflet]/pond_lip_vol
                    lipnum_area = lipid_area/pond_lip_apl-(memvol[bilayer][leaflet]/pond_lip_vol)
                    lipnum_dict[bilayer][leaflet]            = lipnum
                    lipnum_area_dict[bilayer][leaflet]       = lipnum_area
                else:
                    lipnum_dict[bilayer][leaflet] = lipnum_area_dict[bilayer][leaflet] = 1
                    x_len = y_len = np.sqrt(pond_lip_apl)
                    logger.debug(f"x_len={x_len}, X_len={X_len}")
                    if x_len > X_len:
                        X_min = -x_len/2; X_max = x_len/2; X_len = x_len
                        Y_min = -y_len/2; Y_max = y_len/2; Y_len = y_len

            charge_lip = charge_solute = 0
            if not self.vol:
                lipnum_dict = lipnum_area_dict


    
            ################################ SOLUTE ######################################

            if not self.solvate:
                if self.solute is not None and self.solute_inmem:
                    for i,sol in enumerate(self.solute):
                        logger.info(f"Adding {self.solute_con[i]} {self.solute[i]} to the lipid volume")
                        grid_file, solute_vol      = self.pdbvol(self.solute[i])
                        self.created.append(grid_file)
                        if self.solute_con[i].endswith("M") and is_number(self.solute_con[i][:-1]):
                            solute_num      = int(float(self.solute_con[i][:-1])*((sum(lipid_vol)*avogadro/(1*10**27))))
                        elif self.solute_con[i].endswith("%") and is_number(self.solute_con[i][:-1]):
                            solute_num      = int(float(self.solute_con[i][:-1])/100*((sum(lipid_vol)/solute_vol)))
                            solute_vol_tot  = int(float(self.solute_con[i][:-1])/100*(sum(lipid_vol)))
                        elif is_number(self.solute_con[i]):
                            try:
                                int(self.solute_con[i])
                            except (ValueError, TypeError):
                                logger.error("ERROR:\n    A number less than 1 is specified. If a concentration was intended, add M/% as a suffix!")
                                sys.exit(1)
                            solute_num      = int(self.solute_con[i])
                        else:
                            logger.error("ERROR:\n    The format used to specify the number of molecules is not correct! It has to be a number or a number with an M/% suffix.")
                            sys.exit(1)
                        if solute_num < 1:
                            logger.error("ERROR:\n    The solute concentration is too low for the calculated box size. Try increasing the concentration.")
                            sys.exit(1)
                        if not self.solute_con[i].endswith("%"):
                            solute_vol_tot  = solute_vol*solute_num
                        charge_solute += self.solute_charge[i]*solute_num
                        for leaflet in lipnum_dict[bilayer]:
                            lipnum_dict[bilayer][leaflet] -= int((solute_vol_tot)/(2*pond_lip_vol_dict[bilayer][leaflet]))

                        content_solute += f"structure {self.solute[i]}\n"
                        content_solute += f"  number {int(solute_num)}\n"
                        if self.solute_prot_dist is not None and self.pdb[bilayer] != "None":
                            content_solute += f"  outside cylinder 0. 0. {minmax[2]-self.solute_prot_dist} 0. 0. 1. {max_rad+self.solute_prot_dist} {minmax[5]-minmax[2]+self.solute_prot_dist} \n"
                        if self.curvature is not None:
                            if not self.pbc:
                                content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solute += f"  inside sphere 0. 0. {-sphere_radius} {z_offset+sphere_radius+leaflet_z}\n"
                            content_solute += f"  outside sphere 0. 0. {-sphere_radius} {z_offset+sphere_radius-leaflet_z}\n"
                        elif self.xygauss:
                            if not self.pbc:
                                content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solute += f"  below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {z_offset+leaflet_z} {self.xygauss[2]}\n"
                            content_solute += f"  over xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {z_offset-leaflet_z} {self.xygauss[2]}\n"
                        elif not self.pbc:
                            content_solute += f"  inside box {X_min*lip_offset:.2f} {Y_min*lip_offset:.2f} {z_offset-leaflet_z} {X_max*lip_offset:.2f} {Y_max*lip_offset:.2f} {z_offset+leaflet_z}\n"
                        content_solute += "end structure\n\n"
                elif (self.solute is not None or self.solute_con is not None) and self.solute_inmem:
                    logger.error("ERROR:\n    The solute parameters are incomplete. Please include both a solute pdb and a concentration.")
                    sys.exit(1)


            if not self.solvate:
                for leaflet in composition[bilayer]:
                    for lipid in sorted(composition[bilayer][leaflet], reverse=True, key=lambda x: composition[bilayer][leaflet][x]):
                        if self.headplane is None:
                            bound_head=float(self.parameters[lipid]["h_bound"])
                            if bound_head >= leaflet_z:
                                logger.error(f"ERROR:\n    The boundary for {lipid} head group is out of the space delimited for the membrane by the membrane width {leaflet_z}. Please consider increasing the value!")
                                sys.exit(1)
                        if self.tailplane is None:
                            bound_tail=float(self.parameters[lipid]["t_bound"])
                            if bound_tail <=0:
                                logger.error(f"ERROR:\n    The boundary for {lipid} tail is out of the space delimited for the membrane by the membrane center at the z axis origin (it must be a positive value greater than 0). Please consider increasing the value!")
                                sys.exit(1)
                        if not os.path.isfile(f"./{lipid}.pdb"):
                            try:
                                shutil.copy(f"{script_path}{self._rep}/pdbs/{lipid}.pdb", "./")
                            except OSError:
                                pdbtar.extract(f"{lipid}.pdb")
                            self.created_notrun.append(f"{lipid}.pdb")

                        content_lipid += f"structure {lipid}.pdb\n"
                        sp = 0
                        if lipid in sterols_rings or "PI" in lipid or any([lipid.endswith(e) for e in ["DG","MG","SQ","GG","SG"]]): ## Avoid ring piercing by lipid tails, adding extra radius. Later remove those piercing despite this (find_piercing_lipids). Add inositol rings as well!
                            if "PI" in lipid:
                                _pdb = pdb_parse_TER(f"{lipid}.pdb", onlybb=False)
                                _atom_string = " ".join([ str(_a[3]) for _a in _pdb[list(_pdb.keys())[0]].keys() if _a[0] in PI_res and _a[2] in PI_ring_probe])
                                if _atom_string.strip() != '':
                                    content_lipid += f"  atoms {_atom_string}\n"
                                    content_lipid +=  "    radius 1.5\n"
                                    content_lipid +=  "  end atoms\n"
                            elif any([lipid.endswith(e) for e in ["DG","MG","SQ","GG","SG"]]):
                                _pdb = pdb_parse_TER(f"{lipid}.pdb", onlybb=False)
                                _atom_string = " ".join([ str(_a[3]) for _a in _pdb[list(_pdb.keys())[0]].keys() if _a[0] in GG_res and _a[2] in MGG_ring_probe])
                                if lipid.endswith("DG"):
                                    _atom_string += " " + " ".join([ str(_a[3]) for _a in _pdb[list(_pdb.keys())[0]].keys() if _a[0] in GG_res and _a[2] in DGG_ring_probe])
                                if _atom_string.strip() != '':
                                    content_lipid += f"  atoms {_atom_string}\n"
                                    content_lipid +=  "    radius 1.5\n"
                                    content_lipid +=  "  end atoms\n"
                            else:
                                content_lipid += "  radius 1.5\n"
                            if sum([composition[bilayer][leaflet][l] for l in composition[bilayer][leaflet] if l in sterols_rings]) < 0.5 and (X_len > 50 and Y_len > 50): # only enable if less then half of the composition of the leaflet are sterols
                                if not self.pbc:
                                    logger.info(f"Adding 5A padding to the sterol or PI {lipid} components to avoid piercing in the periodic boundary")
                                    sp = 5 #Safety padding to avoid having sterols in the system rim and piercing from periodic image. Taking about "a lipid" width
                            else:
                                logger.warning("Sterols and/or PI are used, and the concentration is too high or the system too small to add proper side padding. Check that your system doesn't have pierced sterols or PI in the periodic boundary once the packing is finished")
                        content_lipid += f"  nloop {self.nloop}\n"
                        if int(round(composition[bilayer][leaflet][lipid]*lipnum_dict[bilayer][leaflet])) < 1:
                            logger.error(f"ERROR:\n    The ratio for lipid {lipid} is too small for the given/estimated system size. Either increase the ratio or make the system bigger!")
                            sys.exit(1)
                        content_lipid += f"  number {int(round(composition[bilayer][leaflet][lipid]*lipnum_dict[bilayer][leaflet]))}\n"

                        if not self.pbc:
                            if self.curvature is not None or self.xygauss or self.self_assembly:
                                content_lipid += f"  inside box {round(X_min*lip_offset,2)+sp} {round(Y_min*lip_offset,2)+sp} {Z_dim[bilayer][0]+z_offset} {round(X_max*lip_offset,2)-sp} {round(Y_max*lip_offset,2)-sp} {Z_dim[bilayer][1]+z_offset}\n"
                            else:
                                content_lipid += f"  inside box {round(X_min*lip_offset,2)+sp} {round(Y_min*lip_offset,2)+sp} {z_offset-leaflet_z+leaflet_z*leaflet} {round(X_max*lip_offset,2)-sp} {round(Y_max*lip_offset,2)-sp} {z_offset+leaflet_z*leaflet}\n"

                        if self.channel_plug is not None and self.pdb[bilayer] != "None":
                            if self.channel_plug == 0:
                                self.channel_plug = max_rad/2
                            content_lipid += f"  outside cylinder 0. 0. {minmax[2]} 0. 0. 1. {self.channel_plug} {minmax[5]-minmax[2]} \n"

                        if not self.self_assembly:
                            p_atms = " ".join(self.parameters[lipid]["p_atm"].split(","))
                            content_lipid += f"  atoms {p_atms}\n"
                            if leaflet == 0:
                                if self.curvature is not None:
                                    content_lipid += f"    inside sphere 0. 0. {-sphere_radius} {sphere_radius-bound_head+z_offset}\n"
                                elif self.xygauss:
                                    content_lipid += f"    below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {-bound_head+z_offset} {self.xygauss[2]}\n"
                                else:
                                    content_lipid += f"    below plane 0. 0. 1. {-bound_head+z_offset}\n"
                            else:
                                if self.curvature is not None:
                                    content_lipid += f"    outside sphere 0. 0. {-sphere_radius} {sphere_radius+bound_head+z_offset}\n"
                                elif self.xygauss:
                                    content_lipid += f"    over xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {bound_head+z_offset} {self.xygauss[2]}\n"
                                else:
                                    content_lipid += f"    over plane 0. 0. 1. {bound_head+z_offset}\n"
                            content_lipid += "  end atoms\n"
                            t_atms = " ".join(self.parameters[lipid]["t_atm"].split(","))
                            content_lipid += f"  atoms {t_atms}\n"
                            if leaflet == 0:
                                if self.curvature is not None:
                                    content_lipid += f"    outside sphere 0. 0. {-sphere_radius} {sphere_radius-bound_tail+z_offset}\n"
                                elif self.xygauss:
                                    content_lipid += f"    over xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {-bound_tail+z_offset} {self.xygauss[2]}\n"
                                else:
                                    content_lipid += f"    over plane 0. 0. 1. {-bound_tail+z_offset}\n"
                            else:
                                if self.curvature is not None:
                                    content_lipid += f"    inside sphere 0. 0. {-sphere_radius} {sphere_radius+bound_tail+z_offset}\n"
                                elif self.xygauss:
                                    content_lipid += f"    below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {bound_tail+z_offset} {self.xygauss[2]}\n"
                                else:
                                    content_lipid += f"    below plane 0. 0. 1. {bound_tail+z_offset}\n"
                            content_lipid += "  end atoms\n"
                        content_lipid += "end structure\n\n"

            ######################## WATER && SOLUTE #####################################

            for solvent in self.solvents.split(":"):
                solvent_pdb = f"{solvent}.pdb"
                if os.path.isfile(solvent_pdb):
                    logger.info(f"Using {solvent_pdb} in the folder")
                else:
                    try:
                        shutil.copy(os.path.join(script_path, self._rep, "pdbs", solvent_pdb), "./")
                    except OSError:
                        pdbtar.extract(solvent_pdb)
                    self.created_notrun.append(solvent_pdb)
                if not os.path.isfile(solvent_pdb):
                    logger.critical(f"CRITICAL:{solvent_pdb} is not to found in the folder!")
                    sys.exit(1)

            if self.curvature is not None:
                solvent_vol_up           = sphere_integral_square(X_min,X_max,Y_min,Y_max,r1=sphere_radius+z_offset+leaflet_z,z_max=Z_dim[bilayer][1]+z_offset,c=-sphere_radius)-solvol[bilayer][1]
                solvent_vol_down         = sphere_integral_square(X_min,X_max,Y_min,Y_max,z_min=Z_dim[bilayer][0]+z_offset,r2=sphere_radius+z_offset-leaflet_z,c=-sphere_radius)-solvol[bilayer][0]
            elif self.xygauss:
                solvent_vol_up           = gauss_integral_square(X_min,X_max,Y_min,Y_max,*map(float,self.xygauss),g1=z_offset+leaflet_z,z_max=Z_dim[bilayer][1]+z_offset)-solvol[bilayer][1]
                solvent_vol_down         = gauss_integral_square(X_min,X_max,Y_min,Y_max,*map(float,self.xygauss),z_min=Z_dim[bilayer][0]+z_offset,g2=z_offset-leaflet_z)-solvol[bilayer][0]
            else:
                solvent_vol_up   = (X_len*Y_len*(abs(Z_dim[bilayer][1])-leaflet_z))-solvol[bilayer][1]
                solvent_vol_down = (X_len*Y_len*(abs(Z_dim[bilayer][0])-leaflet_z))-solvol[bilayer][0]
            if self.solvate:
                solvent_vol_up   = solvent_vol_up+lipid_vol_up
                solvent_vol_down = solvent_vol_down+lipid_vol_down
            solvent_vol_tot = solvent_vol_up+solvent_vol_down
            watnum_up = int(solvent_vol_up*solvent_con)
            watnum_down = int(solvent_vol_down*solvent_con)
    
            if self.solute is not None and not self.solute_inmem:
                for i,sol in enumerate(self.solute):
                    logger.info(f"Adding {self.solute_con[i]} {self.solute[i]} to the water volume")
                    grid_file, solute_vol      = self.pdbvol(self.solute[i])
                    self.created.append(grid_file)
                    if self.solute_con[i].endswith("M") and is_number(self.solute_con[i][:-1]):
                        solute_up       = int(float(self.solute_con[i][:-1])*((solvent_vol_up*avogadro/(1*10**27))))
                        solute_down     = int(float(self.solute_con[i][:-1])*((solvent_vol_down*avogadro/(1*10**27))))
                    elif self.solute_con[i].endswith("%") and is_number(self.solute_con[i][:-1]):
                        solute_up       = int(float(self.solute_con[i][:-1])/100*((solvent_vol_up/solute_vol)))
                        solute_down     = int(float(self.solute_con[i][:-1])/100*((solvent_vol_down/solute_vol)))
                        solute_vol_up   = int(float(self.solute_con[i][:-1])/100*(solvent_vol_up))
                        solute_vol_down = int(float(self.solute_con[i][:-1])/100*(solvent_vol_down))
                    elif is_number(self.solute_con[i]):
                        try:
                            int(self.solute_con[i])
                        except (ValueError, TypeError):
                            logger.error("ERROR:\n    A number less than 1 is specified. If a concentration was intended, add M as a suffix!")
                            sys.exit(1)
                        solute_up, solute_down = distribute_integer(int(self.solute_con[i]),[solvent_vol_up,solvent_vol_down])
                    else:
                        logger.error("ERROR:\n    The format used to specify the number of molecules is not correct! It has to be a number or a number with an M/% suffix.")
                        sys.exit(1)
                    if not self.solute_con[i].endswith("%"):
                        solute_vol_up   = solute_vol*solute_up
                        solute_vol_down = solute_vol*solute_down
                    watnum_up       = watnum_up-int((solute_vol_up)*solvent_con)
                    watnum_down     = watnum_down-int((solute_vol_down)*solvent_con)
                    if solute_up+solute_down < 1:
                        logger.error("ERROR:\n    The solute concentration is too low for the calculated box size. Try increasing the concentration.")
                        sys.exit(1)
                    charge_solute += self.solute_charge[i]*(solute_down+solute_up)
                    if not self.solvate and not self.self_assembly:
                        if solute_down > 0:
                            content_solute += f"structure {self.solute[i]}\n"
                            content_solute += f"  nloop {self.nloop}\n"
                            content_solute += f"  number {solute_down}\n"
                            if self.solute_prot_dist is not None and self.pdb[bilayer] != "None":
                                content_solute += f"  outside cylinder 0. 0. {minmax[2]-self.solute_prot_dist} 0. 0. 1. {max_rad+self.solute_prot_dist} {minmax[5]-minmax[2]+self.solute_prot_dist} \n"
                            if self.curvature is not None:
                                if not self.pbc:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                                content_solute += f"  inside sphere 0. 0. {-sphere_radius} {sphere_radius-leaflet_z+z_offset}\n"
                            elif self.xygauss:
                                if not self.pbc:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                                content_solute += f"  below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {-leaflet_z+z_offset} {self.xygauss[2]}\n"
                            else:
                                if self.pbc:
                                    content_solute += f"  below plane 0. 0. 1. {-leaflet_z+z_offset}\n"
                                else:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {-leaflet_z+z_offset}\n"
                            content_solute += "end structure\n\n"
                        if solute_up > 0:
                            content_solute += f"structure {self.solute[i]}\n"
                            content_solute += f"  nloop {self.nloop}\n"
                            content_solute += f"  number {solute_up}\n"
                            if self.solute_prot_dist is not None and self.pdb[bilayer] != "None":
                                content_solute += f"  outside cylinder 0. 0. {minmax[2]-self.solute_prot_dist} 0. 0. 1. {max_rad+self.solute_prot_dist} {minmax[5]-minmax[2]+self.solute_prot_dist} \n"
                            if self.curvature is not None:
                                if not self.pbc:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                                content_solute += f"  outside sphere 0. 0. {-sphere_radius} {sphere_radius+leaflet_z+z_offset}\n"
                            elif self.xygauss:
                                if not self.pbc:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                                content_solute += f"  below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {leaflet_z+z_offset} {self.xygauss[2]}\n"
                            else:
                                if self.pbc:
                                    content_solute += f"  above plane 0. 0. 1. {leaflet_z+z_offset}\n"
                                else:
                                    content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {leaflet_z+z_offset} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                            content_solute += "end structure\n\n"
                    else:
                        content_solute += f"structure {self.solute[i]}\n"
                        content_solute += f"  nloop {self.nloop}\n"
                        content_solute += f"  number {solute_down+solute_up}\n"
                        if self.solute_prot_dist is not None and self.pdb[bilayer] != "None":
                                content_solute += f"  outside cylinder 0. 0. {minmax[2]-self.solute_prot_dist} 0. 0. 1. {max_rad+self.solute_prot_dist} {minmax[5]-minmax[2]+self.solute_prot_dist} \n"
                        if not self.pbc:
                            content_solute += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                        content_solute += "end structure\n\n"
    
            elif (self.solute is not None or self.solute_con is not None) and not self.solute_inmem:
                logger.error("ERROR:\n    The solute parameters are incomplete. Please include both a solute pdb and a concentration.")
                sys.exit(1)
    
            ################################# SALT & CHARGES #############################
    
            pos_up = pos_down = 0
            neg_up = neg_down = 0
            charge = charges[bilayer]
            if not self.solvate:
                for leaflet in composition[bilayer]:
                    for lipid in composition[bilayer][leaflet]:
                        charge_lip += int(round(composition[bilayer][leaflet][lipid]*lipnum_dict[bilayer][leaflet]))*int(self.parameters[lipid]["charge"])
            if charge_lip != 0:
                logger.debug(f"The lipids contribute a charge of {charge_lip} to the system. It will be considered for the neutralization.")
                charge += charge_lip
            if charge_solute != 0:
                logger.debug(f"The solutes contribute a charge of {charge_solute} to the system. It will be considered for the neutralization.")
                charge += charge_solute
            if charge > 0:
                neg_up = int(round(charge*(solvent_vol_up/(solvent_vol_tot))))
                neg_down = int(round(charge*(solvent_vol_down/(solvent_vol_tot))))
            else:
                pos_up = int(round((abs(charge)/self.ion_dict[self.salt_c][1])*(solvent_vol_up/(solvent_vol_tot))))
                pos_down = int(round((abs(charge)/self.ion_dict[self.salt_c][1])*(solvent_vol_down/(solvent_vol_tot))))
            con_pos = (pos_up+pos_down)/((solvent_vol_tot)*avogadro/(1*10**27))
            con_neg = (neg_up+neg_down)/((solvent_vol_tot)*avogadro/(1*10**27))
            if self.salt:
                if con_pos > saltcon or con_neg > saltcon*self.ion_dict[self.salt_c][1]:
            #        print pos_up, pos_down, neg_up, neg_down, saltnum_up, saltnum_down
                    logger.warning("""WARNING:
                The concentration of ions required to neutralize the system is higher than the concentration specified.
                Either increase the salt concentration by using the --saltcon flag or run the script without the --salt flag.""")
                    logger.info(f"Positive ion concentration: {con_pos:.3f}")
                    logger.info(f"Negative ion concentration: {con_neg:.3f}")
                    logger.info(f"Salt concentration specified: {saltcon}")
                    if override_salt:
                        if self.verbose:
                            logger.info("Overriding salt concentration...")
                        saltcon = max(con_pos,con_neg)
                        pass
                    else:
                        sys.exit(
                            "The concentration of ions required to neutralize the system "
                            "is higher than the concentration specified. "
                            "Either increase the salt concentration (--saltcon) or "
                            "run without the --salt flag."
                        )
                saltnum_up   = int(solvent_vol_up*saltcon*avogadro/(1*10**27))
                saltnum_down = int(solvent_vol_down*saltcon*avogadro/(1*10**27))
    
                if abs(charge)/2 < min(saltnum_up,saltnum_down):
                    pos_up   += saltnum_up-abs(charge)/(self.ion_dict[self.salt_c][1]*2)
                    pos_down += saltnum_down-abs(charge)/(self.ion_dict[self.salt_c][1]*2)
                    neg_up   += saltnum_up*self.ion_dict[self.salt_c][1]-abs(charge)/2
                    neg_down += saltnum_down*self.ion_dict[self.salt_c][1]-abs(charge)/2
    
                if self.charge_imbalance != 0:
                    if n % 2 == 0:
                        if self.imbalance_ion == "cat":
                            pos_up   += self.charge_imbalance/self.ion_dict[self.salt_c][1]
                            pos_down -= self.charge_imbalance/self.ion_dict[self.salt_c][1]
                        else:
                            neg_up   -= self.charge_imbalance
                            neg_down += self.charge_imbalance
                    else:
                        if self.imbalance_ion == "cat":
                            pos_up   -= self.charge_imbalance/self.ion_dict[self.salt_c][1]
                            pos_down += self.charge_imbalance/self.ion_dict[self.salt_c][1]
                        else:
                            neg_up   += self.charge_imbalance
                            neg_down -= self.charge_imbalance
    
                charge_data= """
    Salt and charge info:
    Upper positive charges   = %-9s
    Lower positive charges   = %-9s
    Upper negative charges   = %-9s
    Lower negative charges   = %-9s
    Charge imbalance         = %-9s
    Upper salt number        = %-9s
    Lower salt number        = %-9s
                """
                logger.debug(charge_data % ( pos_up, pos_down, neg_up, neg_down, self.charge_imbalance, saltnum_up, saltnum_down ))
    
                checkup = [pos_up,pos_down,neg_up,neg_down]
                if any(v < 0 for v in checkup):
                    logger.critical("CRITICAL:\n  The applied charge imbalance caused a negative number of ions! Check your input")
                    sys.exit(1)
    
    
            #    new_con_neg = (neg_up+neg_down)/(((solvent_vol_tot)*avogadro/(1*10**27)))
            #    new_con_pos = (pos_up+pos_down)/(((solvent_vol_tot)*avogadro/(1*10**27)))
    
            try:
                shutil.copy(os.path.join(script_path, self._rep, "pdbs", f"{cation}.pdb"), "./")
            except OSError:
                pdbtar.extract(f"{cation}.pdb")
            self.created_notrun.append(f"{cation}.pdb")
            try:
                shutil.copy(os.path.join(script_path, self._rep, "pdbs", f"{anion}.pdb"), "./")
            except OSError:
                pdbtar.extract(f"{anion}.pdb")
            self.created_notrun.append(f"{anion}.pdb")
            if not self.solvate and not self.self_assembly:
                ion_args = dict(bilayer=bilayer, z_offset=z_offset, leaflet_z=leaflet_z,
                                X_min=X_min, Y_min=Y_min, X_max=X_max, Y_max=Y_max,
                                Z_dim=Z_dim, composition=composition, sphere_radius=sphere_radius)
                if pos_down > 0:
                    content_ion += self._build_ion_block(f"{cation}.pdb", pos_down, is_upper=False, **ion_args)
                if pos_up > 0:
                    content_ion += self._build_ion_block(f"{cation}.pdb", pos_up, is_upper=True, **ion_args)
                if neg_down > 0:
                    content_ion += self._build_ion_block(f"{anion}.pdb", neg_down, is_upper=False, **ion_args)
                if neg_up > 0:
                    content_ion += self._build_ion_block(f"{anion}.pdb", neg_up, is_upper=True, **ion_args)
            else:
                if pos_down+pos_up > 0:
                    content_ion += f"structure {cation}.pdb\n"
                    content_ion += f"  nloop {self.nloop}\n"
                    content_ion += f"  number {int(pos_down+pos_up)}\n"
                    if not self.pbc:
                        content_ion += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                    content_ion += "end structure\n\n"
                if neg_down+neg_up > 0:
                    content_ion += f"structure {anion}.pdb\n"
                    content_ion += f"  nloop {self.nloop}\n"
                    content_ion += f"  number {int(neg_down+neg_up)}\n"
                    if not self.pbc:
                        content_ion += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                    content_ion += "end structure\n\n"
    
            for i, solvent in enumerate(self.solvents.split(":")):
                solvent_pdb   = f"{solvent}.pdb"
                solvents_up   = int((watnum_up/solvent_con)*(solvent_ratios[i]/float(sum(solvent_ratios)))*(avogadro/(1*10**24))*(float(self.sparameters[solvent]["density"])/float(self.sparameters[solvent]["MW"])))
                solvents_down = int((watnum_down/solvent_con)*(solvent_ratios[i]/float(sum(solvent_ratios)))*(avogadro/(1*10**24))*(float(self.sparameters[solvent]["density"])/float(self.sparameters[solvent]["MW"])))

                content_solvent_header = f"structure {solvent_pdb}\n"
                if self.sirah:
                    content_solvent_header += "  atoms 5\n"
                    content_solvent_header += "    radius 2.5\n"
                    content_solvent_header += "  end atoms\n"
                elif solvent == "WAT" and self.watorient:
                    content_solvent_header += "  atoms 1\n"
                    content_solvent_header += "    radius 1.5\n"
                    content_solvent_header += "  end atoms\n"
                content_solvent_header += f"  nloop {self.nloop}\n"

                if not self.solvate and not self.self_assembly:
                    if solvents_down > 0:
                        content_solvent += content_solvent_header
                        content_solvent += f"  number {solvents_down}\n" # deleted -pos_down-neg_down. Was it necessary?
                        if self.curvature is not None:
                            if not self.pbc:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solvent += f"  inside sphere 0. 0. {-sphere_radius} {sphere_radius-leaflet_z+z_offset}\n"
                        elif self.xygauss:
                            if not self.pbc:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solvent += f"  below xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {-leaflet_z+z_offset} {self.xygauss[2]}\n"
                        else:
                            if self.pbc:
                                content_solvent += f"  below plane 0. 0. 1. {-leaflet_z+z_offset}\n"
                                if bilayer > 0:
                                    content_solvent += f"  above plane 0. 0. 1. {Z_dim[bilayer][0]+z_offset:.2f}\n"
                            else:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {-leaflet_z+z_offset}\n"
                        content_solvent += "end structure\n\n"
                    if solvents_up > 0:
                        content_solvent += content_solvent_header
                        content_solvent += f"  number {solvents_up}\n" # deleted -pos_up-neg_up. Was it necessary?
                        if self.curvature is not None:
                            if not self.pbc:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solvent += f"  outside sphere 0. 0. {-sphere_radius} {sphere_radius+leaflet_z+z_offset}\n"
                        elif self.xygauss:
                            if not self.pbc:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]}\n"
                            content_solvent += f"  over xygauss 0. 0. {self.xygauss[0]} {self.xygauss[1]} {leaflet_z+z_offset} {self.xygauss[2]}\n"
                        else:
                            if self.pbc:
                                content_solvent += f"  above plane 0. 0. 1. {leaflet_z+z_offset}\n"
                                if bilayer+1 < len(composition):
                                    content_solvent += f"  below plane 0. 0. 1. {Z_dim[bilayer][1]+z_offset:.2f}\n"
                            else:
                                content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {leaflet_z+z_offset} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                        content_solvent += "end structure\n\n"
                elif solvents_down+solvents_up > 0:
                    content_solvent += content_solvent_header
                    content_solvent += f"  number {solvents_down+solvents_up}\n" # deleted -pos-neg. Was it necessary?
                    if not self.pbc:
                        content_solvent += f"  inside box {X_min:.2f} {Y_min:.2f} {Z_dim[bilayer][0]+z_offset:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[bilayer][1]+z_offset:.2f}\n"
                    content_solvent += "end structure\n\n"
    
            if self.nocounter:
                logger.info("Ions will not be added. PMEMD will assume a counter charge 'plasma'.")
                content_ion = ""
            if self.pbc:
                content_header += f"pbc {X_min:.2f} {Y_min:.2f} {Z_dim[0][0]:.2f} {X_max:.2f} {Y_max:.2f} {Z_dim[0][0]+sum([zdim[2] for zdim in Z_dim]):.2f} \n\n"

            self.contents = content_header+content_prot+content_lipid+content_solvent+content_ion+content_solute

            if not self.solvate:
                box_data = """
                Lower water box vol    = %-9s A^3
                Upper water box vol    = %-9s A^3
                Mem. upper leaflet vol = %-9s A^3
                Mem. lower leaflet vol = %-9s A^3
    
                """
    
                logger.debug(box_data % (round(solvent_vol_down,2), round(solvent_vol_up,2), round(lipid_vol_up,2), round(lipid_vol_down,2)))
            else:
                box_data = """
                Water box vol    = %-9s A^3
    
                """
    
                logger.debug(box_data % (round(solvent_vol_down+solvent_vol_up,2)))

        return True

    def prepare(self):
        """Prepare the membrane system by loading parameters and building the PACKMOL input.

        Orchestrates all preparation steps: parameter loading, argument validation,
        tool detection, composition parsing, protein orientation, geometry
        calculation, and PACKMOL input script generation.

        Returns:
            bool: True if the input script was built successfully, False if
                the system has no membrane and no solvent to pack.
        """
        pdbtar = self._load_parameters()
        self._validate_arguments()
        self._detect_tools()
        composition, apl_offset, lipnum_set = self._parse_composition()
        self._validate_lipid_parameters(composition, pdbtar)
        content_header = self._build_packmol_header()
        geom = self._process_proteins_and_geometry(composition, apl_offset, pdbtar)
        if geom is False:
            return False
        return self._build_packmol_input(composition, apl_offset, lipnum_set,
                                         content_header, geom, pdbtar)

    ############## SET OF USED FUNCTIONS  #####################
    def ppm3_align(self,pdb,keepligs=False,double_span=False,verbose=False,overwrite=False,barrel=False,n_ter="in"):
        """Orient a protein in a membrane using PPM3.

        Args:
            pdb: Path to the input PDB file.
            keepligs: If True, retain HETATM ligand records in output.
            double_span: If True, use double membrane-spanning mode.
            verbose: If True, enable verbose logging.
            overwrite: If True, re-run even if output already exists.
            barrel: If True, use beta-barrel orientation mode.
            n_ter: N-terminus orientation relative to membrane ('in' or 'out').

        Returns:
            tuple: (output_pdb_path, tmp_folder_path).
        """
        output = pdb[:-4]+n_ter+"_PPM3.pdb"
        tmp_folder = "_tmp_"+pdb[:-4]+n_ter+"_PPM3"
        if not os.path.exists(output) or overwrite:
            if not os.path.exists(tmp_folder):
                os.mkdir(tmp_folder)
            os.chdir(tmp_folder)
            os.symlink("../"+pdb,"ppm3tmp.pdb")
            handle = open("ppm.inp", "w")
            ppm3_inp  = "2\n"
            ppm3_inp += ("yes" if keepligs else "no") + "\n"
            ppm3_inp += "ppm3tmp.pdb\n"
            ppm3_inp += "1\n" # Number of bilayers
            ppm3_inp += "    \n"
            ppm3_inp += "planar\n"
            ppm3_inp += f"{n_ter}\n"
            ppm3_inp += ",".join(list(set([l[21] for l in open(f"../{pdb}","r").readlines() if l.startswith("ATOM")])))+"\n"
            handle.write(ppm3_inp)
            handle.close()
            shutil.copy(os.path.join(script_path, "lib", "ppm3", "res.lib"), "./")
            subprocess.run(self.ppm3+" < ppm.inp > "+output.replace("_PPM3.pdb","_PPM3.log"), shell=True)
            outlines = open("ppm3tmpout.pdb", "r").readlines()
            with open("ppm3tmpout_noDUM.pdb", "w") as f:
                for line in outlines:
                    if line.startswith("HETATM") and "DUM x" in line:
                        continue
                    if not keepligs and line.startswith("HETATM"):
                        continue
                    f.write(line)
            shutil.move("ppm3tmpout_noDUM.pdb","../"+output)
            os.chdir("..")
        return output, tmp_folder

    def memembed_align(self,pdb,keepligs=False,double_span=False,verbose=False,overwrite=False,barrel=False,n_ter="in",opt="3"):
        """Orient a protein in a membrane using MEMEMBED.

        Args:
            pdb: Path to the input PDB file.
            keepligs: If True, superimpose original PDB to retain ligands.
            double_span: If True, use double membrane-spanning mode.
            verbose: If True, enable verbose logging.
            overwrite: If True, re-run even if output already exists.
            barrel: If True, use beta-barrel orientation mode (-b flag).
            n_ter: N-terminus orientation relative to membrane ('in' or 'out').
            opt: MEMEMBED optimization level (default '3').

        Returns:
            str: Path to the oriented output PDB file.
        """
        output = f"{pdb[:-4]}{n_ter}_EMBED.pdb"
        if not os.path.exists(output) or overwrite:
            if not barrel:
                subprocess.run(f"{self.memembed} -s {opt} -n {n_ter} -o {output} {pdb} > {output.replace('_EMBED.pdb','_memembed.log')}", shell=True)
            else:
                subprocess.run(f"{self.memembed} -s {opt} -b -n {n_ter} -o {output} {pdb} > {output.replace('_EMBED.pdb','_memembed.log')}", shell=True)
        if keepligs:
            if verbose:
                logger.info("Superimposing to keep ligands")
            rmsd_of_pdbs(pdb,output,transform_pdb1=output.replace("_EMBED.pdb","_EMBED_ligs.pdb"), standard=True)
            output = output.replace("_EMBED.pdb","_EMBED_ligs.pdb")
            return output
        if double_span:
            outpdb = pdb_parse(output, onlybb=False)
            low_bound = np.mean([outpdb[res][atom] for res in outpdb.keys() if res[0] == "DUM" for atom in outpdb[res] if atom[0] == "N" ], axis=0)
            up_bound  = np.mean([outpdb[res][atom] for res in outpdb.keys() if res[0] == "DUM" for atom in outpdb[res] if atom[0] == "O" ], axis=0)
            offset = 0
            mem1_cen  = np.mean([low_bound, up_bound], axis=0)
            tmless                  = {res:outpdb[res] for res in outpdb.keys() if not any([outpdb[res][atom][2] >= low_bound[2]-offset and outpdb[res][atom][2] <= up_bound[2]+offset for atom in outpdb[res]])}
            tmless[('MEM', 1, 'X')] = {('MEM', 1): mem1_cen}
            pdb_write(tmless, outfile="temp1.pdb")
            if not barrel:
                subprocess.run(f"{self.memembed} -s {opt} -n {n_ter} -o temp2.pdb temp1.pdb > double_span.log", shell=True)
            else:
                subprocess.run(f"{self.memembed} -s {opt} -b -n {n_ter} -o temp2.pdb temp1.pdb > double_span.log", shell=True)

            temppdb = pdb_parse("temp2.pdb", onlybb=False)
            low_bound = np.mean([temppdb[res][atom] for res in temppdb.keys() if res[0] == "DUM" for atom in temppdb[res] if atom[0] == "N" ], axis=0)
            up_bound  = np.mean([temppdb[res][atom] for res in temppdb.keys() if res[0] == "DUM" for atom in temppdb[res] if atom[0] == "O" ], axis=0)
            offset = 5
            mem2_cen  = np.mean([low_bound, up_bound], axis=0)
            dumless                  = {res:temppdb[res] for res in temppdb.keys() if res[0] != "DUM"}
            dumless[('MEM', 2, 'X')] = {('MEM', 2): mem2_cen}
            z_dist = dumless[('MEM', 1, 'X')][('MEM', 1)][2]+dumless[('MEM', 2, 'X')][('MEM', 2)][2]
            if z_dist < 0:
                dumless = translate_pdb(dumless,vec=[0,0,z_dist])
                z_dist *= -1

            pdb_write(dumless,outfile="presuper.pdb")

            translated = superimpose_pdb(dumless,outpdb)
            pdb_write(translated, outfile=output.replace("EMBED","EMBED_double"))
            return (output.replace("EMBED","EMBED_double"), z_dist)

        return output

    def pymemembed_align(self,pdb,keepligs=False,double_span=False,verbose=False,overwrite=False,barrel=False,n_ter="in",opt="3"):
        """Orient a protein in a membrane using pymemembed (Python/Numba).

        Drop-in replacement for memembed_align() that uses the pure Python
        implementation instead of the C++ binary. Same interface and output
        format.

        Args:
            pdb: Path to the input PDB file.
            keepligs: If True, superimpose original PDB to retain ligands.
            double_span: If True, use double membrane-spanning mode.
            verbose: If True, enable verbose logging.
            overwrite: If True, re-run even if output already exists.
            barrel: If True, use beta-barrel orientation mode.
            n_ter: N-terminus orientation relative to membrane ('in' or 'out').
            opt: Optimization option (0=GA, 1=Grid, 2=Direct, 3=GA x5).

        Returns:
            str or tuple: Path to the oriented output PDB file,
                or (output_path, z_dist) if double_span.
        """
        try:
            from packmol_memgen.lib.pymemembed.memembed_wrapper import memembed_align_replacement
        except ImportError:
            from lib.pymemembed.memembed_wrapper import memembed_align_replacement
        return memembed_align_replacement(self,pdb,keepligs=keepligs,double_span=double_span,verbose=verbose,overwrite=overwrite,barrel=barrel,n_ter=n_ter,opt=opt)

    def pdbvol(self,pdb,spacing=0.5,overwrite=False):
        """Calculate the volume of a protein using grid-based estimation.

        Places a grid with the given spacing around the protein atoms and
        counts occupied cells to estimate the molecular volume.

        Args:
            pdb: Path to the input PDB file.
            spacing: Grid spacing in Angstroms (default 0.5).
            overwrite: If True, recalculate even if grid PDB exists.

        Returns:
            tuple: (grid_pdb_path, volume_in_cubic_angstroms).
        """
        output = pdb[:-4]+".grid.pdb"
        if os.path.exists(output) and not overwrite:
            filelength = len(open(output,"r").readlines())
            vol        = filelength*spacing**3
            return (output, vol)
        else:
            filelines = open(pdb,"r").readlines()
            temp_pdb = []
            for line in filelines:
                if (line[0:4] == "ATOM" or line[0:6] == "HETATM") and  line[17:20].strip() != "DUM":
                    temp_pdb.append(line)
            temp = open("temp.pdb","w").writelines(temp_pdb)
            atoms = pdbatoms.read_pdb("temp.pdb")
            pdbatoms.add_radii(atoms)
            vol = volume(atoms, spacing, output, verbose=False)
            os.remove("temp.pdb")
            return (output, vol)

    def run_packmol(self):
        """Write the PACKMOL input script and execute PACKMOL.

        Writes self.contents to the .inp file, launches PACKMOL as a subprocess,
        monitors progress via a progress bar, and optionally generates GENCAN
        optimization plots.
        """
        with open(self.packlog+".inp","w+") as script:
    
            script.write(self.contents)
            script.seek(0, os.SEEK_SET)
    
            logger.debug(f"Script for packmol written to {self.packlog}.inp")
    
            if self.packmol is not None and os.path.exists(self.packmol) and self.run:

                logger.info("\nRunning Packmol...")
                log = open(self.packlog+".log","w")
                p = subprocess.Popen(self.packmol, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=script)
                self._pid = p.pid
                def kill_child():
                    if self._pid is None:
                        pass
                    else:
                        try:
                            os.kill(self._pid, signal.SIGTERM)
                        except OSError:
                            pass
                atexit.register(kill_child)
                GENCAN_track = 0
                TOTGENCAN    = 0
                FRAME        = 0
                energy_values = []
                starting = True
                all_together = False
                progress_bar = True
                step = 1
                while True:
                    output = p.stdout.readline().decode('utf-8')
                    log.write(output)
                    if output == '' and p.poll() is not None:
                        break
                    if "Number of independent structures:" in output.strip():
                        structs = output.strip().split()[-1]
                        if not self.packall:
                            if not self.onlymembrane:
                                TOTAL = int(self.nloop)*(int(structs)-1)+self.nloop_all
                            else:
                                TOTAL = int(self.nloop)*(int(structs))+self.nloop_all
                        else:
                            TOTAL = int(self.nloop_all)
                        mag   = int(math.log10(TOTAL))+2
                        if not self.noprogress:
                            p_bar = tqdm.tqdm(total=TOTAL)

                    if "Starting GENCAN loop"  in output.strip():
                        if GENCAN_track < self.nloop+1:
                            GENCAN_track += 1; TOTGENCAN += 1
                        if self.noprogress:
                            if GENCAN_track % 10 == 0:
                                sys.stdout.write(".")
                                sys.stdout.flush()
                        if not self.noprogress and GENCAN_track <= self.nloop:
                            p_bar.update(1)
                    if "Packing molecules " in output.strip():
                        if self.noprogress:
#                            sys.stdout.write("\033[F")
                            sys.stdout.write("\r" +"\nProcessing segment "+output.strip().split()[-1]+" of "+structs)
                            sys.stdout.flush()
                        else:
                            if int(self.nloop)-GENCAN_track > 0 and not starting:
                                p_bar.update(int(self.nloop)-GENCAN_track)
                            else:
                                starting = False
                            p_bar.set_description(f"Molecule segment {output.strip().split()[-1]}/{structs}")
                        GENCAN_track = 0
                    if ("Current solution written to file" in output.strip() or "Writing current (perhaps bad) structure to file" in output.strip()) and self.traj:
                        FRAME += 1
                        shutil.move(self.outfile, self.outfile.replace(".pdb", f"_{FRAME:0{mag}d}.pdb"))
                    if "Packing all molecules together" in output.strip():
                        all_together = True
                        if not self.noprogress:
                            if int(self.nloop)-GENCAN_track > 0 and not self.packall:
                                p_bar.update(int(self.nloop)-GENCAN_track)
                            p_bar.set_description("All-together Packing")
                        logger.debug("\nIndividual packing processes complete. Initiating all-together packing. This might take a while!")
                        sys.stdout.write("\033[F")
                        sys.stdout.write("\r" +"\nAll-together Packing")
                        sys.stdout.flush()
                        GENCAN_track = 0
                        self.nloop = self.nloop_all
                    if "All-type function" in output.strip():
                        fnx_value = float(output.strip().split()[-1])
                        energy_values.append((TOTGENCAN,fnx_value))
                    if "Function value from last GENCAN" in output.strip() and all_together:
                        fnx_value = float(output.strip().split()[-1])
                        energy_values.append((TOTGENCAN,fnx_value))
                    if "Success!" in output.strip():
                        if not self.noprogress:
                            p_bar.update(int(self.nloop)-GENCAN_track)

            if self.run and self.plot:
                try:
                    import matplotlib
                    matplotlib.use('Agg')
                    import matplotlib.pyplot as plt
                    matplotlib.rcParams["font.sans-serif"]='Arial'
                    plt.plot(*list(zip(*energy_values)),color="black")
                    plt.xlabel('Iteration')
                    plt.ylabel('Objective function')
                    plt.savefig(self.outfile+'.png')
                except ImportError:
                    logger.error("ERROR:\n    Matplotlib could not be imported. Check that you have a working version.")
                with open("GENCAN.log","w") as gencanlog:
                    gencanlog.write("\n".join("%s %s" % x for x in energy_values))
    
            elif not os.path.exists(self.packmol) or not self.run:
                logger.info("The script generated can be run by using a packmol executable ($PACKMOL_PATH < memgen.inp)")
                if self.sirah:
                    logger.info("An artificial 'COM WT4' atom was added to avoid clashes. Make sure to delete it post packing and before parametrizing with 'grep -v \"COM WT4\"'")
                sys.exit(1)
    
            if not os.path.exists(self.outfile):
                logger.critical("CRITICAL:\n  No output file generated by PACKMOL. Check packmol.log and if the initial set of constraints are adequate for your system (e.g. leaflet size, tail and head planes)!")
                sys.exit(1)
    
            if self.sirah:
                fixwt4 = []
                with open(self.outfile, "r") as f:
                    for line in f:
                        if "COM WT4" in line:
                            continue
                        fixwt4.append(line)
                with open(self.outfile, "w") as f:
                    f.writelines(fixwt4)

    def postprocess(self):
        """Post-process the packed system: optionally convert to CHARMM, parametrize, and minimize.

        Removes piercing lipid tails from sterol/ring systems and optionally
        runs LEaP parametrization, hydrogen mass repartitioning, and energy
        minimization. If --charmm is set, converts the AMBER output to CHARMM
        format using amberlipid2charmm.
        """
        if self.charmm:
            logger.info("Transforming to CHARMM")
            amberlipid2charmm(self.outfile, self.outfile, os.path.join(script_path, "lib", "charmmlipid2amber", "charmmlipid2amber.csv"))

        if self.sterols_PI_used:
            logger.info("Sterols and/or PI residues were packed. Potential piercing lipid tails will be searched")
            try:
                to_remove = find_piercing_lipids(self.outfile, verbose=True)
                try:
                    if len(to_remove) > 0:
                       self.outfile = remove_piercing_lipids(self.outfile, to_remove, outfile=self.outfile.replace(".pdb","_noclash.pdb"), verbose=True)
                except Exception:
                    logger.warning("Lipid piercing removal failed. Check your structure manually in case of clashing lipid tails!")
            except Exception:
                logger.warning("Lipid piercing finder failed. Check your structure manually in case of clashing lipid tails!")

        if not self.charmm:
            if self.parametrize or self.onlyleapin:
                if self.sirah:
                    logger.info("Parametrizing using LEaP with SIRAH")
                else:
                    logger.info(f"Parametrizing using LEaP with {self.fflip}, {self.ffprot} and {self.ffwat}")
                infiles = prepare_leap(
                            self.outfile,
                            ligands=self.ligand_param,
                            cation=self.ion_dict[self.salt_c][2],
                            anion=self.ion_dict[self.salt_a][2],
                            sirah=self.sirah,
                            suffix="_wat" if self.solvate else "_lipid",
                            custom_lines=self.leapline,
                            gaff2=self.gaff2, 
                            nocounter=self.nocounter, 
                            ffprot=self.ffprot, 
                            ffwat=self.ffwat,
                            fflip=self.fflip, 
                            extended=self.extended,
                            x_solvent=(self.solvents != "WAT"),
                            dim_vec=[self.X_len,self.Y_len,sum([zdim[2] for zdim in self.Z_dim])] if self.tight_box else None, 
                            cli=any(["CL" in lipid for lipid in self.lipids]),
                            onlyleapin=self.onlyleapin)
                if self.onlyleapin:
                    logger.info("Leap script created. Run it with tleap -f leap.in after modyfing it.")
                    sys.exit(1)
    
                if os.stat(infiles[1]).st_size == 0:
                    self.minimize = False
                    logger.error("ERROR:\n    Parametrization Failed! Check that all the components parameters are included (leap_.log file for details)")
                    sys.exit(1)
                self.created.extend(("leap.log","leap_ .log","leap.in"))
                if self.HMR:
                    HMassRepartition(infiles[1])
            if self.minimize:
                logger.info("Minimizing...")
                logger.info(f"Minimizing using {self.engine}")
                if self.pdb is not None and self.pdb.count("None") != len(self.pdb):
                    prot_residues = sum([len(pdb_parse(pdb)) for pdb in self.pdb if pdb is not None])
                    minimized_restraint = amber_minimize(infiles, f"(:1-{prot_residues} | @P31)", sd_steps = self.sd_steps, cg_steps = self.cg_steps, engine=self.engine)
                else:
                    minimized_restraint = amber_minimize(infiles, sd_steps = self.sd_steps, cg_steps = self.cg_steps, engine=self.engine)
                if os.stat(minimized_restraint[0]).st_size == 0:
                    self.minimize = False
                    logger.error("ERROR:\n    Restrained minimization Failed! (log files for details)")
                    sys.exit(1)
                minimized = amber_minimize(minimized_restraint, sd_steps = self.sd_steps, cg_steps = self.cg_steps, min_script=self.outfile.replace(".pdb","_min.in"),engine=self.engine,outfile=self.outfile.replace(".pdb","_min.pdb"))
                if os.stat(minimized[0]).st_size == 0:
                    self.minimize = False
                    logger.error("ERROR:\n    Minimization Failed! (log files for details)")
                    sys.exit(1)

    def cleanup(self):
        """Remove temporary files and print completion message."""
        if self.delete:
            logger.debug("Deleting temporary files...")
            for file in self.created:
                try:
                    if os.path.isfile(file):
                        os.remove(file)
                    elif os.path.isdir(file):
                        shutil.rmtree(file)
                except OSError:
                    pass
            if self.run:
                for file in self.created_notrun:
                    try:
                        os.remove(file)
                    except OSError:
                        pass
    
        warn = "#Packing process finished. Check your final structure, particularly for lipids inserted in proteins, protein tunnels or piercing rings!#"
        print("\n"+"#"*len(warn))
        logger.info(warn)
        print("#"*len(warn))
        print("DONE!")

    def run_all(self):
        """Execute the complete workflow: prepare, pack, postprocess, and cleanup."""
        pack = self.prepare()
        if pack:
            self.run_packmol()
        self.postprocess()
        self.cleanup()

    def lipids_df(self):
        """Return lipid parameters as a pandas DataFrame.

        Returns:
            pandas.DataFrame: Lipid parameters indexed by lipid name,
                or None if prepare() has not been called.
        """
        try:
            return pd.DataFrame.from_dict(self.parameters).T
        except AttributeError:
            print("Run prepare() to populate the lipid parameters")

    def solvents_df(self):
        """Return solvent parameters as a pandas DataFrame.

        Returns:
            pandas.DataFrame: Solvent parameters indexed by solvent name,
                or None if prepare() has not been called.
        """
        try:
            return pd.DataFrame.from_dict(self.sparameters).T
        except AttributeError:
            print("Run prepare() to populate the solvent parameters")

    def ions_df(self):
        """Return the AMBER ion dictionary as a pandas DataFrame.

        Returns:
            pandas.DataFrame: Ion properties (PDB name, charge, LEaP name)
                indexed by ion identifier.
        """
        return pd.DataFrame.from_dict(amber_ion_dict).T

if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)

    streamer = logging.StreamHandler()
    streamer.setLevel(logging.INFO)

    logger.addHandler(streamer)

    args = parser.parse_args()

    if args.json:
        if not os.path.isfile(args.json):
            print(f"ERROR: JSON config file not found: {args.json}", file=sys.stderr)
            sys.exit(1)
        with open(args.json) as _jf:
            _config = json.load(_jf)
        args = parser.parse_args([])
        for _k, _v in _config.items():
            if hasattr(args, _k) and _k != 'json':
                setattr(args, _k, _v)

    if not (args.available_lipids or args.available_lipids_all or
            args.available_solvents or args.available_ions):
        # pdb2pqr reflects actual usage: True when used, False when protonation is disabled or reduce is chosen
        args.pdb2pqr = not args.notprotonate and not args.reduce and not args.reducebuild
        _json_out = os.path.splitext(args.log)[0] + ".json"
        _config_dict = {k: v for k, v in vars(args).items() if k != 'json'}
        with open(_json_out, 'w') as _jf:
            json.dump(_config_dict, _jf, indent=2)
        logger.debug(f"Configuration saved to {_json_out}")

    pmg = PACKMOLMemgen(args)
    pack = pmg.prepare()
    if pack:
        pmg.run_packmol()
    pmg.postprocess()
    pmg.cleanup()


# Web interface integration
__all__ = ['PACKMOLMemgen', 'build_parser', 'create_memgen_from_dict']


def create_memgen_from_dict(config: dict) -> 'PACKMOLMemgen':
    """Create PACKMOLMemgen instance from a configuration dictionary.

    This function allows programmatic configuration without using argparse,
    enabling web interfaces and other tools to create membrane systems.

    Args:
        config: Dictionary with configuration keys matching argparse arguments.
                Example: {'pdb': ['protein.pdb'], 'lipids': ['DOPC'],
                         'ratio': ['1'], 'output': 'system.pdb'}

    Returns:
        Configured PACKMOLMemgen instance ready for prepare()/run_packmol().

    Example:
        >>> config = {
        ...     'pdb': ['protein.pdb'],
        ...     'lipids': ['DOPC:DOPG'],
        ...     'ratio': ['3:1'],
        ...     'output': 'bilayer.pdb',
        ...     'salt': True,
        ... }
        >>> pmg = create_memgen_from_dict(config)
        >>> pmg.prepare()
        >>> pmg.run_packmol()
    """
    # Create namespace with defaults from parser
    args = build_parser().parse_args([])

    # Override with provided config
    for key, value in config.items():
        if hasattr(args, key):
            setattr(args, key, value)

    return PACKMOLMemgen(args)
