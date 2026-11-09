#!/usr/bin/python
"""Convert AMBER lipid naming conventions to CHARMM format in PDB files.

Inverse of charmmlipid2amber: processes PDB files by substituting AMBER
(Lipid14/Lipid21) style atom and residue names with their CHARMM equivalents
using the charmmlipid2amber CSV dictionary in reverse. Only ATOM, HETATM,
and TER lines are processed; all other PDB records are removed.

Identification of each lipid molecule uses the complete set of AMBER atom
keys (columns 13-21) present in a residue, which is unique for all 72
supported lipid types. Atom-level substitution uses position-ordered lookup
from the CSV, allowing correct disambiguation of lipids with two identical
acyl chains (e.g., DOPC, DPPE) where the same AMBER atom name appears twice.

Requires all atoms of each lipid molecule to share the same residue sequence
number (as produced by charmmlipid2amber.py) and to be listed in the original
AMBER output order.

Usage (standalone):
    amberlipid2charmm.py [-c charmmlipid2amber.csv] -i input.pdb -o output.pdb
"""

import sys
import csv
import re
import getopt
import os


def amberlipid2charmm(inputpdb, outputpdb=None,
                 csv_dict=os.path.join(os.path.dirname(__file__), "charmmlipid2amber.csv")):
    """Convert AMBER lipid names to CHARMM naming in a PDB file.

    Reads the input PDB, splits it into residues (respecting chain IDs and
    TER records), and applies inverse atom/residue name substitutions from a
    CSV dictionary file. The substitution maps AMBER-style names (Lipid14/21)
    back to their CHARMM equivalents while preserving atom ordering.

    Lipid molecules are identified by the frozenset of all AMBER atom keys
    (columns 13-21) present in the residue. This is unique across all 72
    supported lipid types. Atom substitution is then performed by position
    (CSV 'order' column), which correctly handles lipids whose two acyl chains
    map to the same AMBER atom names.

    Args:
        inputpdb: Path to the input PDB file with AMBER lipid naming.
        outputpdb: Path for the output PDB file. If None, defaults to
            the input filename with '_charmm' appended before the extension.
        csv_dict: Path to the CSV substitution dictionary file. Defaults
            to 'charmmlipid2amber.csv' in the same directory as this module.
            Falls back to $AMBERHOME/dat/charmmlipid2amber/charmmlipid2amber.csv
            if the provided path is empty.

    Returns:
        The path to the output file if substitutions were made, or the
        input file path if no residues matched the substitution dictionary.
    """
    input_file_name = inputpdb
    if outputpdb is not None:
        output_file_name = outputpdb
    else:
        output_file_name = inputpdb.replace(".pdb", "_charmm.pdb")
    convert_file_name = csv_dict
    if convert_file_name == '':
        amberhome = os.getenv('AMBERHOME')
        if amberhome is None:
            print("Error: amberlipid2charmm.py AMBERHOME not set and -c is not set. "
                  "Set the AMBERHOME environment variable OR manually specify a "
                  "substitution file with -c.")
            print("Usage: amberlipid2charmm.py [-c charmmlipid2amber.csv] -i input.pdb -o output.pdb")
            sys.exit(2)
        else:
            convert_file_name = "%s/dat/charmmlipid2amber/charmmlipid2amber.csv" % amberhome
    if not os.path.isfile(convert_file_name):
        print("Error: No substitution file found. Check that AMBERHOME is set "
              "properly OR the file set with -c is correct.")
        sys.exit(1)

    try:
        input_file = open(input_file_name, 'r')
    except IOError as err:
        print("Error:", str(err))
        sys.exit(1)
    input_file_list = [line for line in input_file]
    input_file.close()

    # Split file into residues by checking columns 23-27 and chain ID.
    # Uses identical logic to charmmlipid2amber.py.
    residue_list = []
    residue_start = []
    residue_end = []
    it0 = 1
    previous_residue = ""
    current_residue = ""
    previous_chain = ""
    current_chain = ""
    if (input_file_list[0][0:6] == "ATOM  " or
            input_file_list[0][0:6] == "HETATM"):
        residue_list.append(input_file_list[0][22:28])
        residue_start.append(it0)
        previous_residue = input_file_list[0][22:28]
        previous_chain = input_file_list[0][21:22]
    elif input_file_list[0][0:3] == "TER":
        previous_residue = ""
        previous_chain = ""
    else:
        previous_residue = ""
        previous_chain = ""
    it0 += 1
    TER_trigger = False
    for line in input_file_list[1:]:
        if line[0:6] == "ATOM  " or line[0:6] == "HETATM":
            current_residue = line[22:28]
            current_chain = line[21:22]
        elif line[0:3] == "TER":
            current_residue = previous_residue
            current_chain = previous_chain
        else:
            current_residue = ""
            current_chain = ""
        if previous_residue != current_residue or previous_chain != current_chain or TER_trigger:
            if previous_residue == "" or previous_chain == "":
                residue_list.append(current_residue)
                residue_start.append(it0)
                previous_residue = current_residue
                previous_chain = current_chain
            elif current_residue == "" or current_chain == "":
                residue_end.append(it0 - 1)
                previous_residue = current_residue
                previous_chain = current_chain
            else:
                residue_list.append(current_residue)
                residue_start.append(it0)
                residue_end.append(it0 - 1)
                previous_residue = current_residue
                previous_chain = current_chain
            TER_trigger = False
        it0 += 1
        if line[0:3] == "TER":
            TER_trigger = True
    if current_residue != "":
        residue_end.append(it0 - 1)

    # Read CSV and build reverse (AMBER → CHARMM) substitution data.
    try:
        csv_file = open(convert_file_name, 'r')
    except IOError as err:
        print("Error:", str(err))
        sys.exit(1)
    csv_file.readline()  # skip version line
    csv_file_reader = csv.DictReader(csv_file)

    # Per CHARMM-residue tables built from the forward CSV:
    #   amber_key_sets: unique AMBER atom keys (columns 13-21 of 'replace')
    #                   → used to identify the lipid type via frozenset match
    #   ordered_triples: list of (order, amber_key, charmm_key) tuples
    #                    → sorted by 'order' to give position-indexed lookup
    #   ter_needed:     whether a TER card should follow the residue
    #   num_atom:       expected number of ATOM/HETATM lines per residue
    amber_key_sets = {}
    ordered_triples = {}
    ter_needed = {}
    num_atom = {}

    for row in csv_file_reader:
        charmm_res = row['residue']
        amber_key = row['replace']
        charmm_key = row['search']
        order = int(row['order'])
        if charmm_res not in amber_key_sets:
            amber_key_sets[charmm_res] = set()
            ordered_triples[charmm_res] = []
            ter_needed[charmm_res] = (row['TER'] == 'True')
            num_atom[charmm_res] = int(row['num_atom'])
        amber_key_sets[charmm_res].add(amber_key)
        ordered_triples[charmm_res].append((order, amber_key, charmm_key))
    csv_file.close()

    # Build position-indexed map: charmm_res → {position: (amber_key, charmm_key)}
    # 'position' is the 0-based index among ATOM/HETATM lines within the residue.
    position_maps = {}
    for charmm_res, triples in ordered_triples.items():
        triples.sort(key=lambda x: x[0])
        position_maps[charmm_res] = [(t[1], t[2]) for t in triples]

    # Build frozenset(unique AMBER keys) → CHARMM residue name lookup.
    # This is unique for all 72 supported lipid types.
    frozenset_to_charmm = {
        frozenset(keys): charmm_res
        for charmm_res, keys in amber_key_sets.items()
    }

    # Do substitutions
    output_file_list = []
    residue_substituted = False
    for it1 in range(len(residue_list)):
        input_residue = input_file_list[residue_start[it1] - 1: residue_end[it1]]
        output_residue = []

        # Collect AMBER atom keys from all ATOM/HETATM lines
        amber_atom_keys = [line[12:21] for line in input_residue if line[0:3] != "TER"]
        charmm_res = frozenset_to_charmm.get(frozenset(amber_atom_keys))

        if charmm_res is not None:
            residue_substituted = True
            n_TER_cards = sum(1 for line in input_residue if line[0:3] == "TER")
            if len(input_residue) - n_TER_cards != num_atom[charmm_res]:
                print("Error: Number of atoms in residue does not match number of "
                      "atoms in residue in replacement data file")
                print(input_residue, num_atom[charmm_res])
                sys.exit(1)

            pos_map = position_maps[charmm_res]
            atom_index = 0
            for line in input_residue:
                if line[0:3] != "TER":
                    expected_amber_key, charmm_key = pos_map[atom_index]
                    actual_amber_key = line[12:21]
                    if actual_amber_key != expected_amber_key:
                        print("Warning: amberlipid2charmm: %s atom %d: "
                              "expected AMBER key %r, found %r. "
                              "Atoms may be out of order." %
                              (charmm_res, atom_index,
                               expected_amber_key, actual_amber_key))
                    # Replace columns 13-21 (0-based 12:21) with CHARMM key
                    output_residue.append(line[:12] + charmm_key + line[21:])
                    atom_index += 1
                else:
                    output_residue.append("TER   \n")
            if ter_needed[charmm_res]:
                if not output_residue or output_residue[-1][0:3] != "TER":
                    output_residue.append("TER   \n")
        else:
            output_residue = input_residue

        output_file_list.extend(output_residue)

    if not residue_substituted:
        print("No residues substituted by amberlipid2charmm")
        return input_file_name

    # Write output
    try:
        output_file = open(output_file_name, 'w')
    except IOError as err:
        print("Error:", str(err))
        sys.exit(1)
    output_file.write("REMARK   Packmol generated pdb file, Packmol Memgen estimated parameters\n")
    output_file.write("REMARK   amberlipid2charmm.py transformed file\n")
    for line in output_file_list:
        output_file.write(line)
    output_file.write("END   \n")
    output_file.close()
    return output_file_name


if __name__ == '__main__':
    input_file_name = ''
    output_file_name = ''
    convert_file_name = ''
    try:
        myopts, args = getopt.getopt(sys.argv[1:], "i:o:c:")
    except getopt.GetoptError as err:
        print("Error:", str(err))
        print("Usage: amberlipid2charmm.py [-c charmmlipid2amber.csv] -i input.pdb -o output.pdb")
        sys.exit(2)
    for o, a in myopts:
        if o == "-i":
            input_file_name = a
        elif o == "-o":
            output_file_name = a
        elif o == "-c":
            convert_file_name = a
        else:
            print("Usage: amberlipid2charmm.py [-c charmmlipid2amber.csv] -i input.pdb -o output.pdb")
            sys.exit(0)
    if input_file_name == '' or output_file_name == '':
        print("Usage: amberlipid2charmm.py [-c charmmlipid2amber.csv] -i input.pdb -o output.pdb")
        sys.exit(2)
    amberlipid2charmm(input_file_name, outputpdb=output_file_name,
                 csv_dict=os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                                       "charmmlipid2amber.csv"))
