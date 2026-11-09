      subroutine read_small (nat,xyz,solv,numres,namsu,
     *   iprint,namat,namres,nres,ifirst,ilast)
c     -------------------------------------------------
c     Read atoms of a samll molecule in PDB formate; define their
c     ASA and solvation, charge and ionization parameters
c
c     Input formate for dipoles and pKa in small molecule PDB files
c     is slightly different from that in library of amino acid
c     residues (res.lib): there are residue niumbers, but no sign
c     of charge (charge2) here.
c
c                              Approximations
c                              --------------
c     No smoothening for dipole moments and charges partially buried from
c     water (asaref_cut=0.5A). This is questionable for large molecules 
c     that can be folded. Charges of hydrophobic ions with fully inaccessibled
c     central charged atoms should be assigned to accesible nonpolar atoms!
c
c            Modifications of PDB formate:
c     1. pKa and group dipole moments in the beginning of the file
c        as REMARK PKA or REMARK DIP
c        isig_pka =  -1 - the group is charged at pH > pK (e.g. D,E)
c                     1 - the group is charged at pH < pK (e.g. H,K,R), 
c                         sign of the charge does not matter
c        Born and ionization contributions are divided between non-
c        hydrogen atoms of ionizable groups as defined by 'part_pka'
c     2. All hydrogens must be included to identify types of C, N, O
c        (sp2 carbons are carbons with three covalent neighbors)
c
c     Ionic radii are equal to the corresponding atomic radii
c
c     Defunct parameters:
c     namsu,namres,
c
c     Atom types:
c     1  - C sp3 1.88*
c     2  - C sp2 1.76*
c     3  - NH    1.64*
c     4  - N     1.64*
c     5  - OH    1.46*
c     6  - O     1.42*
c     7  - S     1.77*
c     8  - Cpol  1.88*
c     9  - COO-
c    10  - Nh3+
c    11  - C sp1 1.75**
c    12  - N(CN) 1.61**
c    13  - F     1.44**
c    14  - Cl    1.74**
c    15  - Br    1.85**
c    16  - I     2.00**
c    17  - N and O of  NO2 group
c     *vdW radii from Tsai et al. (JMB 290, 253-256)
c     ** vdW radii from Rowland and Taylor (J.Phys.Chem. 100, 7384-7391)
c
      parameter (maxat=200000,maxlen=65,maxres=30000,
     * nsolv=16,maxpka=50,maxdip=100)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      data zslice/0.05/,probe/1.4/,asaref_cut/14./
      real xyz(3,1),xyzs(maxat,3),rads(maxat),solv(1),
     *  rad_asa(17)/1.88,1.76,1.64,1.64,1.46,1.42,1.77,1.88,1.42,1.64,
     *  1.75,1.61,1.44,1.74,1.85,2.00,1.53/,
     *  ASP_lip(17)/-0.022,-0.019,0.053,0.053,0.057,0.057,0.010,
     *   -0.022,0.129,0.118,-0.002,0.008,-0.007,-0.010,-0.012,
     *   -0.012,0.016/,
c     hydrophobicities of atom types 11 to 17 in ASP-lip are overestimated
c     because the sigmas are taken after subtraction of the dipolar energy
c
     * dipole(maxdip),part_pka(maxpka),pka(maxpka)
      character*80 line
      character*1 namu,namsu(1)
      character*4 atnam,resnam,namat(1),namres(1),
     * name_pka(maxpka),name_dip(maxdip)
c
      integer numres(1),ifirst(1),ilast(1),
     *  idon(maxat),ibb(maxat),
     *  numres_pka(maxpka),numres_dip(maxdip),isig_pka(maxpka)
c
c     1. Read information about charged groups and dipoles
c     and atomic coordinates
c
      namu=' '
      m=0
      npka=0
      ndip=0
      do i=1,200000
         read (21,'(a)',end=10) line
         if(line(1:10).eq.'REMARK PKA') then
            npka=npka+1
            read (line,'(11x,a4,i3,2f6.2,i3)') 
     *        name_pka(npka),numres_pka(npka),
     *        part_pka(npka),pka(npka),isig_pka(npka)
         end if
c
         if(line(1:10).eq.'REMARK DIP') then
            ndip=ndip+1
            read (line,'(11x,a4,i3,f6.2)') 
     *        name_dip(ndip),numres_dip(ndip),dipole(ndip)
         end if
c
         if(line(1:4).eq.'ATOM') then
            m=m+1
            if(m.gt.maxat) then
               write (*,'(''Too many atoms in PDB file'')') 
               stop
            end if
            read (line,'(13x,a4,5x,i4,4x,3f8.3)') 
     *        namat(m),numres(m),(xyz(k,m),k=1,3)
         end if
      end do
   10 continue
      nat=m
c
c     2. Define types of atoms using numbers of neighbor atoms
c     nbr    - total number of neighbor atoms
c     nbrpol - number of neighbor polar (N and O) atoms
c     nbrh   - number of neighbor hydrogens
c
      do i=1,nat
c
c        define numbers of neighbors for atom i
c
         nbr=0
         nbrpol=0
         nbrh=0
         do j=1,nat
            if(j.ne.i) then
               a=xyz(1,i)-xyz(1,j)
               b=xyz(2,i)-xyz(2,j)
               c=xyz(3,i)-xyz(3,j)
               dist=sqrt(a*a+b*b+c*c)
               if(dist.le.1.8) then
                  nbr=nbr+1
c                 write (*,'(2a5)') namat(i),namat(j)
                  if(namat(j)(1:1).eq.'N'.or.
     *               namat(j)(1:1).eq.'O') nbrpol=nbrpol+1
                  if(namat(j)(1:1).eq.'H') nbrh=nbrh+1
               end if
            end if
         end do
c
         if(nbr.eq.0) then
            write (*,'(''no neighbors for atom '',a4,i5)') namat(i),i
            stop
         end if
         iat(i)=0
         if(namat(i)(1:1).eq.'C') then
            if(nbr.eq.4) iat(i)=1
            if(nbr.eq.3) iat(i)=2
            if(nbr.eq.2) iat(i)=11
            if(iat(i).eq.1.and.nbrpol.ge.1) iat(i)=8
            if(nbr.le.1) then
               write (*,'(''less than 2 neighbors for atom'',
     *          a4,i5)') namat(i),i
               stop
            end if
         end if
         if(namat(i)(1:1).eq.'F') iat(i)=13
         if(namat(i)(1:2).eq.'Cl') iat(i)=14
         if(namat(i)(1:2).eq.'Br') iat(i)=15
         if(namat(i)(1:1).eq.'I') iat(i)=16
         if(namat(i)(1:1).eq.'N') then
            iat(i)=4
            if(nbr.le.0) then
               write (*,'(''zero neighbors for atom'',
     *          a4,i5)') namat(i),i
               stop
            end if
            if(nbrh.ge.1) iat(i)=3
            if(nbr.eq.1) iat(i)=12
            if(nbrpol.ge.1) iat(i)=17
         end if
         if(namat(i)(1:1).eq.'O') then
            iat(i)=6
            if(nbrh.ge.1) iat(i)=5
            if(nbrpol.ge.1) iat(i)=17
         end if
         if(namat(i)(1:1).eq.'S') iat(i)=7
         if(namat(i)(1:1).eq.'H') iat(i)=21
c        write (*,'(a1,i5)') namat(i)(1:1),nbr
         if(iat(i).eq.0) then
            write (*,'(''atom type undefined:'',
     *       a4,i5)') namat(i),i
            stop
         end if
      end do
c
c     3. Exclude hydrogens and define atomc radii
c
      m=0
      do i=1,nat
         ia=iat(i)
         if(ia.ne.21) then
            m=m+1
            namat(m)=namat(i)
            do j=1,3
               xyz(j,m)=xyz(j,i)
            end do
            numres(m)=numres(i)
            rads(m)=rad_asa(iat(i))
            iat(m)=iat(i)
            charge2(m)=0.
         end if
      end do
      nat=m
c
      ph=7.5
      temp=293.
      rt=(8.314*0.239/1000.)*temp
c
c     4. Assign pKa-related parameters and group dipole moments
c
      do i=1,nat
         namsu(i)=' '
         dip(i)=0.
         charge(i)=0.
         eioniz(i)=0.
         asaref(i)=0.
         ibb(i)=1
         idon(i)=0
         hbond(i)=0.
         solv(i)=ASP_lip(iat(i))
         do j=1,ndip
            if(namat(i).eq.name_dip(j).and.
     *        numres(i).eq.numres_dip(j)) then
               dip(i)=dipole(j)
               asaref(i)=asaref_cut
            end if
         end do
         do j=1,npka
            if(namat(i).eq.name_pka(j).and.
     *        numres(i).eq.numres_pka(j)) then
               asaref(i)=asaref_cut
               if(iat(i).eq.3.or.iat(i).eq.4) iat(i)=10
               if(iat(i).eq.5.or.iat(i).eq.6) iat(i)=9
               echarge=0.
               if((isig_pka(j).eq.-1.and.pka(j).lt.ph).or.
     *           (isig_pka(j).eq.1.and.pka(j).gt.ph))
     *            echarge=rt*alog(10.)*abs(ph-pka(j))
               eioniz(i)=part_pka(j)*echarge
               if(echarge.ne.0.) charge(i)=166.*part_pka(j)/rads(i)
            end if
         end do
      end do
c
c     5. Calculate ASA
c
      nats=nat
      do i=1,nat
         do j=1,3
            xyzs(i,j)=xyz(j,i)
         end do
      end do
      call solva (nats,xyzs,rads,accs,probe,zslice)
      do i=1,nat
         if(accs(i).lt.0.02) accs(i)=0.
      end do
c
c     6. Define borders of residues:
c     The list of residues is continuous and it can include
c     several PDB subunits
c
      m=1
      ifirst(1)=1
      do i=2,nat
         if(numres(i).ne.numres(i-1).or.
     *     namsu(i).ne.namsu(i-1)) then
            m=m+1
            if(m.gt.maxres) then
               write (*,'(''Too many residues'')')
               stop
            end if
            ifirst(m)=i
         end if
      end do 
      nres=m
      do i=1,nres-1
         ilast(i)=ifirst(i+1)-1
      end do
      ilast(nres)=nat
c
      if(iprint.ge.2) then
         write (*,'(''read_small:'')')
         do i=1,nat
            write(*,'(i4,1x,a4,i4,3f8.3,f5.2,f5.1,3f8.3,
     *        f5.0,i2,f4.1)')
     *        numres(i),namat(i),iat(i),(xyz(j,i),j=1,3),
     *        rads(i),accs(i),dip(i),charge(i),eioniz(i),asaref(i),
     *        idon(i),hbond(i)
         end do
      end if
      return
      end 
