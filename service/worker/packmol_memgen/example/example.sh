#!/bin/bash
#
#PACKMOL MEMGEN EXAMPLE
#
#This example run is for the Streptomyces Potassium Channel KcsA. This will protonate
#and orientate the protein, and prepare a membrane system with a DOPE:DOPG mixture 3:1.

if [[ $1 = "clean" ]]; then
cd $(dirname $0)
#rm $(ls -I example.sh)
find . \! -name "example.sh" -type f -delete
exit
fi

SCRIPT_PATH=../../packmol-memgen

PDB=1BL8

if [[ ! -f ${PDB}.cif ]]; then
    echo "DOWNLOADING PDB FILE..."
    wget https://files.rcsb.org/download/${PDB}.cif
fi

echo "RUNNING PACKMOL_MEMGEN..."

if [[ $1 = "test" ]]; then
$SCRIPT_PATH --pdb ${PDB}.cif --lipids DOPE:DOPG --ratio 3:1 --salt_c K+ --keep --nloop 2 --nloop_all 2 --plot --mem_opt 2 --writeout 2
exit
fi

if [ ! -z "$AMBERHOME" ]
then
echo "AMBERHOME found. Parametrizing and minimizing."
$SCRIPT_PATH --pdb ${PDB}.cif --lipids DOPE:DOPG --ratio 3:1 --salt_c K+ --plot --parametrize --minimize
else
$SCRIPT_PATH --pdb ${PDB}.cif --lipids DOPE:DOPG --ratio 3:1 --salt_c K+ --plot 
fi
