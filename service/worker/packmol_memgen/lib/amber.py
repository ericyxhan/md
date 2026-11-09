#! /usr/bin/python
"""AMBER molecular dynamics toolchain interface for PACKMOL-Memgen.

Provides functions for interacting with AMBER tools including reduce (protonation),
tleap (force field parametrization), pmemd/sander (minimization), and SIRAH
coarse-grained conversion. Also defines the supported ion dictionary used for
system neutralization and salt addition.
"""

import logging
import os
import subprocess
import sys

import numpy as np

from .utils import pdb_parse
module_path = os.path.abspath(os.path.dirname(__file__))+os.path.sep

logger = logging.getLogger("pmmg_log")

if os.name == 'nt':
    exe_suffix =    ".exe"
    script_suffix = ".bat"
else:
    exe_suffix =    ""
    script_suffix = ""

parmed = False
try:
    amberhome = os.environ['AMBERHOME']
    amberhome_bin = os.path.join(amberhome, "bin")

    reduce     = os.path.join(amberhome_bin, "reduce" + exe_suffix)
    leap       = os.path.join(amberhome_bin, "tleap"  + script_suffix)
    sander     = os.path.join(amberhome_bin, "sander" + exe_suffix)
    pmemd      = os.path.join(amberhome_bin, "pmemd"  + exe_suffix)
    pmemd_cuda = os.path.join(amberhome_bin, "pmemd.cuda"  + exe_suffix)
    ambpdb     = os.path.join(amberhome_bin, "ambpdb" + exe_suffix)
    cgconv     = os.path.join(amberhome, "dat/SIRAH/tools/CGCONV/cgconv.pl")
    if not os.path.exists(pmemd):
        logger.debug("PMEMD not found. Setting path to SANDER")
        pmemd = sander
        pmemd_cuda = sander
    elif not os.path.exists(pmemd_cuda):
        logger.debug("PMEMD.CUDA not found. Setting path to PMEMD")
        pmemd_cuda = pmemd
    for exec_path in [reduce,leap,sander,ambpdb]:
        if not os.path.exists(exec_path):
            logger.debug(f"AMBER path found, but {exec_path} executable is not available")
    try:
        import parmed as pmd
        parmed = True
    except ImportError:
        logger.warning("Parmed could not be loaded. Some functions will be disabled")
except KeyError:
    logger.critical("AMBER environment variables not found!")

# Mapping of ion names to their AMBER parameters.
# Each entry is: "IonSymbol" : (pdb_name, charge, leap_name)
#   - pdb_name:  Atom/residue name used in PDB files
#   - charge:    Formal ionic charge (positive for cations, negative for anions)
#   - leap_name: Residue name used in LEaP commands
amber_ion_dict = {
"NH4+" :( "NH4" ,  1,"NH4" ),
"H3O+" :( "H3O+",  1,"H3O+"),
"Li+"  :(  "LI" ,  1, "LI" ),#   3
"Be2+" :(  "Be" ,  2, "Be" ),#   4
"F-"   :(  "F"  , -1, "F"  ),#   9
"Na+"  :(  "Na+",  1, "Na+"),#   11
"Mg2+" :(  "MG" ,  2, "MG" ),#   12
"Al3+" :(  "AL" ,  3, "AL" ),#   13
"Cl-"  :(  "Cl-", -1, "Cl-"),#   17
"K+"   :(  "K+" ,  1, "K+" ),#   19
"Ca2+" :(  "CA" ,  2, "CA" ),#   20
"V2+"  :(  "V2+",  2, "V2+"),#   23
"Cr2+" :(  "Cr" ,  2, "Cr" ),#   24
"Cr3+" :(  "CR" ,  3, "CR" ),#   24
"Mn2+" :(  "MN" ,  2, "MN" ),#   25
"Fe2+" :(  "FE2",  2, "FE2"),#   26
"Fe3+" :(  "FE" ,  3, "FE" ),#   26
"Co2+" :(  "CO" ,  2, "CO" ),#   27
"Ni2+" :(  "NI" ,  2, "NI" ),#   28
"Cu+"  :(  "CU1",  1, "CU1"),#   29
"Cu2+" :(  "CU" ,  2, "CU" ),#   29
"Zn2+" :(  "ZN" ,  2, "ZN" ),#   30
"Br-"  :(  "BR" , -1, "BR" ),#   35
"Rb+"  :(  "RB" ,  1, "RB" ),#   37
"Sr2+" :(  "SR" ,  2, "SR" ),#   38
"Y3+"  :(  "Y"  ,  3, "Y"  ),#   39
"Zr4+" :(  "Zr" ,  4, "Zr" ),#   40
"Pd2+" :(  "PD" ,  2, "PD" ),#   46
"Ag+"  :(  "AG" ,  1, "AG" ),#   47
"Ag2+" :(  "Ag" ,  2, "Ag" ),#   47
"Cd2+" :(  "CD" ,  2, "CD" ),#   48
"In3+" :(  "IN" ,  3, "IN" ),#   49
"Sn2+" :(  "Sn" ,  2, "Sn" ),#   50
"I-"   :(  "IOD", -1, "IOD"),#   53
"Cs+"  :(  "CS" ,  1, "CS" ),#   55
"Ba2+" :(  "BA" ,  2, "BA" ),#   56
"La3+" :(  "LA" ,  3, "LA" ),#   57
"Ce3+" :(  "CE" ,  3, "CE" ),#   58
"Ce4+" :(  "Ce" ,  4, "Ce" ),#   58
"Pr3+" :(  "PR" ,  3, "PR" ),#   59
"Nd3+" :(  "Nd" ,  3, "Nd" ),#   60
"Sm2+" :(  "Sm" ,  2, "Sm" ),#   62
"Sm3+" :(  "SM" ,  3, "SM" ),#   62
"Eu3+" :(  "EU3",  3, "EU3"),#   63
"Eu2+" :(  "EU" ,  2, "EU" ),#   63
"Gd3+" :(  "GD3",  3, "GD3"),#   64
"Tb3+" :(  "TB" ,  3, "TB" ),#   65
"Dy3+" :(  "Dy" ,  3, "Dy" ),#   66
"Er3+" :(  "Er" ,  3, "Er" ),#   68
"Tm3+" :(  "Tm" ,  3, "Tm" ),#   69
"Yb2+" :(  "YB2",  2, "YB2"),#   70
"Lu3+" :(  "LU" ,  3, "LU" ),#   71
"Hf4+" :(  "Hf" ,  4, "Hf" ),#   72
"Pt2+" :(  "PT" ,  2, "PT" ),#   78
"Hg2+" :(  "HG" ,  2, "HG" ),#   80
"Tl+"  :(  "TL" ,  1, "TL" ),#   81
"Tl3+" :(  "Tl" ,  3, "Tl" ),#   81
"Pb2+" :(  "PB" ,  2, "PB" ),#   82
"Ra2+" :(  "Ra" ,  2, "Ra" ),#   88
"Th4+" :(  "Th" ,  4, "Th" ),#   90
"U4+"  :(  "U4+",  4, "U4+"),#   92
"Pu4+" :(  "Pu" ,  4, "Pu" )#   94
}

def HMassRepartition(parmpath, outpath=None):
    """Apply hydrogen mass repartitioning to an AMBER topology file.

    Redistributes mass from heavy atoms to bonded hydrogens, enabling
    larger simulation time steps (up to 4 fs). Requires ParmEd.

    Args:
        parmpath: Path to the AMBER topology (.top/.prmtop) file.
        outpath: Path for the output topology. If None, the original file
            is renamed with a '.ori' suffix and overwritten in place.

    Returns:
        None if ParmEd is not available.
    """
    if not os.path.exists(parmpath):
        logger.error(f"ERROR:\n The topology {parmpath} was not found")
        sys.exit(1)
    if outpath is None:
        logger.info(f"Renaming the original topology without HMR to {parmpath}.ori")
        outpath = parmpath
        parmpath = parmpath+".ori"
        os.replace(outpath,parmpath)
    if parmed:
        parm = pmd.amber.AmberParm(parmpath)
        logger.info("Applying hydrogen mass repartitioning with Parmed")
        HMR = pmd.tools.actions.HMassRepartition(parm)
        HMR.execute()
        pmd.tools.parmout(parm, outpath).execute()
    else:
        logger.warning("Parmed is not available! No hydrogen mass repartitioning will be performed")
        return None

def reduce_protonate(pdb,overwrite=False, build=False):
    """Add hydrogen atoms to a PDB file using AMBER's reduce tool.

    Args:
        pdb: Path to the input PDB file.
        overwrite: If True, regenerate output even if it already exists.
        build: If True, use reduce's -BUILD mode to add and optimize
            all hydrogens. Otherwise, only add hydrogens without optimization.

    Returns:
        Path to the protonated PDB file (suffix '_H.pdb'), or 'error'
        if the output file is empty.
    """
    output = f"{pdb[:-4]}_H.pdb"
    if os.path.exists(output) and not overwrite:
        return output
    log_path = os.path.join(os.path.dirname(os.path.abspath(output)), "reduce_warn.log")
    if build:
        subprocess.run(f"{reduce} -Quiet -BUILD {pdb} > {output} 2>> {log_path}", shell=True)
    else:
        subprocess.run(f"{reduce} -Quiet {pdb} > {output} 2>> {log_path}", shell=True)
    if os.stat(output).st_size == 0:
        return "error"
    return output

def reduce_trim(pdb,overwrite=False):
    """Remove hydrogen atoms from a PDB file using AMBER's reduce tool.

    Args:
        pdb: Path to the input PDB file.
        overwrite: If True, regenerate output even if it already exists.

    Returns:
        Path to the trimmed PDB file (suffix '_Trim.pdb'), or 'error'
        if the output file is empty.
    """
    output = f"{pdb[:-4]}_Trim.pdb"
    if os.path.exists(output) and not overwrite:
        return output
    log_path = os.path.join(os.path.dirname(os.path.abspath(output)), "reduce_Trim_warn.log")
    subprocess.run(f"{reduce} -Trim {pdb} > {output} 2>> {log_path}", shell=True)
    if os.stat(output).st_size == 0:
        return "error"
    return output

def sirah_cgconv(pdb,overwrite=False):
    """Convert an atomistic PDB to SIRAH coarse-grained representation.

    Uses the SIRAH CGCONV tool from the AMBER distribution to map
    all-atom coordinates to coarse-grained beads.

    Args:
        pdb: Path to the input all-atom PDB file.
        overwrite: If True, regenerate output even if it already exists.

    Returns:
        Path to the coarse-grained PDB file (suffix '_cg.pdb'), or
        'error' if the output file is empty.
    """
    output = f"{pdb[:-4]}_cg.pdb"
    if os.path.exists(output) and not overwrite:
        return output
    subprocess.run(f"{cgconv} -i {pdb} -o {output} 2>> cgconv.log", shell=True)
    if os.stat(output).st_size == 0:
        return "error"
    return output


def amber_minimize(infiles,restraintmask=None, sd_steps = 5000, cg_steps = 5000,output="protein",min_script="min.in",outfile="minimized.pdb", engine="pmemd"):
    """Run energy minimization on an AMBER system using steepest descent and conjugate gradient.

    Generates a minimization input script and executes it with the specified
    MD engine (pmemd, pmemd.cuda, or sander). Optionally applies positional
    restraints to selected atoms.

    Args:
        infiles: Tuple of (pdb_path, topology_path, coordinate_path) for
            the AMBER system files.
        restraintmask: AMBER-format atom selection mask for positional
            restraints (e.g., ':PROT | @P31'). None disables restraints.
        sd_steps: Number of steepest descent minimization steps.
        cg_steps: Number of conjugate gradient minimization steps.
        output: Base name for output files (unused, kept for compatibility).
        min_script: Filename for the generated minimization input script.
        outfile: Filename for the minimized PDB output.
        engine: Minimization engine to use. One of 'pmemd', 'pmemd.cuda',
            or 'sander'.

    Returns:
        Tuple of (minimized_pdb_path, topology_path, restart_coordinate_path).
    """
    total = sd_steps+cg_steps
    script = "Memgen AMBER minimization\n"
    script += " &cntrl\n"
    script += "  nmropt = 0,\n"
    script += "  imin = 1,\n"
    if restraintmask is not None:
        script += "  ntr = 1,\n"
        script += "  restraint_wt = 10,\n"
        script += f"  restraintmask = '{restraintmask}',\n" #(:PROT | @P31)
    script += f"  maxcyc = {total},\n"
    script += f"  ncyc = {sd_steps},\n"
    script += " &end\n"
    handle = open(min_script,"w")
    handle.write(script)
    handle.close()
    min_out = min_script.replace(".in",".out")
    min_restrt = min_script.replace(".in",".restrt")
    if engine == "pmemd.cuda":
        result = subprocess.run(f"{pmemd_cuda} -O -i {min_script} -o {min_out} -p {infiles[1]} -c {infiles[2]} -r {min_restrt} -ref {infiles[2]}", shell=True)
    elif engine == "pmemd":
        result = subprocess.run(f"{pmemd} -O -i {min_script} -o {min_out} -p {infiles[1]} -c {infiles[2]} -r {min_restrt} -ref {infiles[2]}", shell=True)
    elif engine == "sander":
        result = subprocess.run(f"{sander} -O -i {min_script} -o {min_out} -p {infiles[1]} -c {infiles[2]} -r {min_restrt} -ref {infiles[2]}", shell=True)
    else:
        logger.critical("CRITICAL:\n  MM engine not found!")
    if result.returncode != 0:
        logger.critical(f"CRITICAL:\n  {engine} failed! Check {min_out} and consider using a different minimization engine or repacking your system")
    subprocess.run(f"{ambpdb} -p {infiles[1]} -c {min_restrt} > {outfile}", shell=True)
    return (outfile,infiles[1],min_restrt)


def prepare_leap(pdb,
                dim_vec=None,
                leap_script="leap.in",
                ligands=None,
                cation="K+",
                anion="Cl-",
                suffix="_par",
                custom_lines=None,
                gaff2=False,
                sirah=False,
                extended=False,
                x_solvent=False,
                cli=False,
                nocounter=False,
                ffprot="ff14SB",
                ffwat="tip3p",
                fflip="lipid21",
                onlyleapin=False
                ):
    """Generate and execute an AMBER LEaP script for force field parametrization.

    Builds a tleap input script that loads force fields, assigns parameters,
    sets box dimensions, adds counterions, and saves topology/coordinate files.
    Supports standard AMBER, SIRAH coarse-grained, extended lipid, and
    cardiolipin (CLI) workflows.

    Args:
        pdb: Path to the input PDB file to parametrize.
        dim_vec: Box dimensions as [x, y, z] in Angstroms. If None, uses
            vdW-based automatic box sizing.
        leap_script: Filename for the generated LEaP input script.
        ligands: List of ligand parameter strings in 'frcmod:lib' format.
        cation: Cation species for neutralization (key from amber_ion_dict).
        anion: Anion species for neutralization (key from amber_ion_dict).
        suffix: Suffix appended to output filenames (before extension).
        custom_lines: List of additional LEaP commands to include. Lines
            starting with 'load' or 'source' are placed before PDB loading;
            all others are placed after.
        gaff2: If True, use GAFF2 instead of GAFF for ligand parameters.
        sirah: If True, use SIRAH coarse-grained force field.
        extended: If True, load extended lipid library (cyanobacterial lipids).
        x_solvent: If True, load extra solvent force field parameters.
        cli: If True, enable cardiolipin bonding workflow with pdb4amber
            preprocessing and explicit bond definitions.
        nocounter: If True, skip addition of counterions.
        ffprot: Protein force field name (e.g., 'ff14SB', 'ff19SB').
        ffwat: Water model name (e.g., 'tip3p', 'opc', 'spce').
        fflip: Lipid force field name (e.g., 'lipid21').
        onlyleapin: If True, only write the LEaP input script without
            executing it. No output files are returned.

    Returns:
        Tuple of (parametrized_pdb_path, topology_path, coordinate_path)
        when onlyleapin is False. Returns None when onlyleapin is True.
    """

    if sirah:
        script = f"addPath {amberhome}/dat/SIRAH/\n"
        script += "source leaprc.sirah\n"
    else:
        script = f"source leaprc.{fflip}\n"
        if extended or x_solvent:
            script += f"addPath {module_path}../data/\n"
        if extended:
            script += "source leaprc.lipid_ext\n"
        script += f"source leaprc.protein.{ffprot}\n"
        script += f"source leaprc.water.{ffwat}\n"
        if x_solvent:
            script += "source leaprc.extra_solvents\n"

    if custom_lines is not None:
        for line in [line for line in custom_lines if (line.startswith("load") or line.startswith("source"))]:
            script += f"{line}\n"
    if ligands is not None:
        if gaff2:
            script += "source leaprc.gaff2\n"
        else:
            script += "source leaprc.gaff\n"
        for ligand in ligands:
            params = ligand.split(":")      # AMBER frcmod,lib
            script += f"loadamberparams {params[0]}\n"
            script += f"loadoff {params[1]}\n"
    if cli:
        try:
            logger.debug("Running pdb4amber to clean the output")
            import pdb4amber
            p4alogger = logging.getLogger('pdb4amber_log')
            logging.StreamHandler().setLevel(logging.WARNING)
            pdb4amber.main(["-i",pdb,"-o","cli_clean.pdb","-l","p4a.log"])
            logging.StreamHandler().setLevel(logging.INFO)
        except Exception:
            logger.critical("CRITICAL:\n  pdb4amber failed! Is it available in your PYTHONPATH?")
            sys.exit(1)
        script += "SYS = loadpdb cli_clean.pdb \n"
        cli_leap = script
        cli_leap += "savepdb SYS cli_temp.pdb"
        handle = open("leap_cli.in","w")
        handle.write(cli_leap)
        handle.close()
        subprocess.run(f"{leap} -f leap_cli.in > leap_cli.log 2>&1", shell=True)
        cli_temp = pdb_parse("cli_temp.pdb", onlybb=False)
        for res in cli_temp:
            if res[0] == "CLI":
                script += f"bond SYS.{res[1]}.C11B SYS.{res[1]+2}.C12\n"
                script += f"bond SYS.{res[1]}.C21B SYS.{res[1]+3}.C12\n"
                script += f"deletebond SYS.{res[1]+2}.C12 SYS.{res[1]+3}.C12\n"
    else:
        script += f"SYS = loadpdb {pdb} \n"
    if custom_lines is not None:
        for line in [line for line in custom_lines if not (line.startswith("load") or line.startswith("source"))]:
            script += f"{line}\n"
    if dim_vec is None:
        script += "setBox SYS vdw\n"
    else:
        script += f"set SYS box {{ {dim_vec[0]:6.3f} {dim_vec[1]:6.3f} {dim_vec[2]:6.3f} }}\n"
    if cation == "Ca2+":
        cation = "CA"
    if not nocounter:
        script += f"addionsrand SYS {cation} 0\n"
        script += f"addionsrand SYS {anion} 0\n"
    script += f"savepdb SYS {pdb.replace('.pdb',suffix+'.pdb')}\n"
    script += f"saveAmberParmNetcdf SYS {pdb.replace('.pdb',suffix+'.top')} {pdb.replace('.pdb',suffix+'.crd')}\n"
    script += "quit\n"
    handle = open(leap_script,"w")
    handle.write(script)
    handle.close()
    if not onlyleapin:
        if not os.path.exists(pdb.replace(".pdb",suffix+".top")):
            subprocess.run(f"{leap} -f {leap_script} > leap_.log 2>&1", shell=True)
        else:
            logger.warning(f"Output {pdb.replace('.pdb',suffix+'.top')} found. Skipping Leap")
        if not os.path.exists(pdb.replace(".pdb",suffix+".top")):
            logger.critical("Leap Failed! Check the leap_.log file")
        return (pdb.replace(".pdb",suffix+".pdb"),pdb.replace(".pdb",suffix+".top"),pdb.replace(".pdb",suffix+".crd"))
