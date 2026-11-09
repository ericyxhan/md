      subroutine readpdb (nat,xyz,solv,numres,namsu,iprint,namat,
     *  namres,nres,ifirst,ilast,ihetero,nmembr,linesub)
c     -----------------------------------------------------------
c     Read atoms from PDB file as a continuous list; define their
c     ASA, solvation parameters, and residue IDs; and prepare
c     list of CA atoms of secondary structures
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
     * nsolv=26,max_at=60,max_res=80)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      data zslice/0.05/,probe/1.4/,asaref_cut/14./
      real xyz(3,1),xyzs(maxat,3),rads(maxat),
     *  solv(1),
     *  rad_asa(17)/1.88,1.76,1.64,1.64,1.46,1.42,1.77,1.88,1.42,1.64,
     *  1.75,1.61,1.44,1.74,1.85,2.00,1.53/,
     *  ASP_lip(17)/-0.022,-0.019,0.053,0.053,0.057,0.057,0.010,
     *   -0.022,0.129,0.118,-0.002,0.008,-0.007,-0.010,-0.012,
     *   -0.012,0.016/
c     hydrophobicities of atom types 11 to 17 in ASP-lip are overestimated
c     because the sigmas are taken after subtraction of the dipolar energy
c
      character*80 line,reslib
      character*1 namsu(1)
      character*4 namat(1),namres(1),namsolv(nsolv)/
     * 'HOH ','DOD ','LDA ','BNG ','BGL ','BHG ','CE1 ','LMT ',
     * 'LDM ','F09 ','SO4 ','C8E ','HTG ','HTO ','BOG ','GOL ',
     * 'NAG ','K   ','MOH ',' CA ','CA  ',' CL ',' NI ',' ZN ',
     * ' NA ',' CS '/
c
      integer numres(1),ifirst(1),ilast(1),idon(maxat),ibb(maxat)
c
      real dip_at(max_res,max_at),pka(max_res,max_at),
     *  part_pka(max_res,max_at),charge_at(max_res,max_at)
      integer kndat(max_res,max_at),natres(max_res),ndip(max_res),
     * npka(max_res),isig_pka(max_res,max_at)
      character*4 name_res(max_res),name_at(max_res,max_at),
     *  name_dip(max_res,max_at),name_pka(max_res,max_at) 
      character*300 linesub
c
      ph=7.5
      temp=293.
      rt=(8.314*0.239/1000.)*temp
c
c     Read libary of residues
c
      reslib(1:7)='res.lib'
      call read_res (reslib,ndict,name_res,natres,name_at,kndat,ndip,
     *  name_dip,dip_at,npka,name_pka,pka,part_pka,isig_pka,charge_at)
c
      if(ndict.eq.0) then
         write (*,'(''Place library of aa residues in''
     *    '' current directory'')')
         stop
      end if
c
c     Output of residue library:
c
c     do i=1,ndict
c        write (*,'(a4,i4)') name_res(i),natres(i)
c        if(ndip(i).gt.0) then
c           do j=1,ndip(i)
c              write (*,'(a4,f6.2)') name_dip(i,j),dip_at(i,j)
c           end do
c        end if
c        if(npka(i).gt.0) then
c           do j=1,npka(i)
c              write (*,'(a4,2f6.2,i3,f6.2)') name_pka(i,j),pka(i,j),
c    *           part_pka(i,j),isig_pka(i,j),charge_at(i,j) 
c           end do
c        end if
c        do j=1,natres(i)
c           write (*,'(a4,i2)') name_at(i,j),kndat(i,j) 
c        end do
c     end do
c
c     Read PDB file 
c
      nat=0
      do i=1,999999
         read (21,'(a)',end=50) line
c
c        select 1st NMR model:
c
         if(nmembr.eq.0) then
            if(line(1:6).eq.'ENDMDL'.or.line(18:20).eq.'DUM') go to 50
         else
            if(line(1:6).eq.'ENDMDL') go to 50
            if(line(1:4).eq.'ATOM'.or.line(1:6).eq.'HETATM') then
               lsub=index(linesub,' ')
               nsub=lsub/2
               do j=1,nsub
                  jj=2*j-1
                  if(line(22:22).eq.linesub(jj:jj)) go to 10
               end do
c              write (*,'(a80)') line
               go to 40
            end if
         end if
   10    continue
c
         if(line(1:4).ne.'ATOM'.and.line(1:6).ne.'HETATM') go to 40
c        if(line(1:6).eq.'HETATM'.and.ihetero.eq.0) go to 40
         if(line(14:14).eq.'H'.or.line(14:14).eq.'D'.or.
     *     line(13:13).eq.'H'.or.line(14:14).eq.'Q') go to 40
c
c        crystal disorder: select structure A
c
         if(line(17:17).ne.' '.and.line(17:17).ne.'A') go to 40
         if(line(17:17).ne.' ') line(17:17)=' '
c
c        exclude solvents, detergents and precipitants
c        included in list 'namsolv':
c
         do i1=1,nsolv
            if(line(18:21).eq.namsolv(i1)) go to 40
         end do
c
         nat=nat+1
         if(nat.gt.maxat) then
            write (*,'(''Too many atoms in PDB file'')') 
            stop
         end if
         read (line,'(13x,2a4,a1,i4,4x,3f8.3)') namat(nat),
     *     namres(nat),namsu(nat),numres(nat),(xyz(k,nat),k=1,3)
c        write (*,'(13x,2a4,a1,i4,4x,3f8.3)') namat(nat),
c    *     namres(nat),namsu(nat),numres(nat),(xyz(k,nat),k=1,3)
         asaref(nat)=0.
         dip(nat)=0.
         charge(nat)=0.
         eioniz(nat)=0.
         charge2(nat)=0.
         ibb(nat)=0
c
c        Find residue from library for this atom:
c
         do l=1,ndict
            if(name_res(l)(1:3).eq.line(18:20)) then
               ires=l
c
c              Find atom for this residue in the library and
c              assign its type
c
               do j=1,natres(ires)
                  if(name_at(ires,j).eq.namat(nat)) then
                     iatom=kndat(ires,j)
                     go to 20
                  end if
               end do
c
c              non-standard atoms (e.g. OXT) of residues found in the library
c              are treated as hetero-atoms, but always included:
c
               if(namat(nat).ne.'OXT ') write(*,
     *           '(''atom not in library: '',a4,1x,a1,1x,a4,i5)')
     *           namat(nat),namsu(nat),namres(nat),numres(nat)
            end if
         end do
c
c        Residue not found (some heterogroups can be marked as "ATOM'
c        in PDB files generated by QUANTA)
c
         if(ihetero.eq.0) then
c           write (*,'(''Excluded: '',a60)') line(1:60)
            nat=nat-1
            go to 40
         end if
c        write (*,'(''Not in the library of aa residues: '',a40)') 
c    *     line(1:40)
c
c        Assign atom types, dioples and other parameters to heteroatoms
c        not in the library. Ionizable greoups are not defined as such.
c        Heteroatoms with 1st characters other than N,S,C,O
c        are defined as OH
c
         iatom=5
         if(namat(nat)(1:1).eq.'C') iatom=1
         if(namat(nat)(1:1).eq.'N') iatom=3
         if(namat(nat)(1:1).eq.'O') iatom=6
         if(namat(nat)(1:1).eq.'S') iatom=7
         if(namat(nat)(1:1).eq.'F') iatom=13
         if(namat(nat)(1:2).eq.'Cl') iatom=14
         if(namat(nat)(1:2).eq.'Br') iatom=15
         if(namat(nat)(1:1).eq.'I') iatom=16
         if(iatom.gt.2) then
c           (we do not have types 8,9,10 here)
            dip(nat)=1.4
            asaref(nat)=asaref_cut
            if(namat(nat).eq.'O   ') dip(nat)=2.3
            if(namat(nat).eq.'OXT ') then
               dip(nat)=2.3
               eioniz(nat)=6.3
               charge(nat)=65.0
            end if
         end if
         iat(nat)=iatom
         rads(nat)=rad_asa(iatom)
         go to 30
c
   20    continue
c
c        atom of amino acid residue was found in the library:
c
         iat(nat)=iatom
         rads(nat)=rad_asa(iatom)
c
c        Looking for dipoles
c
         if(ndip(ires).gt.0) then
            do j=1,ndip(ires)
               if(name_dip(ires,j).eq.namat(nat)) then
                  dip(nat)=dip_at(ires,j)
                  asaref(nat)=asaref_cut
               end if
            end do
         end if
c
c        Looking for ionizable groups (all charged groups are
c        assumed to be ionizable here)
c
         if(npka(ires).gt.0) then
            do j=1,npka(ires)
               if(name_pka(ires,j).eq.namat(nat)) then
                  echarge=0.
                  if((isig_pka(ires,j).eq.-1.and.pka(ires,j).lt.ph).or.
     *              (isig_pka(ires,j).eq.1.and.pka(ires,j).gt.ph))
     *               echarge=2.3*rt*abs(ph-pka(ires,j))
                  eioniz(nat)=part_pka(ires,j)*echarge
                  if(echarge.ne.0.) charge(nat)=
     *              166.*part_pka(ires,j)/rads(nat)
                  charge2(nat)=charge_at(ires,j)
                  asaref(nat)=asaref_cut
               end if
            end do
         end if
c
   30    continue
         if(namat(nat).eq.'O   '.or.namat(nat).eq.'N   '.or.
     *      namat(nat).eq.'C   '.or.namat(nat).eq.'CA  ') ibb(nat)=1
c
c        exclude all H-bonds except those formed by side-chains of S,T,Y
c
         if(namres(nat).ne.'SER '.and.namres(nat).ne.'THR ') ibb(nat)=1
c
         solv(nat)=ASP_lip(iat(nat))
c
   40    continue
      end do
   50 continue
c
c     2. Calculate ASA
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
c     Define borders of residues:
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
      if(nres.gt.1) then
         do i=1,nres-1
            ilast(i)=ifirst(i+1)-1
         end do
      end if
      ilast(nres)=nat
c
c     Identification of H-bonds and correctiong charges of atoms in
c     ionizable residues involved in ion pairs
c
      do i=1,nat
         idon(i)=0
c
c        assume that COO can be an H-bond donor in uncharged state
c
         if(iat(i).eq.3.or.iat(i).eq.10) idon(i)=1
         if(iat(i).eq.4.or.iat(i).eq.6) idon(i)=2
         if(iat(i).eq.5.or.iat(i).eq.9) idon(i)=3
      end do
c
      call hbcor(nat,xyz,idon,nres,ifirst,ilast,ibb)
c
      if(iprint.ge.2) then
         write (*,'(''readpdb:'')')
         do i=1,nat
c           write(*,'(a4,i4,1x,a4,i4,3f8.3,f5.2,f5.1,3f8.3,
c    *        f5.0,i2,f4.1)') 
c    *        namres(i),numres(i),namat(i),iat(i),(xyz(j,i),j=1,3),
c    *        rads(i),accs(i),dip(i),charge(i),eioniz(i),asaref(i),
c    *        idon(i),hbond(i)
            write(*,'(a4,i4,1x,a4,i4,3f8.3,f5.2,f5.1,
     *        f5.0,i2,f4.1,f7.3)')
     *        namres(i),numres(i),namat(i),iat(i),(xyz(j,i),j=1,3),
     *        rads(i),accs(i),asaref(i),idon(i),hbond(i),solv(i)

         end do
         ica=0  
      end if
      return
      end 
c
      subroutine read_res (reslib,ndict,namres,natres,namat,kndat,ndip,
     *  name_dip,dip,npka,name_pka,pka,part_pka,isig_pka,charge)
c     ----------------------------------------------------------------
c     read library of amino acid residues
c
      parameter (max_res=80)
c
      character*80 reslib,line
      real dip(max_res,1),pka(max_res,1),part_pka(max_res,1),
     *  charge(max_res,1)
      integer kndat(max_res,1),natres(1),ndip(1),npka(1),
     * isig_pka(max_res,1)
      character*4 namres(1),namat(max_res,1),name_dip(max_res,1),
     *  name_pka(max_res,1) 
c
      open (2,file='res.lib')
      ndict=0
      do i=1,200000
         read (2,'(a)',end=20) line
c
         if(line(1:4).eq.'RES ') then
            ndict=ndict+1
            namres(ndict)=line(5:8)
            natres(ndict)=0
            ndip(ndict)=0
            npka(ndict)=0
            if(ndict.gt.max_res) then
               write (*,'(''Too many residues in residue library'')') 
               stop
            end if
            go to 10
         end if
c
         if(line(1:4).eq.'DIP ') then
            ndip(ndict)=ndip(ndict)+1
            read (line,'(4x,a4,f6.2)') name_dip(ndict,ndip(ndict)),
     *        dip(ndict,ndip(ndict))
            go to 10
         end if
c
         if(line(1:4).eq.'PKA ') then
            npka(ndict)=npka(ndict)+1
            read (line,'(4x,a4,f5.2,f6.2,i3,f6.2)') 
     *        name_pka(ndict,npka(ndict)),part_pka(ndict,npka(ndict)),
     *        pka(ndict,npka(ndict)),isig_pka(ndict,npka(ndict)),
     *        charge(ndict,npka(ndict)) 
            go to 10
         end if
c
         natres(ndict)=natres(ndict)+1
         read (line,'(a4,i2)') namat(ndict,natres(ndict)),
     *     kndat(ndict,natres(ndict))
   10    continue
      end do
   20 continue
      close(2)
      return
      end
