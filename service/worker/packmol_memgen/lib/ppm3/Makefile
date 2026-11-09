#
# Makefile for MAIN
#
FC=gfortran
OBJS = opm.o min.o rmsd.o solva.o readpdb.o read_small.o watface.o \
	 tilting.o locate.o profile.o hbcor.o deftm.o orient.o find_segm.o

all: immers

immers: $(OBJS)
	 $(FC) -O -g -o $@ $^

.PHONY: clean

clean:
	rm *.o immers
