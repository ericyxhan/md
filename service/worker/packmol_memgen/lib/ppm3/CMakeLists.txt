project(immers Fortran)

add_compile_options(${OPT_FFLAGS})

# Build the executable
add_executable(immers
       deftm.f
       find_segm.f
       hbcor.f
       locate.f
       min.f
       opm.f
       orient.f
       profile.f
       readpdb.f
       read_small.f
       rmsd.f
       solva.f
       tilting.f
       watface.f)

# Installation directive
install (TARGETS immers DESTINATION ${BINDIR})
