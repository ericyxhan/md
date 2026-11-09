#!/usr/bin/python
"""Utility functions for PACKMOL-Memgen membrane system building.

This module provides PDB parsing, coordinate manipulation, geometric
calculations, and membrane parameter analysis for constructing
membrane-protein-lipid bilayer systems. Key functionality includes:

- PDB file I/O and coordinate transformations (rotation, translation)
- Protein volume and charge estimation for membrane embedding
- Lipid piercing detection and removal for sterol/ring lipid clashes
- Box geometry calculation for PACKMOL packing
- CIF to PDB format conversion
"""

import contextlib
import copy
import logging
import math
import os
import random
import string
import sys
import tempfile
import warnings

import numpy as np
from scipy import integrate
import numba
from numba import njit, prange

from .pdbremix import data


logger = logging.getLogger("pmmg_log")
logger.setLevel(logging.WARN)

#Load pdb2pqr functions if available
try:
    import shutil
    pdb2pqr = shutil.which("pdb2pqr30") or shutil.which("pdb2pqr")
    if not pdb2pqr:
        logger.debug("PDB2PQR not found in PATH. Install with: pip install pdb2pqr")
except Exception:
    logger.debug("PDB2PQR not available.")
    pdb2pqr = False

VCH           = 21.65 # A^3
VCH2          = 27.03 # A^3
avogadro = 6.02214086*10**23
residues = {"CYS","CYX","CYM","MET","HIS","HSD","HIE","HID","HIP","HSE","SER","GLN","ASP","ASH","GLU","GLH","TYR","THR","ALA","LEU","ILE","PHE","TRP","ARG","ASN","LYS","LYN","VAL","PRO","GLY"}
cgatoms  = {"CA","CB","C","N","O"}
charged  = {"ASP":-1,"GLU":-1,"LYS":1,"ARG":1,"HIP":1,"Cl-":-1,"MG":2,"Na+":1,"CA":2,"OHE":-0.308100,
            "A":-1,"A5":-0.3081,"A3":-0.6919,"DA":-1,"DA5":-0.3079,"DA3":-0.6921,
            "C":-1,"C5":-0.3081,"C3":-0.6919,"DC":-1,"DC5":-0.3079,"DC3":-0.6921,
            "G":-1,"G5":-0.3081,"G3":-0.6919,"DG":-1,"DG5":-0.3079,"DG3":-0.6921,
            "U":-1,"U5":-0.3081,"U3":-0.6919,"DT":-1,"DT5":-0.3079,"DT3":-0.6921,
            "PTR":-2,"SEP":-2,"TPO":-2,"Y1P":-1,"S1P":-1,"T1P":-1,"H1D": 0,"H2D":-1,"H1E": 0,"H2E":-1,
            "NME":1,"ACE":-1} #These two are actually neutral, but by being added, the opposite terminal end charge is not neutralized. Should work as long as no custom terminal ends or protein constructs are used.

tails = {"LAL","MY","PA","ST","OL","AR","DHA","SA"}

sterols_rings = {"CHL1","ERG","CAM","SIT","STI","PI"}
ring_lipid_endings = {"DG","MG","SQ","GG","SG"}
sterol_ring_probes = [["C1","C2","C3","C4","C5","C10"],["C5","C6","C7","C8","C9","C10"],["C8","C9","C11","C12","C13","C14"],["C13","C14","C15","C16","C17"]]
PI_res        = ["2-A","2-B","2-C","H2A","H2B","H2C","P2A","P2B","P2C","P2D","P2E","P2F","P3-","P3A","P3B","P3C","P3D","P3E","P3F","P3H","PH3","PH4","PH5","PI","PI3","PI4","PI5"]
PI_ring_probe = ["C31","C32","C33","C34","C35","C36"]

GG_res = ["DGG","MGG","SQ","GSG","SGG"]
MGG_ring_probe = ["O3A","C31","C32","C33","C34","C35"]
DGG_ring_probe = ["O4A","C41","C42","C43","C44","C45"]

#masses   = {"C": 12, "S": 32, "O": 16, "H": 1, "N": 14}

def cif_to_pdb(cif_file, output_pdb=None):
    """Convert an mmCIF file to PDB format using the Gemmi library.

    Args:
        cif_file: Path to input CIF/mmCIF file.
        output_pdb: Path for the output PDB file. If None, creates
            ``{basename}_converted.pdb`` alongside the input file.

    Returns:
        Path to the generated PDB file.

    Raises:
        ImportError: If the gemmi library is not installed.
        RuntimeError: If the CIF-to-PDB conversion fails.
    """
    try:
        import gemmi
    except ImportError:
        logger.critical("CRITICAL:\n  Gemmi library required for CIF support.\n"
                       "  Install with: pip install gemmi")
        raise ImportError("Gemmi library not found")

    if output_pdb is None:
        # Create output filename: input.cif -> input_converted.pdb
        base = cif_file.rsplit('.', 1)[0]
        output_pdb = f"{base}_converted.pdb"

    try:
        # Read CIF structure
        structure = gemmi.read_structure(cif_file)

        # Write as PDB format
        structure.write_pdb(output_pdb)

        logger.debug(f"Converted {cif_file} to {output_pdb}")
        return output_pdb

    except Exception as e:
        logger.critical(f"CRITICAL:\n  Failed to convert {cif_file} to PDB format.\n"
                       f"  Error: {e}")
        raise RuntimeError(f"CIF conversion failed: {e}")

def pdb2pqr_protonate(pdb,overwrite=False,ffout='AMBER',pH=7.0):
    """Protonate a PDB file using PDB2PQR.

    Runs PDB2PQR with PROPKA titration to add hydrogens at the specified
    pH and converts output to AMBER-compatible format.

    Args:
        pdb: Path to the input PDB file.
        overwrite: If False, skip protonation when output files already exist.
        ffout: Output force field format (default 'AMBER').
        pH: Target pH for protonation state assignment.

    Returns:
        Path to the protonated PDB file (``{basename}_H.pdb``).
    """
    if not pdb2pqr:
        logger.critical("PDB2PQR module was not found. Use a different method to protonate your system")
        exit()
    output_pqr = pdb[:-4]+"_H.pqr"
    output_pdb = pdb[:-4]+"_H.pdb"
    if os.path.exists(output_pdb) and os.path.exists(output_pqr) and not overwrite:
        return output_pdb
    # Strip DUM atoms (added by membrane orientation tools) before passing to pdb2pqr
    tmp_pdb = None
    input_pdb = pdb
    with open(pdb) as f:
        lines = f.readlines()
    filtered = [l for l in lines if not (len(l) >= 20 and l[17:20].strip() == "DUM")]
    if len(filtered) < len(lines):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.pdb', delete=False)
        tmp.writelines(filtered)
        tmp.close()
        tmp_pdb = tmp.name
        input_pdb = tmp_pdb
    try:
#As pdb2pqr call logging.basicConfig in the main function, it disrupts the logging setup. Calling in os.system to avoid issues
        log_path = os.path.join(os.path.dirname(os.path.abspath(output_pdb)), "pdb2pqr.log")
        args = " ".join([pdb2pqr,'--pdb-output='+output_pdb,'--ff=PARSE','--ffout=AMBER','--titration-state-method=propka','--with-ph='+str(pH),input_pdb,output_pqr,"&>",log_path])
        rtrn_code = os.system(args)
    finally:
        if tmp_pdb and os.path.exists(tmp_pdb):
            os.remove(tmp_pdb)
    if rtrn_code != 0:
        logger.critical("CRITICAL:\n PDB2PQR failed! Check pdb2pqr.log")
        exit()
    return output_pdb

def estimated_density(MW):
    """Estimate protein density from molecular weight.

    Uses the empirical formula from Protein Sci. 2004 Oct; 13(10):2825-2828:
    density = 1.41 + 0.145 * exp(-MW / 13000).

    Args:
        MW: Molecular weight in Daltons.

    Returns:
        Estimated density in g/cm^3.
    """
    density = 1.41 + 0.145*math.exp(float(-MW)/13000)  #Protein Sci. 2004 Oct; 13(10):2825-2828
    return density

def distribute_integer(integer, fracs):
    """Distribute an integer among bins according to fractional weights.

    Performs greedy rounding to ensure the distributed values sum to
    the original integer exactly.

    Args:
        integer: Total integer value to distribute.
        fracs: List of fractional weights for each bin.

    Returns:
        List of integers summing to the original integer, distributed
        proportionally to the given fractions.
    """
    dist = []
    tot = sum(fracs)
    for frac in fracs:
        d = int(round(integer*frac/tot))
        dist.append(d)
        tot -= frac
        integer -= d
    return dist

def rotation_matrix(axis, theta):
    """Compute a 3D rotation matrix for counterclockwise rotation about an axis.

    Uses the Rodrigues rotation formula via quaternion decomposition.

    Args:
        axis: 3-element array-like specifying the rotation axis.
        theta: Rotation angle in radians.

    Returns:
        3x3 numpy array representing the rotation matrix.
    """
    axis = np.asarray(axis)
    axis = axis/math.sqrt(np.dot(axis, axis))
    a = math.cos(theta/2.0)
    b, c, d = -axis*math.sin(theta/2.0)
    aa, bb, cc, dd = a*a, b*b, c*c, d*d
    bc, ad, ac, ab, bd, cd = b*c, a*d, a*c, a*b, b*d, c*d
    return np.array([[aa+bb-cc-dd, 2*(bc+ad), 2*(bd-ac)],
                     [2*(bc-ad), aa+cc-bb-dd, 2*(cd+ab)],
                     [2*(bd+ac), 2*(cd-ab), aa+dd-bb-cc]])

def vector_angle(vec1,vec2, ref=[1,1,0]):
    """Calculate the angle between two 3D vectors.

    Args:
        vec1: First vector as array-like.
        vec2: Second vector as array-like.
        ref: Reference vector for orientation (unused in current implementation).

    Returns:
        Angle between the vectors in radians.
    """
    cross = np.cross(vec1,vec2)
    dot = np.dot(vec1,vec2)
    dot /= np.linalg.norm(vec1)*np.linalg.norm(vec2)
    ori = np.dot(cross, ref)
    return np.arccos(dot)

def align_vectors(vec1,vec2, R=None):
    """Rotate vec1 toward vec2 using a rotation matrix.

    Args:
        vec1: Source vector to rotate.
        vec2: Target direction vector.
        R: Pre-computed rotation matrix. If None, one is computed from
            the cross product axis and angle between vec1 and vec2.

    Returns:
        Rotated vector as a numpy array, or the zero vector if vec1 is zero.
    """
    if np.allclose(vec1,np.array([0,0,0])):
        return np.array([0,0,0])
    angle = vector_angle(vec1,vec2)
    if R is None:
        R = rotation_matrix(cross,angle)
    return np.matmul(vec1,R)

def rotate_pdb(pdb_ori,tip_num,pivot_num, ref=[0,0,1],randomize=False,randomize_vec=[0,0,1]):
    """Rotate a parsed PDB structure so that a tip-to-pivot vector aligns with a reference.

    Optionally applies a random rotation about the Z axis after alignment.

    Args:
        pdb_ori: Parsed PDB dictionary (residue -> atom -> coordinates).
        tip_num: Atom number(s) defining the tip point. Can be int or list
            of ints for averaging.
        pivot_num: Atom number(s) defining the pivot point. Can be int or
            list of ints for averaging.
        ref: Target reference direction vector (default [0,0,1], i.e. +Z).
        randomize: If True, apply an additional random rotation about Z.
        randomize_vec: Axis for the random rotation (default [0,0,1]).

    Returns:
        Deep copy of the PDB dictionary with rotated coordinates.
    """
    pdb = copy.deepcopy(pdb_ori)
    tip = []
    pivot = []
    for res in pdb:
        for atom in pdb[res]:
            if isinstance(tip_num, list):
                if atom[1] in tip_num:
                    tip.append(pdb[res][atom])
            else:
                if atom[1] == tip_num:
                    tip = pdb[res][atom]
            if isinstance(pivot_num,list):
                if atom[1] in pivot_num:
                    pivot.append(pdb[res][atom])
            else:
                if atom[1] == pivot_num:
                    pivot = pdb[res][atom]
    if isinstance(tip_num, list):
        tip = np.mean(tip,axis=0)
    if isinstance(pivot_num,list):
        pivot = np.mean(pivot,axis=0)
    angle = vector_angle(tip-pivot,np.array(ref))
    axis = np.cross(tip-pivot,np.array(ref))   # vector perpendicular to v1 v2 plane
    R = rotation_matrix(axis,angle)
    for res in pdb:
        if randomize:
            angle = random.uniform(0,6.28)
            axis = np.array([0,0,1])
            R = np.matmul(R,rotation_matrix(axis,angle))
        for atom in pdb[res]:
            pdb[res][atom] = align_vectors(pdb[res][atom]-pivot,np.array(ref),R)+pivot
    return pdb

def randomize_pdb(pdb_ori,tip_num,pivot_num, ref=[0,0,1]):
    """Apply a random rotation about a reference axis to a parsed PDB structure.

    The rotation is performed around the pivot point with a uniformly
    random angle between 0 and 2*pi.

    Args:
        pdb_ori: Parsed PDB dictionary (residue -> atom -> coordinates).
        tip_num: Atom number(s) defining the tip point. Can be int or list
            of ints for averaging.
        pivot_num: Atom number(s) defining the pivot point. Can be int or
            list of ints for averaging.
        ref: Rotation axis vector (default [0,0,1], i.e. Z-axis).

    Returns:
        Deep copy of the PDB dictionary with randomly rotated coordinates.
    """
    pdb = copy.deepcopy(pdb_ori)
    tip = []
    pivot = []
    for res in pdb:
        for atom in pdb[res]:
            if isinstance(tip_num, list):
                if atom[1] in tip_num:
                    tip.append(pdb[res][atom])
            else:
                if atom[1] == tip_num:
                    tip = pdb[res][atom]
            if isinstance(pivot_num,list):
                if atom[1] in pivot_num:
                    pivot.append(pdb[res][atom])
            else:
                if atom[1] == pivot_num:
                    pivot = pdb[res][atom]
    if isinstance(tip_num, list):
        tip = np.mean(tip,axis=0)
    if isinstance(pivot_num,list):
        pivot = np.mean(pivot,axis=0)
    angle = random.uniform(0,6.28)
    axis = np.array(ref)
    R = rotation_matrix(axis,angle)
    if len(pdb[res]) > 1:
        for res in pdb:
            for atom in pdb[res]:
                pdb[res][atom] = align_vectors(pdb[res][atom]-pivot,np.array(ref),R)+pivot
    return pdb

def translate_pdb(pdb_ori,target=None,ref_atm=None,vec=None):
    """Translate a parsed PDB structure by a vector or toward a target point.

    Either a target/ref_atm pair or a vec must be provided. When target and
    ref_atm are given, the structure is translated so that ref_atm moves
    to the target position.

    Args:
        pdb_ori: Parsed PDB dictionary (residue -> atom -> coordinates).
        target: Target position as a numpy array (used with ref_atm).
        ref_atm: Atom number of the reference atom to move to target.
        vec: Explicit translation vector as a numpy array.

    Returns:
        Deep copy of the PDB dictionary with translated coordinates.
    """
    pdb = copy.deepcopy(pdb_ori)
    if target is not None and ref_atm is not None:
        for res in pdb:
            for atom in pdb[res]:
                if atom[1] == ref_atm:
                    ref = pdb[res][atom]
        tran_vec = ref-target
    elif vec is not None:
        tran_vec = vec
    else:
        logger.critical("A target and reference atom, or a translation vector has to be provided")
        exit()
    for res in pdb:
        for atom in pdb[res]:
            pdb[res][atom] = pdb[res][atom]-tran_vec
    return pdb

def superimpose_pdb(pdb1,pdb2):
    """Superimpose pdb2 onto pdb1 using a three-point alignment.

    Uses the first three residues/atoms to compute a translation and
    two sequential rotations for structural superposition. Writes
    intermediate files ``trans.pdb`` and ``rot1.pdb`` for debugging.

    Args:
        pdb1: Reference parsed PDB dictionary.
        pdb2: Mobile parsed PDB dictionary to superimpose onto pdb1.

    Returns:
        Deep copy of pdb2 with coordinates superimposed onto pdb1.
    """

    points = []

    count = 0
    while count < 3:
        key   = list(pdb1.keys())[count]
        key2  = list(pdb1[key].keys())[count]
        points.append([pdb1[key][key2],pdb2[key][key2]])
        count += 1

    trans_vec = points[0][1]-points[0][0]
#    print(trans_vec)

    for n, point in enumerate(points):
        points[n][1] = points[n][1]-trans_vec

    angle = vector_angle(points[1][1]-points[0][0],points[1][0]-points[0][0])
    axis = np.cross(points[1][1]-points[0][0],points[1][0]-points[0][0])

    R = rotation_matrix(axis,angle)


    if not np.allclose(align_vectors(points[1][1]-points[0][0],points[1][0]-points[0][0],R),points[1][0]-points[0][0],atol=1e-01):
        #print("Flipping!")
        R = rotation_matrix(axis,-angle)

    pdb3 = translate_pdb(pdb2,vec=trans_vec)

    pdb_write(pdb3,outfile="trans.pdb")

    for res in pdb3:
        for atom in pdb3[res]:
            pdb3[res][atom] = align_vectors(pdb3[res][atom]-points[0][0],points[1][0]-points[0][0],R)+points[0][0]

    for n, point in enumerate(points):
        points[n][1] = align_vectors(points[n][1]-points[0][0],points[1][0]-points[0][0],R)+points[0][0]

    pdb_write(pdb3,outfile="rot1.pdb")

    axis = points[1][0]-points[0][0]

    axis_n     = axis/np.linalg.norm(axis)
    vec_proj1  = np.dot((points[2][1]-points[0][0]),axis_n)
    vec_proj2  = np.dot((points[2][0]-points[0][0]),axis_n)
    line_point1 = points[0][0] + vec_proj1*axis_n
    line_point2 = points[0][0] + vec_proj2*axis_n

    angle = vector_angle(points[2][1]-line_point1,points[2][0]-line_point1)

    R = rotation_matrix(axis,angle)


    if not np.allclose(align_vectors(points[2][1]-line_point1,points[2][0]-line_point1,R),points[2][0]-line_point1,atol=1e-02):
#        print("Flipping2!")
        R = rotation_matrix(axis,-angle)

    for res in pdb3:
        for atom in pdb3[res]:
            pdb3[res][atom] = align_vectors(pdb3[res][atom]-line_point1,points[1][0]-line_point1,R)+line_point1

    return pdb3

def sphere_dist(rad, dx, dy=0, dz=0):
    """Calculate the geodesic (great-circle) distance on a sphere surface.

    Args:
        rad: Radius of the sphere.
        dx: Displacement in x.
        dy: Displacement in y (default 0).
        dz: Displacement in z (default 0).

    Returns:
        Geodesic distance on the sphere surface.
    """
    return rad*2*np.arcsin(np.sqrt(dx**2+dy**2+dz**2)/(2*rad))

def sphere_rectangle_area(rad, a, b):
    """Calculate the area of a spherical rectangle.

    Converts chord lengths to arc lengths and computes the area of the
    corresponding region on a sphere.

    Args:
        rad: Radius of the sphere.
        a: First side length (chord).
        b: Second side length (chord).

    Returns:
        Area of the spherical rectangle.
    """
    a = sphere_dist(rad, a)
    b = sphere_dist(rad, b)
    return rad**2*(2*np.pi-4*np.arccos(np.tan(a/(2*rad))*np.tan(b/(2*rad))))

def sphere_integral(a,b,c,r):
    """Compute the volume of a sphere via triple integration.

    Integrates the unit function over a sphere of radius r centered at
    (a, b, c).

    Args:
        a: X-coordinate of the sphere center.
        b: Y-coordinate of the sphere center.
        c: Z-coordinate of the sphere center.
        r: Radius of the sphere.

    Returns:
        Volume of the sphere (numerical integration result).
    """
    f = lambda z, y, x: 1
    return integrate.tplquad(f, a-r, a+r,
                lambda x: -np.sqrt(r**2-(x-a)**2)+b,             lambda x: np.sqrt(r**2-(x-a)**2)+b,
                lambda x, y: -np.sqrt(r**2-(x-a)**2-(y-b)**2)+c, lambda x, y: np.sqrt(r**2-(x-a)**2-(y-b)**2)+c)[0]

def sphere_integral_square(x_min,x_max,y_min,y_max,z_min=None, z_max=None,r1=None,r2=None, a=0,b=0,c=0):
    """Compute the volume between spherical caps within a rectangular XY region.

    Integrates over a rectangular XY domain with Z bounds defined by one or
    two concentric spheres, or a combination of a flat plane and a sphere.

    Args:
        x_min: Minimum x boundary.
        x_max: Maximum x boundary.
        y_min: Minimum y boundary.
        y_max: Maximum y boundary.
        z_min: Flat minimum z boundary (used with r2).
        z_max: Flat maximum z boundary (used with r1).
        r1: Inner sphere radius (lower Z surface).
        r2: Outer sphere radius (upper Z surface).
        a: X-coordinate of sphere center (default 0).
        b: Y-coordinate of sphere center (default 0).
        c: Z-coordinate of sphere center (default 0).

    Returns:
        Computed volume between the specified surfaces.

    Raises:
        ValueError: If the radius is too small for the given XY dimensions,
            or if an invalid combination of parameters is provided.
    """
    f = lambda z, y, x: 1
    if r1 is not None and r2 is not None:
        if r1**2-(x_max-a)**2-(y_max-b)**2 < 0:
            logger.critical("Radius is too small for given dimensions!")
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                lambda x, y: np.sqrt(r1**2-(x-a)**2-(y-b)**2)+c, lambda x, y: np.sqrt(r2**2-(x-a)**2-(y-b)**2)+c)[0]
    elif z_min is not None and r2 is not None:
        if r2**2-(x_max-a)**2-(y_max-b)**2 < 0:
            logger.critical("Radius is too small for given dimensions!")
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                lambda x, y: z_min, lambda x, y: np.sqrt(r2**2-(x-a)**2-(y-b)**2)+c)[0]
    elif z_max is not None and r1 is not None:
        if r1**2-(x_max-a)**2-(y_max-b)**2 < 0:
            logger.critical("Radius is too small for given dimensions!")
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                lambda x, y: np.sqrt(r1**2-(x-a)**2-(y-b)**2)+c, lambda x, y: z_max)[0]
    else:
        raise ValueError

def gauss_rectangle_area(x_min,x_max,y_min,y_max,b,d,h,a=0,c=0):
    """Compute the surface area of a Gaussian bump over a rectangular region.

    Integrates the surface element of a 2D Gaussian function
    z = h * exp(-(x-a)^2/(2b^2) - (y-c)^2/(2d^2)) over the given
    rectangular domain.

    Args:
        x_min: Minimum x boundary.
        x_max: Maximum x boundary.
        y_min: Minimum y boundary.
        y_max: Maximum y boundary.
        b: Gaussian width parameter in x.
        d: Gaussian width parameter in y.
        h: Gaussian height (amplitude).
        a: X-coordinate of the Gaussian center (default 0).
        c: Y-coordinate of the Gaussian center (default 0).

    Returns:
        Surface area of the Gaussian surface over the rectangle.
    """
    f = lambda y, x: np.sqrt(1 + (-h*(x-a)*np.exp(-(x-a)**2/(2*b**2)-(y-c)**2/(2*d**2))/b**2)**2 + (-h*(y-c)*np.exp(-(x-a)**2/(2*b**2)-(y-c)**2/(2*d**2))/d**2)**2)
    return integrate.dblquad(f, x_min, x_max,
                lambda x: y_min,lambda x: y_max)[0]

def gauss_integral_square(x_min,x_max,y_min,y_max,b,d,h,a=0,c=0,z_min=None, z_max=None, g1=None, g2=None):
    """Compute the volume between two Gaussian surfaces over a rectangular region.

    Integrates the unit function in a rectangular XY domain with Z bounds
    defined by one or two Gaussian functions of the form
    z = h * exp(-(x-a)^2/(2b^2) - (y-c)^2/(2d^2)) + offset.

    Args:
        x_min: Minimum x boundary.
        x_max: Maximum x boundary.
        y_min: Minimum y boundary.
        y_max: Maximum y boundary.
        b: Gaussian width parameter in x.
        d: Gaussian width parameter in y.
        h: Gaussian height (amplitude).
        a: X-coordinate of the Gaussian center (default 0).
        c: Y-coordinate of the Gaussian center (default 0).
        z_min: Flat minimum z boundary (used with g2).
        z_max: Flat maximum z boundary (used with g1).
        g1: Vertical offset for the lower Gaussian surface.
        g2: Vertical offset for the upper Gaussian surface.

    Returns:
        Computed volume between the specified surfaces.

    Raises:
        ValueError: If g2 < g1, g2 < z_min, z_max < g1, or if an invalid
            combination of parameters is provided.
    """
    f = lambda z, y, x: 1
    f1= lambda y, x: h*np.exp(-(x-a)**2/(2*b**2)-(y-c)**2/(2*d**2))+g1
    f2= lambda y, x: h*np.exp(-(x-a)**2/(2*b**2)-(y-c)**2/(2*d**2))+g2
    if g1 is not None and g2 is not None:
        if g2-g1 < 0:
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                f1, f2)[0]
    elif z_min is not None and g2 is not None:
        if g2-z_min < 0:
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                lambda x, y: z_min, f2)[0]
    elif z_max is not None and g1 is not None:
        if z_max-g1 < 0:
            raise ValueError
        return integrate.tplquad(f, x_min, x_max,
                lambda x: y_min,             lambda x: y_max,
                f1, lambda x, y: z_max)[0]
    else:
        raise ValueError

# VdW dictionary from PDBREMIX
VDW_RADII_DICT = {
    'H':  1.20, 'N':  1.55, 'NA': 2.27, 'CU': 1.40, 'CL': 1.75,
    'C':  1.70, 'O':  1.52, 'I':  1.98, 'P':  1.80, 'B':  1.85,
    'BR': 1.85, 'S':  1.80, 'SE': 1.90, 'F':  1.47, 'FE': 1.80,
    'K':  2.75, 'MN': 1.73, 'MG': 1.73, 'ZN': 1.39, 'HG': 1.80,
    'XE': 1.80, 'AU': 1.80, 'LI': 1.80, '.':  1.80
}

class VolumeProfiler:
    def __init__(self, pdb_file):
        """
        Loads PDB, maps atoms to custom VdW radii, and preps for calculation.
        """
    
        # Parse PDB
        pdb_dict = pdb_parse(pdb_file, onlybb=False)
    
        coords = []
        elements = []
        names = []
    
        # Flatten parsed structure
        for residue in pdb_dict.values():
            for (atomname, atomnum), xyz in residue.items():
                coords.append(xyz)
                names.append(atomname)
    
                # crude element guess: first character of atom name
                # (matches PDB / MDAnalysis convention)
                elements.append(atomname[0])
    
        # Convert to numpy
        self.coords = np.asarray(coords, dtype=np.float32)
        elements = np.asarray(elements, dtype=object)
        names = np.asarray(names, dtype=object)
    
        # --- Map VdW radii ---
        self.radii = self._assign_radii(elements, names, len(self.coords))
        
        # Define bounding box with padding (largest radius + buffer)
        max_r = np.max(self.radii)
        self.min_coord = np.min(self.coords, axis=0) - (max_r + 0.5)
        self.max_coord = np.max(self.coords, axis=0) + (max_r + 0.5)
        
        # Profile storage
        self.z_volume_profile = None
        self.z_bins = None
        self.profile_resolution = None
        self.z_start = None

    def _assign_radii(self, elements, names, n_atoms):
        """
        Maps atom elements/names to the VDW_RADII_DICT.
        """
        radii_array = np.zeros(n_atoms, dtype=np.float32)
        
        # Helper to lookup radius
        def get_r(key):
            # Try exact match, then upper case
            k = key.upper()
            return VDW_RADII_DICT.get(k, VDW_RADII_DICT['.'])

        # Iterate and assign
        # (This is done once in Python; overhead is negligible compared to MC loop)
        for i in range(n_atoms):
            # Priority 1: Check the Element column (cleanest)
            el = elements[i].upper()
            if el in VDW_RADII_DICT:
                radii_array[i] = VDW_RADII_DICT[el]
            else:
                # Priority 2: Parse from Atom Name (e.g., "CA" -> "C", "CB" -> "C")
                # Heuristic: Take first character if length > 0
                name = names[i].upper()
                # Remove numbers commonly found in PDB names (e.g., C1, H2)
                clean_name = ''.join([c for c in name if not c.isdigit()])
                
                if clean_name in VDW_RADII_DICT:
                    radii_array[i] = VDW_RADII_DICT[clean_name]
                elif len(clean_name) > 0 and clean_name[0] in VDW_RADII_DICT:
                     radii_array[i] = VDW_RADII_DICT[clean_name[0]]
                else:
                    radii_array[i] = VDW_RADII_DICT['.']
                    
        return radii_array

    def build_profile(self, resolution=0.5, samples_per_bin=10000, threads=1):
        """
        Builds the Z-axis volume histogram.
        resolution: Step size in Angstroms for the Z-slices.
        samples_per_bin: MC samples per slice. Higher = more precision.
        threads: Number of Numba threads for parallel MC sampling.
        """
        numba.set_num_threads(threads)
        # 1. Build Neighbor List (Spatial Hash)
        cell_size = np.max(self.radii) * 2.0
        grid_dim, cell_starts, cell_counts, sorted_indices = build_cell_list(
            self.coords, self.min_coord, self.max_coord, cell_size
        )

        # 2. Setup Z-Bins
        z_min, z_max = self.min_coord[2], self.max_coord[2]
        num_bins = int(np.ceil((z_max - z_min) / resolution))
        self.profile_resolution = resolution
        self.z_start = z_min
        
        # 3. Run Parallel Monte Carlo
        # Calculate XY area for volume scaling
        box_area_xy = (self.max_coord[0] - self.min_coord[0]) * \
                      (self.max_coord[1] - self.min_coord[1])
        
        bin_counts, total_samples = run_z_projected_mc(
            self.coords, self.radii, 
            self.min_coord, self.max_coord,
            cell_starts, cell_counts, sorted_indices, 
            grid_dim, cell_size,
            num_bins, samples_per_bin
        )
        
        # Convert hits to Volume
        slab_vol_total = box_area_xy * resolution
        self.z_volume_profile = (bin_counts / total_samples) * slab_vol_total
        self.z_bins = np.linspace(z_min, z_max, num_bins, endpoint=False)
        
        logger.debug(f"Calculated volume using MC based sampling algorithm with z-profile: {num_bins} slabs, {resolution}A thickness.")

    def get_slab_volume(self, z_lower, z_upper):
        """
        Instantly queries the pre-calculated profile.
        """
        if self.z_volume_profile is None:
            return 0.0
        if z_upper > self.max_coord[2]:
            z_upper = self.max_coord[2]
        if z_lower < self.min_coord[2]:
            z_lower = self.min_coord[2]
        
        # Convert Z coords to array indices
        idx_start = int((z_lower - self.z_start) / self.profile_resolution)
        idx_end = int((z_upper - self.z_start) / self.profile_resolution)
        
        # Clamp
        idx_start = max(0, idx_start)
        idx_end = min(len(self.z_volume_profile), idx_end)
        
        if idx_start >= idx_end:
            return 0.0
            
        return np.sum(self.z_volume_profile[idx_start:idx_end])

# --- Numba Kernels (Unchanged, Pure Mathematical Logic) ---

@njit
def build_cell_list(coords, min_coord, max_coord, cell_size):
    n_atoms = len(coords)
    grid_dim = np.ceil((max_coord - min_coord) / cell_size).astype(np.int32)
    atom_cell_indices = np.zeros(n_atoms, dtype=np.int32)
    
    total_cells = grid_dim[0] * grid_dim[1] * grid_dim[2]
    cell_counts = np.zeros(total_cells, dtype=np.int32)
    
    for i in range(n_atoms):
        ix = int((coords[i, 0] - min_coord[0]) / cell_size)
        iy = int((coords[i, 1] - min_coord[1]) / cell_size)
        iz = int((coords[i, 2] - min_coord[2]) / cell_size)
        
        ix = max(0, min(ix, grid_dim[0] - 1))
        iy = max(0, min(iy, grid_dim[1] - 1))
        iz = max(0, min(iz, grid_dim[2] - 1))
        
        flat_idx = ix + iy * grid_dim[0] + iz * grid_dim[0] * grid_dim[1]
        atom_cell_indices[i] = flat_idx
        cell_counts[flat_idx] += 1
        
    cell_starts = np.zeros(total_cells, dtype=np.int32)
    current_start = 0
    for i in range(total_cells):
        cell_starts[i] = current_start
        current_start += cell_counts[i]
        
    sorted_indices = np.zeros(n_atoms, dtype=np.int32)
    current_fills = np.zeros(total_cells, dtype=np.int32)
    
    for i in range(n_atoms):
        cell_idx = atom_cell_indices[i]
        pos = cell_starts[cell_idx] + current_fills[cell_idx]
        sorted_indices[pos] = i
        current_fills[cell_idx] += 1
        
    return grid_dim, cell_starts, cell_counts, sorted_indices

@njit(parallel=True)
def run_z_projected_mc(coords, radii, min_c, max_c,
                       cell_starts, cell_counts, sorted_indices,
                       grid_dim, cell_size, num_bins, samples_per_bin):
    
    bin_counts = np.zeros(num_bins, dtype=np.int64)
    z_range = max_c[2] - min_c[2]
    
    # Parallelize over Z-bins
    for b in prange(num_bins):
        # Local slab definition
        z_slab_min = min_c[2] + b * (z_range / num_bins)
        z_slab_height = z_range / num_bins
        
        hits = 0
        for _ in range(samples_per_bin):
            rx = np.random.uniform(min_c[0], max_c[0])
            ry = np.random.uniform(min_c[1], max_c[1])
            rz = np.random.uniform(z_slab_min, z_slab_min + z_slab_height)
            
            # Find cell
            ix = int((rx - min_c[0]) / cell_size)
            iy = int((ry - min_c[1]) / cell_size)
            iz = int((rz - min_c[2]) / cell_size)
            
            is_inside = False
            
            # Search neighbors
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    for dz in range(-1, 2):
                        nx, ny, nz = ix + dx, iy + dy, iz + dz
                        
                        if (nx >= 0 and nx < grid_dim[0] and 
                            ny >= 0 and ny < grid_dim[1] and 
                            nz >= 0 and nz < grid_dim[2]):
                            
                            flat_idx = nx + ny * grid_dim[0] + nz * grid_dim[0] * grid_dim[1]
                            start = cell_starts[flat_idx]
                            count = cell_counts[flat_idx]
                            
                            for k in range(count):
                                atom_idx = sorted_indices[start + k]
                                ax, ay, az = coords[atom_idx]
                                ar = radii[atom_idx]
                                
                                # Distance check
                                if (rx-ax)**2 + (ry-ay)**2 + (rz-az)**2 < ar*ar:
                                    is_inside = True
                                    break
                        if is_inside: break
                    if is_inside: break
                if is_inside: break
            
            if is_inside:
                hits += 1
        
        bin_counts[b] = hits
        
    return bin_counts, samples_per_bin


class MembraneParams(object):
    """Analyzes a protein PDB to compute membrane-embedding parameters.

    Reads a PDB file, re-indexes atoms and chains, optionally centers or
    translates the structure, and computes properties needed for membrane
    system building: total charge, mass, volume partitioning between
    membrane leaflets and solvent regions, and the maximum XY radius.

    Attributes:
        pdb: Path to the input PDB file.
        leaflet_z: Half-thickness of the membrane in Angstroms.
        grid: Path to a grid PDB file for volume calculation, or None.
        move: Whether to apply a translation vector.
        move_vec: Translation vector [x, y, z].
        xy_cen: Whether to center the structure in XY.
        z_cen: Whether to center the structure in Z.
        outpdb: Path for the output (re-indexed) PDB file.
        chain: Starting chain identifier.
        renumber: Whether to renumber residues sequentially.
        density: Estimated protein density (set after measure()).
        chains: Number of chains detected.
        charge: Net formal charge of the protein.
        mass: Total mass in Daltons.
        hydrogens: Number of hydrogen atoms found.
        use_hex: Whether hexadecimal atom numbering is needed.
        mem_atoms_mass_up: Mass of atoms in the upper membrane leaflet.
        mem_atoms_mass_down: Mass of atoms in the lower membrane leaflet.
        solv_atoms_mass_up: Mass of atoms above the membrane.
        solv_atoms_mass_down: Mass of atoms below the membrane.
        new_pdb: List of reformatted PDB lines.
        x_mem: Sorted X coordinates of atoms within the membrane region.
        y_mem: Sorted Y coordinates of atoms within the membrane region.
        x: List of all X coordinates.
        y: List of all Y coordinates.
        z: List of all Z coordinates.
        minmax: Bounding box [x_min, y_min, z_min, x_max, y_max, z_max].
    """
    def __init__(self,pdb, leaflet_z, move=False, move_vec=None, xy_cen=False, z_cen = False, outpdb="PROT.pdb", chain=" ",renumber=False):
        """Initialize MembraneParams with PDB path and analysis options.

        Args:
            pdb: Path to the input PDB file.
            leaflet_z: Half-thickness of the membrane in Angstroms.
            grid: Path to a grid PDB for volume calculation, or None to
                use mass-based estimation.
            move: If True, apply move_vec translation to coordinates.
            move_vec: Translation vector [x, y, z], or None for [0,0,0].
            xy_cen: If True, center the protein in the XY plane.
            z_cen: If True, center the protein along the Z axis.
            outpdb: Output path for the re-indexed PDB (default "PROT.pdb").
            chain: Starting chain ID character (default " ").
            renumber: If True, renumber residues starting from 1.
        """
        #Getting variables into class attributes
        self.pdb = pdb
        self.leaflet_z = leaflet_z
        self.move = move
        self.move_vec = move_vec if move_vec is not None else [0, 0, 0]
        self.xy_cen = xy_cen
        self.z_cen = z_cen
        self.outpdb = outpdb
        self.chain = chain
        self.renumber = renumber


        #Variables to store values after
        self.density = None
        self.chains = 1
        self.charge = 0
        self.mass = 0
        self.hydrogens = 0
        self.use_hex = False
        self.mem_atoms_mass_up = 0
        self.mem_atoms_mass_down = 0
        self.solv_atoms_mass_up = 0
        self.solv_atoms_mass_down = 0
        self.new_pdb = []
        self.x_mem = []
        self.y_mem = []
        self.pdblines = None
        self.minmax = None

        self.x = []
        self.y = []
        self.z = []

        self._x_cen = 0
        self._y_cen = 0
        self._z_cen = 0

    def read_pdb(self):
        """Read PDB file contents into the pdblines attribute."""
        file = open(self.pdb, "r")
        self.pdblines = file.readlines()
        file.close()

    def write_pdb(self):
        """Write the re-indexed PDB lines to the output file."""
        new_file = open(self.outpdb,"w")
        new_file.writelines(self.new_pdb)
        new_file.close()

    def xyz_center(self):
        """Calculate the geometric center of the PDB from coordinate min/max averages.

        Sets the internal ``_x_cen``, ``_y_cen``, and ``_z_cen`` attributes
        used for optional coordinate centering during re-indexing.
        """
        x = []
        y = []
        z = []
        for line in self.pdblines:
            if (line[0:4] == "ATOM" or line[0:6] == "HETATM") and  line[17:20].strip() != "DUM":
                x_coord = float(line[30:38])+self.move_vec[0]
                y_coord = float(line[38:46])+self.move_vec[1]
                z_coord = float(line[46:54])+self.move_vec[2]
                x.append(float(x_coord))
                y.append(float(y_coord))
                z.append(float(z_coord))
        self._x_cen = (max(x)+min(x))/2
        self._y_cen = (max(y)+min(y))/2
        self._z_cen = (max(z)+min(z))/2

    def pdb_reindex(self):
        """Re-index atoms and chains in the PDB, applying optional transformations.

        Iterates over PDB lines to renumber residues, assign chain IDs,
        fix common atom naming issues (ILE CD -> CD1, OT1 -> O, OT2 -> OXT),
        apply coordinate centering or translation, accumulate charge and mass,
        and partition atom masses into membrane and solvent regions based on
        the leaflet_z threshold.
        """
        last_chain   = None
        last_resnum  = None
        last_type    = None
        track        = None
        chain_list   = list(string.ascii_uppercase)+list(string.ascii_lowercase)+list(map(str,range(0,10)))
        resnum_index = 1
        chain = self.chain

        #Calcualte PDB center to be used later
        self.xyz_center()

        if chain == " ":
            chain_index  = 0
        else:
            try:
                chain_index = chain_list.index(chain)
            except ValueError:
                logger.warning("Chain ID not found in list")
                chain_index  = 0
        for line in self.pdblines:
            if line[0:3] == "TER":
                self.new_pdb.append("TER\n")
                continue
            if (line[0:4] == "ATOM" or line[0:6] == "HETATM") and  line[17:20].strip() != "DUM":
                if last_type is not None and line[0:6].strip() != last_type:
                    if not line.startswith("TER") and not self.new_pdb[-1].startswith("TER"):
                        self.new_pdb.append("TER\n")
                last_type = line[0:6].strip()
                residue = line[17:21].strip()
                atomnum = int(line[6:11].strip())
                atomname = line[12:16].strip()
                resnum = int(line[22:26].strip())
                if self.renumber and resnum != last_resnum:
                    last_resnum   = resnum
                    resnum_new    = resnum_index
                    resnum_index += 1
                    if resnum_new > 9999:
                        resnum_new = ((resnum_new-1)%9999)+1
                if self.renumber:
                    resnum = resnum_new
                segid  = line[72:76].strip()
                if residue == "ILE" and atomname == "CD":
                    atomname = "CD1"
                if residue == "CYM":
                    if atomname == "HN1" or atomname == "HB1":
                        continue
                if atomname == "OT1":
                    atomname = "O"
                if atomname == "OT2":
                    atomname = "OXT"
                if len(atomname) == 3:
                    ali = ">"
                else:
                    ali = "^"
                if last_chain is not None and last_chain != line[21:22]:
                    if not line.startswith("TER") and not self.new_pdb[-1].startswith("TER"):
                        self.new_pdb.append("TER\n")
                    self.chains += 1
                    chain_index += 1
                    chain = chain_list[chain_index % len(chain_list)]
                last_chain = line[21:22]
                if not self.move and not self.xy_cen:
                    x_coord = float(line[30:38])
                    y_coord = float(line[38:46])
                    z_coord = float(line[46:54])
                elif not self.move:
                    x_coord = float(line[30:38])-self._x_cen
                    y_coord = float(line[38:46])-self._y_cen
                    z_coord = float(line[46:54])
                    if self.z_cen:
                        z_coord = float(line[46:54])-self._z_cen
                elif not self.xy_cen:
                    x_coord = float(line[30:38])+self.move_vec[0]
                    y_coord = float(line[38:46])+self.move_vec[1]
                    z_coord = float(line[46:54])+self.move_vec[2]
                else:
                    x_coord = float(line[30:38])+self.move_vec[0]-self._x_cen
                    y_coord = float(line[38:46])+self.move_vec[1]-self._y_cen
                    z_coord = float(line[46:54])+self.move_vec[2]
                    if self.z_cen:
                        z_coord = float(line[46:54])+self.move_vec[2]-self._z_cen
                self.x.append(float(x_coord))
                self.y.append(float(y_coord))
                self.z.append(float(z_coord))
                line = line[0:6]+"{:>5d} {:{align}4} {:<4}{:1}{:>4}    {:>8.3f}{:>8.3f}{:>8.3f}{:>6.2f}{:>6.2f}      {:<4}{:>2}\n".format( atomnum,atomname,residue,chain,resnum,x_coord,y_coord,z_coord,1,0,segid,atomname[0],align=ali)
                self.new_pdb.append(line)

                if line[17:20].strip() in charged and track != line[22:26].strip():
                    self.charge += charged[line[17:20].strip()]
                    track =  line[22:26].strip()
                #Add masses according to z location
                if line[0:4] == "ATOM":
                    element = data.guess_element(residue,atomname)
                    if element in data.masses:
                        self.mass += data.masses[element]
                        if element == "H":
                            self.hydrogens += 1
                        if self.z[-1] > self.leaflet_z:
                            self.solv_atoms_mass_up += data.masses[element]
                        elif self.z[-1] < -self.leaflet_z:
                            self.solv_atoms_mass_down += data.masses[element]
                        else:
                            if self.z[-1] >= 0:
                                self.mem_atoms_mass_up +=  data.masses[element]
                            else:
                                self.mem_atoms_mass_down +=  data.masses[element]
                            self.x_mem.append(self.x[-1])
                            self.y_mem.append(self.y[-1])
                    else:
                        logger.warning("Atom "+element+" mass will not be considered!\n")

    def get_volume_profile(self, threads=1):
        profiler = VolumeProfiler(self.outpdb)
        profiler.build_profile(resolution=0.1, samples_per_bin=10000, threads=threads)
        self.mem_vol_up    = profiler.get_slab_volume(0, self.leaflet_z)
        self.mem_vol_down  = profiler.get_slab_volume(-self.leaflet_z, 0)
        self.solv_vol_up   = profiler.get_slab_volume(self.leaflet_z, np.inf)
        self.solv_vol_down = profiler.get_slab_volume(-np.inf, -self.leaflet_z)
        self.volume = self.mem_vol_up+self.mem_vol_down+self.solv_vol_up+self.solv_vol_down 

    def estimated_atoms(self):
        """Estimate protein volume from mass using density prediction.

        Computes density from molecular weight, then derives total volume
        and per-region volume estimates (membrane up/down, solvent up/down)
        from the mass partitioning accumulated during pdb_reindex().
        """
        est_density = estimated_density(self.mass)
        self.density = est_density*avogadro/10**24
        self.volume = self.mass/self.density
        self.mem_vol_up = self.mem_atoms_mass_up/self.density
        self.mem_vol_down = self.mem_atoms_mass_down/self.density
        self.solv_vol_up = self.solv_atoms_mass_up/self.density
        self.solv_vol_down = self.solv_atoms_mass_down/self.density

    def measure(self, threads=1):
        """Run the full analysis pipeline and return protein parameters.

        Reads the PDB, re-indexes it, writes the output, and computes
        the maximum XY radius, volume estimates (optionally from grid),
        and bounding box coordinates.

        Args:
            threads: Number of CPU threads for MC volume calculation.

        Returns:
            Tuple of (minmax, max_rad, charge, volume, mem_vol_up,
            mem_vol_down, solv_vol_up, solv_vol_down, density, mass, chains)
            where minmax is [x_min, y_min, z_min, x_max, y_max, z_max].
        """

        self.read_pdb()
        self.pdb_reindex()
        self.write_pdb()

        if self.hydrogens == 0:
            logger.warning("Protein doesn't look to be protonated! Please consider that this will cause a bad estimation of the volume and of the packing process!\n\n")

        #### MAXIMUM PROTEIN XY RADIUS ###

        mean_x  = sum(self.x)/len(self.x)
        mean_y  = sum(self.y)/len(self.y)
        self.max_rad = max([math.sqrt((self.x[n]-mean_x)**2+(self.y[n]-mean_y)**2) for n, _ in enumerate(self.x)])

        #### IF GRID VOL CALCULATION, REPLACE ESTIMATION ####
   
        self.estimated_atoms()  # Always needed: sets self.density
        try:
            self.get_volume_profile(threads=threads)  # Overwrites volumes with MC-based values
        except Exception as e:
            logger.warning(f"MC volume calculation failed ({e}), using mass-based volume estimation")
 
        self.x.sort()
        self.y.sort()
        self.z.sort()
        self.x_mem.sort()
        self.y_mem.sort()
        self.minmax = [self.x[0], self.y[0], self.z[0], self.x[-1], self.y[-1], self.z[-1]]
        try:
            area_est = (((self.x_mem[-1]-self.x_mem[0])+(self.y_mem[-1]-self.y_mem[0]))/4)**2*math.pi # Maybe estimate the protein area in the membrane...(Not used ATM)
        except IndexError:
            logger.warning("WARNING! The protein doesn't have atoms sitting in the membrane! Make sure that it was correctly aligned and that the placement is as intended!")
        return [self.x[0], self.y[0], self.z[0], self.x[-1], self.y[-1], self.z[-1]], self.max_rad, self.charge, self.volume, self.mem_vol_up, self.mem_vol_down, self.solv_vol_up, self.solv_vol_down, self.density, self.mass, self.chains

    def __repr__(self):
        """Return a string representation of the MembraneParams instance."""
        return f"<MembraneParam PDB:{self.pdb}>"


def calculate_box_geometry(minmax, max_rad, leaflet_z=23.0, distance=15.0, distance_wat=17.5,
                           dims=None, cubic=False, asym=False, xygauss=None):
    """Calculate simulation box geometry from protein dimensions.

    Computes the box boundaries used by PACKMOL for packing lipids, water,
    and ions around a membrane-embedded protein. Supports cubic, asymmetric,
    and Gaussian-curved membrane configurations.

    Args:
        minmax: Bounding box as [x_min, y_min, z_min, x_max, y_max, z_max]
            from MembraneParams.measure().
        max_rad: Maximum XY radius of the protein from MembraneParams.measure().
        leaflet_z: Half-thickness of the membrane in Angstroms (default 23.0).
        distance: XY distance buffer around the protein in Angstroms (default 15.0).
        distance_wat: Z distance buffer for water layers in Angstroms (default 17.5).
        dims: Fixed box dimensions as (x, y, z) tuple, or None for automatic sizing.
        cubic: If True, enforce a cubic simulation box.
        asym: If True, use asymmetric box dimensions.
        xygauss: Gaussian curvature parameters tuple, or None for flat membranes.

    Returns:
        Dictionary containing 'box' (with x_min/max, y_min/max, z_min/max),
        'membrane' (with upper/lower leaflet Z positions), 'max_side_len',
        'minmax', and 'max_rad'.
    """
    com = [(minmax[0]+minmax[3])/2, (minmax[1]+minmax[4])/2, (minmax[2]+minmax[5])/2]

    if dims is not None:
        pdbx_min = com[0] - dims[0]/2
        pdbx_max = com[0] + dims[0]/2
        pdby_min = com[1] - dims[1]/2
        pdby_max = com[1] + dims[1]/2
        pdbz_min = com[2] - dims[2]/2
        pdbz_max = com[2] + dims[2]/2
    else:
        pdbx_min = minmax[0]
        pdbx_max = minmax[3]
        pdby_min = minmax[1]
        pdby_max = minmax[4]
        pdbz_min = minmax[2]
        pdbz_max = minmax[5]

    pdbx_len = pdbx_max - pdbx_min
    pdby_len = pdby_max - pdby_min
    pdbz_len = pdbz_max - pdbz_min

    if not asym:
        if dims is None:
            max_side_len = 2 * max_rad + 2 * distance
        else:
            max_side_len = max(dims[:2])
        if cubic:
            max_side_len = max(max_side_len, pdbz_len + 2 * distance)
        diff_x = max_side_len - pdbx_len
        diff_y = max_side_len - pdby_len
        diff_z = max_side_len - pdbz_len
    else:
        # Asymmetric mode - check z boundaries
        if pdbz_min > -(leaflet_z + 5):
            correct_z = pdbz_min + (leaflet_z + 5)
            pdbz_min = -(leaflet_z + 5)
            pdbz_max = pdbz_max - correct_z
        if pdbz_max < (leaflet_z + 5):
            correct_z = pdbz_max - (leaflet_z + 5)
            pdbz_max = (leaflet_z + 5)
            pdbz_min = pdbz_min - correct_z
        diff_x = diff_y = diff_z = 0
        max_side_len = max(pdbx_len, pdby_len)

    x_min = pdbx_min - diff_x/2
    x_max = pdbx_max + diff_x/2
    y_min = pdby_min - diff_y/2
    y_max = pdby_max + diff_y/2
    z_min = pdbz_min - diff_z/2
    z_max = pdbz_max + diff_z/2

    # Adjust z dimensions for non-cubic box
    if not cubic and not asym:
        z_min = pdbz_min - distance_wat
        if z_min > -(leaflet_z + distance_wat):
            z_min = -(leaflet_z + distance_wat)
        z_max = pdbz_max + distance_wat
        if z_max < (leaflet_z + distance_wat):
            z_max = (leaflet_z + distance_wat)
        if xygauss:
            z_max += float(xygauss[2])

    return {
        'box': {
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max,
            'z_min': z_min,
            'z_max': z_max,
        },
        'membrane': {
            'upper': leaflet_z,
            'lower': -leaflet_z,
        },
        'max_side_len': max_side_len,
        'minmax': minmax,
        'max_rad': max_rad,
    }


def is_number(num):
    """Check whether a value can be converted to a float.

    Args:
        num: Value to test.

    Returns:
        True if the value is numeric, False otherwise.
    """
    try:
        float(num)
        return True
    except (ValueError, TypeError):
        return False


def pdb_parse(pdbfile, onlybb=True):
    """Parse a PDB file into a nested dictionary of atom coordinates.

    Args:
        pdbfile: Path to the PDB file.
        onlybb: If True, only parse backbone atoms (CA, CB, C, N, O) of
            standard amino acid residues. If False, parse all atoms.

    Returns:
        Dictionary keyed by (residue_name, residue_number, chain_id) tuples,
        with values being dictionaries of (atom_name, atom_number) -> numpy
        coordinate array.
    """
    CA_CB = {}
    pdb = open(pdbfile,"r").readlines()
    for line in pdb:
        if (line.startswith("ATOM") or line.startswith("HETATM")):
            residue = line[17:21].strip()
            atomnum = int(line[6:11].strip())
            atomname = line[12:16].strip()
            resnum = int(line[22:26].strip())
            chain = line[21:22]
            id = (residue,resnum,chain)
            if atomname in cgatoms and residue in residues and onlybb:
                if id not in CA_CB:
                    CA_CB[id]= {}
                CA_CB[id][(atomname,atomnum)] = np.array([float(line[30:38].strip()),float(line[38:46].strip()),float(line[46:54].strip())])
            if not onlybb:
                if id not in CA_CB:
                    CA_CB[id]= {}
                CA_CB[id][(atomname,atomnum)] = np.array([float(line[30:38].strip()),float(line[38:46].strip()),float(line[46:54].strip())])
    return CA_CB

def pdb_write(CA_CB, outfile="test.pdb"):
    """Write a parsed PDB dictionary to a PDB file.

    Args:
        CA_CB: Parsed PDB dictionary as returned by pdb_parse(), keyed by
            (residue_name, residue_number, chain_id) tuples.
        outfile: Output file path (default "test.pdb").
    """
    handle = open(outfile,"w")
    for res in sorted(CA_CB,key=lambda x:(x[2],x[1])):
        for atom in sorted(CA_CB[res], key=lambda x:x[1]):
            handle.write("ATOM  {:>5d} {:>4} {:>3}{:>2}{:>4d}    {:>8.3f}{:>8.3f}{:>8.3f}   1.00  0.00           {:1}\n".format(atom[1],"{:<3}".format(atom[0]),res[0],res[2],res[1],CA_CB[res][atom][0],CA_CB[res][atom][1],CA_CB[res][atom][2],atom[0][0]))
    handle.close()

def pdb_parse_TER(pdbfile, onlybb=True, noH=True, filter_res=None, filter_atm=None):
    """Parse a PDB file into molecule-separated dictionaries split by TER records.

    Similar to pdb_parse() but groups atoms by molecule (separated by TER
    lines) rather than by residue. Handles hexadecimal atom numbering from
    PACKMOL output.

    Args:
        pdbfile: Path to the PDB file.
        onlybb: If True, only parse backbone atoms of standard residues.
        noH: If True and onlybb is False, skip hydrogen atoms.
        filter_res: Set of residue names to include, or None for all.
        filter_atm: Set of atom names to include, or None for all.

    Returns:
        Dictionary keyed by (molecule_number, chain_id) tuples, with values
        being dictionaries of (residue_name, residue_number, atom_name,
        atom_number, line_tracker) -> numpy coordinate array.
    """
    CA_CB = {}
    pdb = open(pdbfile,"r").readlines()
    molnum = 1
    tracker = 1
    hex_switch = False
    atomlimit = False
    for line in pdb:
        if line.startswith("TER"):
            molnum += 1
        if (line.startswith("ATOM") or line.startswith("HETATM")):
            if line[6:11].strip() == "*****" and not atomlimit:
                logger.warning("Found atom number limit '*****'. Atom number parsing will be unreliable")
                atomlimit = True
            residue = line[17:21].strip()
            if not str(line[6:11].strip()).isnumeric():
                hex_switch = True
            if atomlimit:
                atomnum = atomnum + 1
            else:
                atomnum = int(line[6:11].strip(),16) if hex_switch else int(line[6:11].strip()) # asume hex 16 if parsing packmol
            atomname = line[12:16].strip()
            resnum = int(line[22:26].strip())
            chain = line[21:22]
            id = (molnum,chain)
            if atomname in cgatoms and residue in residues and onlybb:
                if id not in CA_CB:
                    CA_CB[id]= {}
                CA_CB[id][(residue, resnum, atomname, atomnum, tracker)] = np.array([float(line[30:38].strip()),float(line[38:46].strip()),float(line[46:54].strip())])
            if not onlybb:
                if noH:
                    if atomname.startswith("H"):
                        continue
                if filter_res is not None:
                    if residue not in filter_res:
                        continue
                if filter_atm is not None:
                    if atomname not in filter_atm:
                        continue
                if id not in CA_CB:
                    CA_CB[id]= {}
                CA_CB[id][(residue, resnum, atomname, atomnum, tracker)] = np.array([float(line[30:38].strip()),float(line[38:46].strip()),float(line[46:54].strip())])
        tracker += 1
    return CA_CB



def pdb_write_TER(CA_CB, outfile="test.pdb"):
    """Write a TER-separated parsed PDB dictionary to a PDB file.

    Writes molecules separated by TER records and ends with an END record.
    Handles atom numbers exceeding 99999 by switching to hexadecimal format.

    Args:
        CA_CB: Parsed PDB dictionary as returned by pdb_parse_TER(), keyed
            by (molecule_number, chain_id) tuples.
        outfile: Output file path (default "test.pdb").

    Returns:
        The output file path.
    """
    handle = open(outfile,"w")
    for mol in sorted(CA_CB,key=lambda x:x[0]):
        for atom in sorted(CA_CB[mol], key=lambda x:(x[4],x[1])): # Packmol output comes serialized first and foremost by atomnumber
            if atom[3] < 100000:
                handle.write("ATOM  {:>5d} {:>4} {:>3}{:>2}{:>4d}    {:>8.3f}{:>8.3f}{:>8.3f}   1.00  0.00           {:1}\n".format(atom[3],"{:<3}".format(atom[2]),atom[0],mol[1],atom[1],CA_CB[mol][atom][0],CA_CB[mol][atom][1],CA_CB[mol][atom][2],atom[0][0]))
            else:
                handle.write("ATOM  {:>5} {:>4} {:>3}{:>2}{:>4d}    {:>8.3f}{:>8.3f}{:>8.3f}   1.00  0.00           {:1}\n".format(hex(atom[3]),"{:<3}".format(atom[2]),atom[0],mol[1],atom[1],CA_CB[mol][atom][0],CA_CB[mol][atom][1],CA_CB[mol][atom][2],atom[0][0]))
        handle.write("TER\n")
    handle.write("END\n")
    handle.close()
    return outfile

def find_piercing_lipids(pdb, outfile="noclash.pdb", verbose=False):
    """Detect lipid tails that pierce through sterol or ring lipid structures.

    Identifies lipid acyl chain bonds whose midpoints fall within 2.5 Angstroms
    of sterol ring centers, PI inositol ring centers, or galactolipid sugar
    ring centers (MGG, DGG). These represent unphysical configurations where
    a lipid tail threads through a rigid ring.

    Args:
        pdb: Path to the PDB file containing the packed system.
        outfile: Output file path (unused, kept for interface compatibility).
        verbose: If True, enable verbose logging.

    Returns:
        Set of (molecule_number, chain_id) tuples identifying molecules
        containing piercing lipid tails that should be removed.
    """
    tails_dict  = pdb_parse_TER(pdb, onlybb=False, filter_res=tails)
    sterol_PI_dict = pdb_parse_TER(pdb, onlybb=False, filter_res=sterols_rings)

    midpoints = np.zeros((len(tails_dict),50,3))+np.inf
    midpointmap = {}

    ringpoints = np.zeros((len(sterol_PI_dict),5,3))+np.inf
    ringmap    = {}

    for i,r in enumerate(tails_dict):
        bond_idx = 0
        if i not in midpointmap:
            midpointmap[i] = r
        search_keys = list(tails_dict[r].keys())
        for x,a in enumerate(search_keys):
            for b in search_keys[x+1:]:
                if np.linalg.norm(tails_dict[r][a]-tails_dict[r][b]) < 1.7: # C-C bond length shouldn't be larger then 1.59A / 1.7 just in case
                    midpoints[i,bond_idx] = np.mean([tails_dict[r][a],tails_dict[r][b]], axis=0)
                    bond_idx += 1

    for i,r in enumerate(sterol_PI_dict):
        if i not in ringmap:
            ringmap[i] = r
        for ring_idx, ring in enumerate(sterol_ring_probes):
            ring_coords = []
            for ring_atom in ring:
                for a in sterol_PI_dict[r]:
                    #Have to check PI and sterols independently, as PI has same atomnames as sterol rings
                    # structure of dict key ('PI', 2, 'P31', 63, 25)  resname, resnum, atomname, atomnum, internal_idx
                    if a[2].strip() == ring_atom and not a[0] in PI_res and not a[0] in GG_res:
                        ring_coords.append(sterol_PI_dict[r][a])
            if len(ring_coords) > 0:
                ringpoints[i,ring_idx] = np.mean(ring_coords,axis=0)
        #Now check for PI and other rings
        ring_coords = []
        for ring_atom in PI_ring_probe:
            for a in sterol_PI_dict[r]:
                if a[2].strip() == ring_atom and a[0] in PI_res:
                    ring_coords.append(sterol_PI_dict[r][a])
        for ring_atom in MGG_ring_probe:
            for a in sterol_PI_dict[r]:
                if a[2].strip() == ring_atom and a[0] in GG_res:
                    ring_coords.append(sterol_PI_dict[r][a])
        #Here we hijack the sterol sterol coord structure and use the 4th slot
        if len(ring_coords) > 0:
            ringpoints[i,3] = np.mean(ring_coords,axis=0)
        ring_coords = []
        for ring_atom in DGG_ring_probe:
            for a in sterol_PI_dict[r]:
                if a[2].strip() == ring_atom and a[0] == "DGG":
                    ring_coords.append(sterol_PI_dict[r][a])
        #And for DGG we use the 5th slot
        if len(ring_coords) > 0:
            ringpoints[i,4] = np.mean(ring_coords,axis=0)


    to_remove = []

    for i,sterol in enumerate(ringpoints):
        for ring_center in sterol:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                pierce_dist = np.linalg.norm(midpoints-ring_center,axis=2)
            for pierce  in np.argwhere(pierce_dist < 2.5):   # H to H benzene "ring diameter" should be about 4.963A (from quick Avogadro min). Distance of the center of an aliphatic bond should be farther then this.
                to_remove.append(midpointmap[pierce[0]])
    to_remove = set(to_remove)

    if len(to_remove) > 0:
        logger.debug("The following lipids have clashing tails with sterols:")
    else:
        logger.debug("No piercing lipid found!")
    for clash in to_remove:
        tr_names  = [i[0] for i in set([clash_res[:2] for clash_res in tails_dict[clash].keys()])]
        tr_resids = [i[1] for i in set([clash_res[:2] for clash_res in tails_dict[clash].keys()])]
        logger.debug("Resnames:%s, Resids:%s" % (tr_names,tr_resids))
    return to_remove


def remove_piercing_lipids(pdb, to_remove, outfile="noclash.pdb", verbose=False):
    """Remove lipid molecules identified as piercing through ring structures.

    Parses the full PDB, deletes the offending molecules, and writes the
    cleaned structure to a new file.

    Args:
        pdb: Path to the input PDB file.
        to_remove: Set of (molecule_number, chain_id) tuples to remove,
            as returned by find_piercing_lipids().
        outfile: Path for the output PDB file (default "noclash.pdb").
        verbose: If True, log removal actions.

    Returns:
        Path to the output PDB file with piercing lipids removed.
    """
    original_dict  = pdb_parse_TER(pdb, onlybb=False, noH=False)

    if verbose:
        logger.debug("Removing clashing lipids")
    for clash in to_remove:
        del original_dict[clash]

    return pdb_write_TER(original_dict, outfile=outfile)




if __name__ == "__main__":
    pdb = sys.argv[1]
    print(measure_parms(pdb,23,None))
    if "-move" in sys.argv:
        vec = [float(i) for i in sys.argv[sys.argv.index("-move")+1].split(",")]
        print(measure_parms(pdb,23,move=True, move_vec=vec))
    if "-cen" in sys.argv:
        print(measure_parms(pdb,23,xy_cen=True))
