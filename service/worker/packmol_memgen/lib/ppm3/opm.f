c                *** opm.f ***
c     Universal version with  new solvation model (transmemberane or
c     peripheral proteins and small molecules)
c
c     Modules: solva.f, min.f, rmsd.f, deftm.f, hbcor.f, profile.f,
c     read_small.f, watface.f, find_segm.f, locate.f, orient.f, readpdb.f,
c     tilting.f
c
c                       Method comments
c                       ---------------
c         The initial orientation is automatically determined by the method of
c         Tusnady. This is done with modified old energy functions (ionizable
c         groups are treated using ASA-based model) in 'orient' module with 
c         recangular rather than sigmoidal boundary. Then, the initial
c         TM secondary stuctures are automatically calculated.
c
c         The "small molecule" option is defined by record "Small molecule" in
c         PDB file. Small molecules should be prepared with hydrogens 
c         and additional information about dipole moments and pKa assigned to
c         specific groups (see comments in read_small.f). They currently
c         include only C,N,O,S atoms.
c
c                     Treatment of heteroatoms
c                     -------------------------
c      1. Solvent molecules ('namsolv' list) are always excluded from 
c         the calculations but re-included in the final coordinate file.
c      2. Cofactors (everything not in residue library) are excluded
c         if ihetero=0 but re-included in final coordinate file. 
c         List of residues 'namwork' serves only to define what is treated
c         heteroi-groups in output PDB file (out.pdb)
c      3. Cofactors are treated as amino acid residues (based on their 
c         residue numbers. Heteroatoms with C,O,N,S in 1st position are 
c         treated as Csp2, OH, NH, and S, respectively. Others are
c         assigned as OH. No electrostatic contributions for charged
c         heteroatoms. Cofactors must be included in the library of
c         residues. More atom types should be added (esp. for ions).
c
c                 Conventions and approximations
c                 ------------------------------
c      1. Some residues in PDB files are incomplete, which leads
c         to omitting contributions of their polar atoms, dipoles, and 
c         ionizable groups. Ideally, they must be reconstructed.
c      2. Electrostatic contributions for dipoles and charged groups are 
c         equally divided between participating atoms. Dipole moments
c         are taken for unionized states. Choice of ionized or unionized
c         state (whichever was of lower energy), rtaher than considering
c         the ionized-unionized equiliblium. No smoothening for ionization
c         energy (eioniz).
c      3. H-bonds are used only for OH groups of S,T and Y. They are 
c         identified as in Quanta (<3.5 A distance and bond angles >90 degrees).
c      4. Topology is defined for N-nerminus of 1st subunit in PDB file
c
      character*80 pdbtempl,line,title,ssfile,ssout,pdbout,pdbinp
      character*3 itopo,sysinp,yesno
      character*6 curvature
      character*300 linesub
      character*1 num_membr(9)/'1','2','3','4','5','6','7','8','9'/
c
      open (23,file='datasub1')
      open (24,file='datapar1')
      open (25,file='datapar2')
c
c     ihetero= 0 - all hetero-groups are excluded
c              1 - all hetero-groups are included except ones
c                  defined as solvent
c
c     model  = 1 - peripheral protein with fixed membrane thickness of 30 A
c              2 - TM protein with variable membrane thickness
c                  (hydrophobic  matching condition depends on type of
c                  sec. structure)
c              3 - peripheral protein (no secondary structure) with variable
c                  membrane thickness (matching condition for alpha-hel. protein)
c
c     ifunc  = 1 - old energy functions with simplified (ASA-dependent) 
c                  energy for ionizable groups and sigmoidal polarity profile
c                  Old functions are used for initial calculation of transmembrane
c                  domain and transfer energy contributions Rfor individual secondary
c                  structures
c              2 - new energy functions
c
      linesub='A'
      nmembr=0
      iprint=1
      read (*,'(i1)') inptype
      do ipdb=1,999999
         if(inptype.eq.2) then
            read (*,'(a3)',end=50) yesno
            if(yesno.eq.'no') then
               ihetero=0
            else 
               ihetero=1
            end if
            read (*,'(a80)') pdbtempl
         else
            read (*,'(i2,1x,2(a3,1x),a80)',end=50) 
     *        ihetero,sysinp,itopo,pdbtempl
            write (*,'(a80)') pdbtempl
         end if
         call biounit (pdbtempl)
c
         j00=index(pdbtempl,'.pdb')-1
         if(j00.le.2) then
            write (*,'(''wrong name of PDB file:'',a50)') pdbtempl
            stop
         end if
c
         if(inptype.eq.2) then
            read (*,'(i1)') nmembrane  
            if(nmembrane.gt.4) then
               write (*,'(''Too many membranes'')') 
               stop
            end if
            nmembr=nmembrane
            do i=1,nmembrane
               read (*,'(a3)') sysinp
               read (*,'(a6)') curvature
               if(curvature.eq.'planar') then
                  icurve=0
               else 
                  icurve=1
               end if
               read (*,'(a3)') itopo
               read (*,'(a)') linesub 
               if(linesub(1:4).eq.'    ') nmembr=0
               if(i.eq.1) then
                  pdbinp=pdbtempl
               else
                  pdbinp=pdbout
               end if
               if(i.eq.nmembrane) then
                  j00=index(pdbtempl,'.pdb')-1
                  pdbout=pdbtempl(1:j00)//'out.pdb'
               else
                  j00=index(pdbtempl,'.pdb')-1
                  pdbout=pdbtempl(1:j00)//'out'//num_membr(i)//'.pdb'
               end if
               write (*,'(i3,1x,2a)') i, pdbinp(1:20),pdbout(1:20)
               write (*,'(i2,1x,2(a3,1x),a80)') 
     *           ihetero,sysinp,itopo,pdbtempl
               call immers (pdbinp,iprint,ihetero,itopo,sysinp,pdbout,
     *           nmembr,linesub,icurve)
            end do
            go to 40
         end if
c         
         icurve=1
c
         pdbout=pdbtempl(1:j00)//'out.pdb'
c
         if(ihetero.eq.1) then
            write (*,'(''heteroatoms included'')')
         else
            write (*,'(''heteroatoms excluded'')')
         end if
c
c        2. Calculate position of the protein
c      
         call immers (pdbtempl,iprint,ihetero,itopo,sysinp,pdbout,
     *     nmembr,linesub,icurve)
c
   40    continue
      end do
   50 continue
      stop
      end
c
      subroutine immers (pdbtempl,iprint,ihetero,itopo,sysinp,pdbout,
     *  nmembr,linesub,icurve)
c     --------------------------------------------------------------
c     Calculate membrane immersion parameters of a 3D structure
c     given its subunits, borders of each subunit, and
c     its secondary structures (SS)
c
      parameter (maxat=200000,maxres=30000,maxlen=65,
     * maxsegm=900,maxsub=95)
c
c**   'maxat' must be the same as 'maxs' in solva.f !
c
      character*80 pdbtempl,pdbout,line
      character*1 namsu(maxat),namsegm(maxsegm),namesu(maxsub)
      character*4 namat(maxat),namres(maxat)
      character*3 itopo,sysinp,sysname(23)/'PMm','PMp','PMf','ERf',
     *  'ERm','GOL','LYS','END','VAC','MOM','MIM','THp','THb','GnO',
     *  'GnI','GpI','ARC','   ','MIC','LPC','MPC','OPC','EPC'/
      character*300 linesub
c
      integer numres(maxat),ienvat(maxat),natsegm(maxsegm),
     * ifirst(maxres),ilast(maxres),ienv(maxres),isegm(2,maxsegm)
c
      real xyz(3,maxat),solv(maxat),xyzbuf(3,20),
     *  xyzc(3,maxat),xyzca(3,maxsegm,maxlen),vcenter(3),
     *  deq(23)/32.0,2*30.6,2*28.7,30.0,30.7,30.0,30.4,22.7,
     *  28.4,30.2,30.8,23.9,30.1,30.3,30.2,30.0,38.0,
     *  21.7,25.7,28.8,35.8/,eeq(23)/9*0.02,2*0.01,2*0.02,
     *  4*0.015,0.001,0.0,4*0.02/
c
      data pi/3.14159/
c     data pi/3.14159/,emism/0.0/
c
c
      open (21,file=pdbtempl)
c
c     1. Read atoms from PDB file as a continuous list; define their
c     ASA, solvation parameters, and residue IDs; and prepare
c     list of CA atoms of all SS
c
      read (21,'(a)') line
      if(line(1:21).eq.'REMARK Small molecule') then
         model=1
         call read_small (nat,xyz,solv,numres,namsu,
     *     iprint,namat,namres,nres,ifirst,ilast)
      else
         close(21)
         open (21,file=pdbtempl)
         call readpdb (nat,xyz,solv,numres,namsu,
     *     iprint,namat,namres,nres,ifirst,ilast,ihetero,
     *           nmembr,linesub)
      end if
      nsuper=10
      if(nat.lt.10) nsuper=nat
      do i=1,nsuper
         do j=1,3
            xyzbuf(j,i)=xyz(j,i)
         end do
      end do
c
c     Read rotamer library
c
c     Side chain reconstruction and initial optimization
c     (set of atoms will be refedined)
c
c     Find optimal initial orientation and hydrophobic thickness
c     in a hydrophobic slab using method of Tusnady
c
      call orient (nat,xyz,solv,phimax,tetamax,vcenter,
     *  dmax,zcenter,emin)
c
      do i=1,nat
         xyz(1,i)=xyz(1,i)-vcenter(1)
         xyz(2,i)=xyz(2,i)-vcenter(2)
         xyz(3,i)=xyz(3,i)-vcenter(3)
      end do
      phimax=phimax*pi/180.
      tetamax=tetamax*pi/180.
      call tilting (phimax,tetamax,nat,xyz,xyzc)
      do i=1,nat
         xyz(1,i)=xyzc(1,i)
         xyz(2,i)=xyzc(2,i)
         xyz(3,i)=xyzc(3,i) - zcenter
      end do
c*    write (*,'(''Initial optimiz. in hydrocarbon slab with '',
c*   *   ''approximate energy functions:'')') 
c*    write (*,'(''emin='',f8.1,'' slab thickn.='',f8.1)') emin,dmax
      dmin=dmax
c
c     Find initial TM secondary structures if any
c
      nsegm=0
      call find_segm (nat,xyz,xyzca,numres,namat,namsu,
     *  namres,nsegm,isegm,namsegm,natsegm,dmax,itypess,0,100.)
c
      model=1
      if(nsegm.ge.1) model=2
      if(dmax.gt.18..and.nsegm.eq.0) model=3
c
      do i=1,23
         if(sysinp.eq.sysname(i)) then
            dmatch=deq(i)
            emism=eeq(i)
            go to 10
         end if
      end do
      write (*,'(''System "'',a3,''" was not found'')') sysinp
      stop
   10 continue
c
      if(model.eq.2.and.itypess.eq.2.and.sysinp.ne.'MOM'.and.
     *  sysinp.ne.'GnO') then
         dmatch=23.9
         emism=0.01
      end if
      if(sysinp.eq.'   ') then
         dmatch=30.
         if(model.eq.2.and.itypess.eq.2) then
            dmatch=23.9
         end if
      end if
c
      ica=0
      write (*,'(i5,'' possible transmembrane secondary structure''
     *  '' segments'')')  nsegm
      if(nsegm.ge.1) then
         do i=1,nsegm
            write (*,'(i4,1x,a1,2i5,i4)') i,namsegm(i),
     *        (isegm(j,i),j=1,2),natsegm(i)
c           do j=1,natsegm(i)
c              ica=ica+1
c              write (*,'(''CA '',i5,3f8.3)') ica,
c    *           (xyzca(k,i,j),k=1,3)
c           end do
         end do
      end if
c     go to 999
c
c     2. Move center of mass of CA atoms to the origin of coordinates
c
      if(model.eq.1) write (*,'(''Peripheral protein'')')
      if(model.eq.2) write (*,'(''Possible transmembrane protein,'',
     *  '' checking... '')')
      if(model.eq.3)write (*,'(''Possible transmembrane without'',
     *  '' TM secondary structure, checking...'')')
      if (model.eq.1.or.model.eq.3) then
         call bundle_axis0 (nat,namat,xyz)
      else 
         call bundle_axis (nat,xyz,xyzc,nsegm,isegm,natsegm,xyzca,
     *     iprint,numres,namsu,namat,namres)
      end if
c
c     3. Determine "water-facing" atoms and residues.  
c     ASA of water-facing atoms are nullified. Currently,
c     this is not done. 
c
      if(model.eq.1.or.model.eq.3) then
         call watface0 (nat,ienvat,nres,ienv)
      else 
         call watface (nat,xyz,numres,namsu,nres,ifirst,ilast,
     *     ienv,iprint,pdbtempl,nsegm,natsegm,xyzca,
     *     model,ienvat,namat,namres,nlipid)
         write (*,'(''N interact. lipids:'',i4)') nlipid 
      end if
c
      ifunc=2
c
c     4. Determine optimal position and hydrophobic thickness
c     immersion depth of the molecule
c
      if(sysinp.eq.'MIC') then
         icurv=1
         micdiam=38.
c        emicmin=99.
c        fmicdiam_min=99.
c        do micdiam=30,45,5
c           dmembr=micdiam
c           dmin=micdiam
c           call profile (dmembr)
c           call locate4 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *        0,0,shminim,phiminim,tetaminim,4.,30.,30.)
c           call locate4 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *        1,1,shminim,phiminim,tetaminim,1.0,2.,2.)
c           if(ener.lt.emicmin) then
c              emicmin=ener
c              fmicdiam_min=float(micdiam)
c           end if 
c        end do
c        dmembr=fmicdiam_min
         dmembr=micdiam
         dmin=micdiam
         call profile (dmembr)
         call locate4 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *     0,0,shminim,phiminim,tetaminim,4.,30.,30.)
         call locate4 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *     1,1,shminim,phiminim,tetaminim,1.0,2.,2.)
         ii1=index(pdbtempl,'.pdb')-1
         write (*,'(a,''  energy='',2f6.1)')
     *     pdbtempl(1:ii1),ener
         write (24,'(a,'';'',2(f6.1,'';''))')
     *     pdbtempl(1:ii1),ener
         go to 999
      end if
c
      icurv=0
      radius=0.
c*    write (*,'(''dmatch='',2f10.1)') dmatch
      call optim (model,dmin,emism,dmatch,nsegm,nat,xyz,xyzc,
     *  solv,numres,namsu,shift,tilt,ener,iprint,namat,namres,
     *  pdbtempl,ifunc,d12,t12,nlipid,sysinp)
c     call profile (dmin)
c*    write (*,'(''ener='',f7.1,'', thickness='',f7.1)') ener,dmin
      dmembr=dmin
      dplanar=dmin
      eplanar=ener
c     call optim_curv(nat,xyz,xyzc,solv,dmin,ecurv,rmin,
c    *  iprint,1)
      if(icurve.eq.1) call optim_curv3(nat,xyz,xyzc,solv,
     *  dmin,ecurv,rmin,iprint,emism,dmatch,nlipid,1,model,sysinp)
c     ecurv=ecurv+float(nlipid)*emism*abs(dmin-dmatch)
c     write (*,'(''planar, curved:'', 2f10.1)') ener,ecurv
c     if(model.ne.1) then
c        call optim_curv2(nat,xyz,xyzc,solv,
c    *     dmin,ecurv,rmin,iprint,emism,dmatch,nlipid,1)
c        write (*,'(''planar, curved, 2:'', 2f10.1)') ener,ecurv
c     end if
      ecutoff=0.05*ener
c     if(icurve.eq.1.and.ecurv.lt.ener+ecutoff) then
      if(icurve.eq.1.and.ecurv.lt.ener) then
         dmembr=dmin
         icurv=1
c        icurv=2
         call profile (dmin)
         if(model.ne.1) then
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,4.,30.,30.,rmin)
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        1,1,shminim,phiminim,tetaminim,1.0,5.,5.,rmin)
         else
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,2.,20.,20.,rmin)
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        1,1,shminim,phiminim,tetaminim,0.5,2.,2.,rmin)
         end if
c        call locate2 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *     0,0,shminim,phiminim,tetaminim,2.,20.,20.,rmin)
c        call locate2 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *     1,1,shminim,phiminim,tetaminim,1.0,5.,5.,rmin)
c        call locate3 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *     0,0,shminim,phiminim,tetaminim,2.,20.,20.,rmin)
c        call locate3 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
c    *     1,1,shminim,phiminim,tetaminim,1.0,2.,2.,rmin)
         ener=ener+float(nlipid)*emism*(dmin-dmatch)**2
         write (*,'(''curved:'',2f9.1)') ener,rmin
         radius=rmin
      else
         dmin=dplanar
         call profile (dmin)
         call locate (nat,xyz,xyzc,solv,numres,namsu,dmin,
     *     shift,tilt,ener,iprint,namat,namres,
     *     pdbtempl,ifunc,s12,t12,1)
         ener=ener+float(nlipid)*emism*(dmin-dmatch)**2
      end if
c**
c     Define list of names of subunits:
c
      nsu=1
      namesu(1)=namsu(1)
      do i=2,nat
         if(namsu(i).ne.namsu(i-1)) then
            nsu=nsu+1
            namesu(nsu)=namsu(i)
         end if
      end do
c     do i=1,nsu
c        write (*,'(a1)') namesu(i)
c     end do
c
c     Output of tilt angles for individual subunits calculated
c     based on their inertia axes and lists of residues
c     penetratin to the hydrocarbon core
c
      if(icurv.eq.0) then
         do i=1,nsu
            call depth_angle2 (nat,xyz,tiltot,dmin,dpenetr,
     *        namat,numres,namsu,namesu(i),pdbtempl)
         end do
      end if
c**
c     Determine transmembrane segments and re-define their
c     tilt angles and tilt angle of the protein
c
      call depth_angle (nat,xyz,tiltot,dmin,dpenetr,icurv,radius)
      if(dpenetr.le.17.) then
         model=1
         dmm=dpenetr+0.4
      else 
         if(icurv.ne.0) then
            call find_segm (nat,xyz,xyzca,numres,namat,
     *        namsu,namres,nsegm,isegm,namsegm,natsegm,dmax,itypess,
     *        icurv,radius)
            write (*,'(i5,''possible transm. secondary structure''
     *        '' segments'')')  nsegm
            if(nsegm.ge.1) then
               do i=1,nsegm
                  write (*,'(i4,1x,a1,2i5,i4)') i,namsegm(i),
     *              (isegm(j,i),j=1,2),natsegm(i)
               end do
            end if
         end if
         if(nsegm.ge.1) call deftm (nres,ifirst,ilast,nsegm,
     *     namsegm,isegm,nat,xyz,dmin,numres,namsu,iprint,namat,
     *     xyzca,ienvat,solv,pdbtempl,tiltot,icurv,radius)
         dmm=dmin+0.8
      end if
c
      if(icurv.eq.0) then
         write (*,'(a10,1x,''emin='',f8.1,'' thickn='',f5.1,
     *     ''+-'',f4.1,'' tilt='',f7.0,''+-'',f6.0)') 
     *     pdbtempl(1:10),ener,dmm,d12,tiltot,t12
         itilt=int(tiltot)
         it12=int(t12)
         write (24,'(a14,'';'',2(f4.1,'';''),2(i4,'';''),
     *     2(f6.1,'';''))') pdbtempl(1:14),dmm,d12,itilt,it12,ener,
     *     ecurv
      else
         write (*,'(a10,1x,''emin='',f8.1,'' thickn='',f5.1,
     *     '' tilt='',f7.0)') 
     *     pdbtempl(1:10),ener,dmm,tiltot
         itilt=int(tiltot)
         write (25,'(a14,'';'',f4.1,'';'',f5.0,'';'',i4,'';'',
     *     2(f6.1,'';''))') pdbtempl(1:14),dmm,rmin,
     *     itilt,ener,eplanar
      end if
c
c     make rotation that provides optimal XY projection for picture
c     of the protein 
c
      call project (nat,xyz)
c
  999 continue
      close (21)
c
c     6. Determine transformation matrix and transform all atoms
c     from the original PDB file including HETERO atoms
c
      open(21,file=pdbtempl)
      open(22,file=pdbout)
      call write_pdb (nsuper,xyz,xyzbuf,dmin,itopo,model,
     *  icurv,radius,dinmin,doutmin,sysinp,nat,namat,namres,numres,
     *  nmembr,linesub)
      close (21)
      close (22)
      if(icurv.eq.1) then
c        write (*,'(''topo: '',a3,2(1x,f12.1))') itopo,dinmin,doutmin
         if((itopo.eq.'in '.and.doutmin.lt.dinmin).or.
     *     (itopo.eq.'out'.and.doutmin.gt.dinmin))
     *     call fixtopo(pdbout)
      end if
c
      return
      end
c
      subroutine optim (model,dmin,emism,dmatch,nsegm,nat,xyz,
     *  xyzc,solv,numres,namsu,shift,tilt,ener,iprint,namat,namres,
     *  pdbtempl,ifunc,d12,t12,nlipid,sysinp)
c     ------------------------------------------------------------
c     Minimize transfer energy. Free variables for optimization:
c     membrane thickness for TM version; shift of center
c     of mass along Z axis; and rotation angles arond OX and OY axes.
c
      character*80 pdbtempl
      character*1 namsu(1)
      character*3 sysinp
      character*4 namat(1),namres(1)
      integer numres(1)
      real xyz(3,1),solv(1),xyzc(3,1),dtab(500),etab(500)
c
      data ecut_tab/1.0/
c     data ecut_tab/1.0/,emism/0.0/
c
      if(model.eq.1) then
         dmembr=dmatch
         call profile (dmembr)
         call locate (nat,xyz,xyzc,solv,numres,namsu,dmembr,
     *     shift,tilt,ener,iprint,namat,namres,
     *     pdbtempl,ifunc,s12,t12,1)
         dmin=dmembr
         d12=s12
      else
         emin=99.
         dmin=99.
         m=0
         dm1=dmatch-3.2
         dm2=dmatch+3.2
         if(sysinp.eq.'   ') then
            dm1=dmatch-5.0
            dm2=dmatch+5.0
         end if
         do dmembr=dm1,dm2,0.2
            call profile (dmembr)
            call locate (nat,xyz,xyzc,solv,numres,namsu,dmembr,
     *        shift,tilt,ener,iprint,namat,namres,
     *        pdbtempl,ifunc,s12,t12,0)
c           diff=abs(dmembr-dmatch)
c           if(diff.gt.0.5) then
c              dmism=diff-0.5
c           else
c              dmism=0.
c           end if
c           ener=ener+float(nlipid)*emism*dmism
            ener=ener+float(nlipid)*emism*(dmembr-dmatch)**2
            m=m+1
            etab(m)=ener
            dtab(m)=dmembr
c           write (*,'(2f9.3,f8.1)') dtab(m),etab(m),tilt
            if(ener.lt.emin) then
               emin=ener
               dmin=dmembr
            end if
         end do
         ntab=m
         dmin0=100.
         dmax0=0.
         do i=1,ntab
c           write (*,'(2f9.3)') dtab(i),etab(i)
            if(etab(i).le.emin+ecut_tab) then
               if(dtab(i).lt.dmin0) dmin0=dtab(i)
               if(dtab(i).gt.dmax0) dmax0=dtab(i)
            end if
         end do
         d12=0.5*(dmax0-dmin0)
c        call profile (dmin)
c        call locate (nat,xyz,xyzc,solv,numres,namsu,dmin,
c    *     shift,tilt,ener,iprint,namat,namres,
c    *     pdbtempl,ifunc,s12,t12,1)
c           diff=abs(dmin-dmatch)
c           if(diff.gt.0.5) then
c              dmism=diff-0.5
c           else
c              dmism=0.
c           end if
c          ener=ener+float(nlipid)*emism*dmism
         ener=emin
      end if
      return
      end
c
      subroutine write_pdb (nsuper,xyz,xyzbuf,dmin,itopo,model,
     *  icurv,radius,dinmin,doutmin,sysinp,nat,namat,namres,numres,
     *  nmembr,linesub)
c     --------------------------------------------------------
c
      parameter (maxat=200000)
      real xyz(3,1),xyzbuf(3,1),vshift1(3),vshift2(3),rot(3,3),
     * xyzcur(3,maxat)
c
      character*3 resname(20)/'LEU','ILE','VAL','PHE','TRP',
     *  'MET','PRO','CYS','TYR','THR','SER','LYS','GLU',
     *  'ASP','HIS','GLN','ASN','ARG','ALA','GLY'/,itopo,
     *  sysinp
      character*4 namat(1),namres(1)
      integer numres(1)
      character*86 line
      character*1 numdum(8)/'x','y','z','s','t','r','p','q'/
      character*300 linesub
      data pi/3.1459/
c
c     Determine transformation matrix, transform all atoms
c     of the original PDB file including HETERO atoms,
c     and rewite PDB file keeping all other records from
c     original PDB file
c
      npoint=60
      maxpnt=2*npoint+1
c
c     determine transformation matrix and translation vector
c     for moving 'xyzbuf' to the coordinate system of 'xyz' set
c
      call rmsd (nsuper,xyz,xyzbuf,vshift1,vshift2,rot,rms)
c
c     modify coordinates of the original PDB file accordingly:
c
      dmem=dmin/2.
      dmm=dmem+0.4
      write (22,'(''REMARK      1/2 of bilayer thickness:'',f7.1)') dmm
      dxymax=0.
      zav=0.
      topo=1.
      mcount=1
c
      if(sysinp.eq.'MIC') then
         do i=1,nat
            a=xyz(1,i)
            b=xyz(2,i)
            c=xyz(3,i)
            write (22,'(''ATOM  '',i5,2x,2a4,i5,4x,3f8.3,a26)')
     *        i,namat(i),namres(i),numres(i),a,b,c
            dxy=sqrt(a*a+b*b)
            if(abs(c).le.25..and.dxy.gt.dxymax) dxymax=dxy
         end do
         dxymax=dxymax+5.
         m=nat+1
c        do phi0=0.,360.,10.
         phi0=0.
         do while (phi0.le.360.)
            phi=phi0*pi/180.
c           do teta0=0.,360.,10.
            teta0=0.
            do while (teta0.le.360.)
               teta=teta0*pi/180.
               co=cos(teta)
               a=dmm*co*cos(phi)
               b=dmm*co*sin(phi)
               c=dmm*sin(teta)
               call checkdum (nat,xyz,a,b,c,indic)
               if(indic.eq.1) then
                  m=m+1
                  write (22,'(''HETATM'',i5,2x,''N   '',''DUM '',
     *              1x,i4,4x,3f8.3)') m,m,a,b,c
               end if
               teta0=teta0+10.
            end do
            phi0=phi0+10.
         end do
         go to 999
      end if 
      mcc=1
      do i=1,999999
         read (21,'(a)',end=20) line
         if(line(1:6).eq.'ENDMDL') go to 20
         if(line(14:14).eq.'H'.or.line(14:14).eq.'D'.or.
     *     line(13:13).eq.'H'.or.line(14:14).eq.'Q') go to 16
         if(nmembr.eq.0) then
            if(line(18:20).eq.'DUM'.or.line(9:14).eq.
     *         '1/2 of') go to 16
         else
            if(line(9:14).eq.'1/2 of') go to 16
         end if
         if(line(1:4).eq.'ATOM'.or.line(1:6).eq.'HETATM') then
            mcc=mcc+1
            read (line,'(30x,3f8.3)') xc,yc,zc
            xc=xc-vshift2(1)
            yc=yc-vshift2(2)
            zc=zc-vshift2(3)
            a=xc*rot(1,1)+yc*rot(1,2)+zc*rot(1,3)
            b=xc*rot(2,1)+yc*rot(2,2)+zc*rot(2,3)
            c=xc*rot(3,1)+yc*rot(3,2)+zc*rot(3,3)
            a = a + vshift1(1)
            b = b + vshift1(2)
            c = c + vshift1(3)
            if(mcount.eq.1) then
               mcount=2
               if(icurv.eq.1) then
                  dd=sqrt(a*a+b*b+c*c)-radius
                  if(itopo.eq.'in '.and.dd.lt.0.) topo=1.
                  if(itopo.eq.'in '.and.dd.ge.0.) topo=-1.
                  if(itopo.eq.'out'.and.dd.lt.0.) topo=-1.
                  if(itopo.eq.'out'.and.dd.ge.0.) topo=1.
               end if
               if(icurv.eq.2) then
                  dd=sqrt(a*a+c*c)-radius
                  if(itopo.eq.'in '.and.dd.lt.0.) topo=1.
                  if(itopo.eq.'in '.and.dd.ge.0.) topo=-1.
                  if(itopo.eq.'out'.and.dd.lt.0.) topo=-1.
                  if(itopo.eq.'out'.and.dd.ge.0.) topo=1.
               end if
               if(icurv.eq.0) then
                  if(itopo.eq.'in '.and.c.lt.0.) topo=1.
                  if(itopo.eq.'in '.and.c.ge.0.) topo=-1.
                  if(itopo.eq.'out'.and.c.lt.0.) topo=-1.
                  if(itopo.eq.'out'.and.c.ge.0.) topo=1.
               end if
c              write (*,'(''topo='',f4.0)') topo
            end if
            c=c*topo
            b=b*topo
            if(mcc.eq.2) then
               a1=a
               b1=b
               c1=c
            end if
            xyzcur(1,mcc)=a
            xyzcur(2,mcc)=b
            xyzcur(3,mcc)=c
            dxy=sqrt(a*a+b*b)
c           if(abs(c).le.25..and.dxy.gt.dxymax) dxymax=dxy
            if(nmembr.eq.0) then
               if(line(18:20).ne.'DUM'.and.dxy.gt.dxymax) dxymax=dxy
            else
               lsub=index(linesub,' ')
               nsub=lsub/2
               do j=1,nsub
                  jj=2*j-1
                  if(line(22:22).eq.linesub(jj:jj)) then
                     if(line(18:20).ne.'DUM'.and.dxy.gt.dxymax) 
     *                 dxymax=dxy
                     go to 10
                  end if
               end do
            end if
   10       continue
c
            if(line(1:4).eq.'ATOM') then
               do j=1,20
                  if(line(18:20).eq.resname(j)) then
                     write (22,'(a30,3f8.3,a26)') line(1:30),
     *                 a,b,c,line(55:86)
                     go to 15
                  end if
               end do
               write (22,'(''HETATM'',a24,3f8.3,a26)') line(7:30),
     *           a,b,c,line(55:86)
   15          continue
            else
               write (22,'(a30,3f8.3,a26)') line(1:30),
     *           a,b,c,line(55:86)
            end if
            zav=zav+c
         else
c          if(line(1:3).ne.'END'.and.line(1:3).ne.'TER'.and.
           if(line(1:6).ne.'ANISOU'.and.line(1:4).ne.'CONE')
     *       write (22,'(a)') line
         end if
   16    continue
      end do
   20 continue
      natcur=mcc
      m=mcc+1
c
      dinmin=10000000.
      doutmin=10000000.
      if(m.gt.80000) m=1
      mm0=1
      idum=1
      fn=2.*float(npoint)
      do i=1,maxpnt
         do j=1,maxpnt
            a=float(2*i)-fn
            b=float(2*j)-fn
            dxy=sqrt(a*a+b*b)
            if(dxy.le.dxymax) then
               m=m+1
               mm0=mm0+1
               if(mm0.gt.9999) then
                  mm0=1
                  idum=idum+1
               end if
               if(icurv.eq.1) then
                  r1=radius-dmem-0.4
                  dist=r1*r1-a*a-b*b 
                  if(dist.gt.1.) then
                     c=topo*sqrt(dist)
                     ad=a-a1
                     bd=b-b1
                     cd=c-c1
                     din=ad*ad+bd*bd+cd*cd
                     if(din.lt.dinmin) dinmin=din
                  else
                     c=-999.
                  end if
               end if 
               if(icurv.eq.2) then
                  r1=radius-dmem-0.4
                  dist=r1*r1-a*a
                  if(dist.gt.1.) then
                     c=topo*sqrt(dist)
                  else
                     c=-999.
                  end if
               end if 
               if(icurv.eq.0) then
                  c=-dmem-0.4
               end if 
               if(c.ne.-999.) then
                  call checkdum (natcur,xyzcur,a,b,c,indic)
                  if(indic.eq.1) 
     *              write (22,'(''HETATM'',i5,2x,''N   '',''DUM '',a1,
     *              i4,4x,3f8.3)') m,numdum(idum),mm0,a,b,c
               end if
               m=m+1
               mm0=mm0+1
               if(mm0.gt.9999) then
                  mm0=1
                  idum=idum+1
               end if
               if(icurv.eq.1) then
                  r1=radius+dmem+0.4
                  dist=r1*r1-a*a-b*b
                  if(dist.gt.1.) then
                     c=topo*sqrt(dist)
                     ad=a-a1
                     bd=b-b1
                     cd=c-c1
                     dout=ad*ad+bd*bd+cd*cd
                     if(dout.lt.doutmin) doutmin=dout
                  else
                     c=-999.
                  end if
               end if 
               if(icurv.eq.2) then
                  r1=radius+dmem+0.4
                  dist=r1*r1-a*a
                  if(dist.gt.1.) then
                     c=topo*sqrt(dist)
                  else
                     c=-999.
                  end if
               end if 
               if(icurv.eq.0) then
                  c=dmem+0.4
               end if 
               if(c.ne.-999.) then
                  call checkdum (natcur,xyzcur,a,b,c,indic)
                  if(indic.eq.1) 
     *              write (22,'(''HETATM'',i5,2x,''O   '',''DUM '',a1,
     *                i4,4x,3f8.3)') m,numdum(idum),mm0,a,b,c
               end if
            end if
         end do
      end do
      do i=1,999999
         read (21,'(a)',end=30,err=30) line
         if(i.eq.1) write (22,'(''ENDMDL'')') 
         if(line(1:5).eq.'MODEL') go to 30
         write (22,'(a)') line
      end do
   30 continue
  999 continue
      return
      end
c
      subroutine biounit (nameinp)
c     ---------------------------
c     Defining names of subunits in quaternary structure
c     files generated by PDB
c     Subunits in 1st "model" will be redefined as A,B,C, etc.,
c     but only if there are several "models"
c
c     No proper treatment for beta-sheet with inter-subunit H-bonds
c   
      parameter (maxsu=62,maxsheet=1000,maxhelix=1000)
      character*80 line,sheet(maxsheet),helix(maxhelix),line2
      character*1 su,name(maxsu)/'A','B','C','D','E','F','G','H','I',
     *  'J','K','L','M','N','O','P','Q','R','S','T','U','V','W','Y',
     *  'X','Z','1','2','3','4','5','6','7','8','9',
     *  'a','b','c','d','e','f','g','h','i',
     *  'j','k','l','m','n','o','p','q','r','s','t','u','v','w','y',
     *  'x','z','0'/,
     *  subuf,set1(2,maxsu),sunew
      character*80 nameinp,namepdb,filess
c
      open(1,file=nameinp)
      iexit1=1
      iexit2=1
      do i=1,200000
         read (1,'(a)',end=5) line
         if(line(1:6).eq.'EXPDTA') then
            if(line(11:27).eq.'X-RAY DIFFRACTION'.or.
     *        line(11:29).eq.'ELECTRON MICROSCOPY') iexit1=0
         end if
         if(line(1:14).eq.'MODEL        2') then
            iexit2=0
            go to 5
         end if
      end do
    5 continue
      close(1)
      if(iexit1.eq.1.or.iexit2.eq.1) return
c
      namepdb=nameinp(1:4)//'.pdbx'
      filess=nameinp(1:4)//'.ss'
      open(1,file=nameinp)
      open(2,file=namepdb)
      open(3,file=filess)
c
c     Read 1st model to identify list of its subunits
c     and establish relations to subunits for renaming
c     (A,B,C, ...). Also read HELIX and SHEET records.
c
      set1(1,1)='!'
      nset=0
      nmodel=1
      nhelix=0
      nsheet=0
      do i=1,200000
         read (1,'(a)',end=10) line
         if(line(1:5).eq.'HELIX') then
               nhelix=nhelix+1
            helix(nhelix)=line
         end if
         if(line(1:5).eq.'SHEET') then
            nsheet=nsheet+1
            sheet(nsheet)=line
         end if
c
         if(line(1:14).eq.'MODEL        2') then
            nmodel=2
            go to 10
         end if
         if(line(1:4).eq.'ATOM'.or.line(1:6).eq.'HETATM') then
            subuf=line(22:22)
            iflag=1
            do j=1,nset
               if(subuf.eq.set1(1,j)) iflag=0
            end do
            if(iflag.eq.1) then
               nset=nset+1
               set1(1,nset)=subuf
               set1(2,nset)=name(nset)
            end if
         end if
      end do
   10 continue
      close(1)
      open(1,file=nameinp)
c
      do i=1,200000
         read (1,'(a)',end=30) line
         if(line(1:5).eq.'MODEL') then
            read (line,'(6x,i8)') kmodel
c
c           write HELIX and SHEET records for the corresponding
c           subunit to separate file:
c
            do j=1,nset
               kalp=j+nset*(kmodel-1)
               sunew=name(kalp)
               if(nhelix.gt.0) then
                  do k=1,nhelix
                     call writess (helix(k),set1(1,j),sunew)
                  end do
               end if
               if(nsheet.gt.0) then
                  do k=1,nsheet
                     call writess (sheet(k),set1(1,j),sunew)
                  end do
               end if
            end do
         end if
c
         if(line(1:5).eq.'MODEL'.or.line(1:6).eq.'ENDMDL') go to 20
         if(line(1:4).eq.'ATOM'.or.line(1:6).eq.'HETATM') then
            if(nmodel.eq.1) then
               write (2,'(a)') line
               go to 20
            end if
            subuf=line(22:22)
            do j=1,nset
               if(subuf.eq.set1(1,j)) jsu=j
            end do
            if(kmodel.eq.1) then
               write (2,'(a21,a1,a58)')
     *           line(1:21),set1(2,jsu),line(23:80)
            else
               kalp=jsu+nset*(kmodel-1)
               if(kalp.gt.maxsu) then
                  write (*,'(''Too many subunits'')')
                  stop
               end if
               write (2,'(a21,a1,a58)') line(1:21),
     *           name(kalp),line(23:80)
            end if
         else
            write (2,'(a)') line
         end if
   20    continue
      end do
   30 continue
      close (1)
      close (2)
      close (3)
c     kalp=nset*kmodel
c     write (*,'(a4,1x,i5,'' subunits'')') namepdb(1:4),kalp
c
      open(1,file=nameinp)
      open(2,file=namepdb)
      open(3,file=filess)
      m=0
      do i=1,200000
         read (2,'(a)',end=50) line
         if(line(1:5).eq.'SHEET'.or.line(1:6).eq.'HELIX') then 
            if(m.eq.0) then
               do j=1,9999
                  read (3,'(a)',end=40) line2
                  write (1,'(a)') line2
               end do
   40          continue
               close (3)
            end if
            m=m+1
         else
            write (1,'(a)') line
         end if
      end do
   50 continue
      close (1)
      close (2)
      return 
      end
c
      subroutine writess (line1,suold,sunew)
c     -------------------------------------
      parameter (npos=6)
      character*80 line1,line2
      character*1 suold,sunew
      integer ipos(6)/20,22,32,33,50,65/
c     
c     HELIX: 20,32, SHEET: 22,33,50,65
c
      iflag=0
      line2=line1
      do j=1,npos
         i=ipos(j)
         if(line1(i-1:i-1).eq.' '.and.line1(i:i).eq.suold.and.
     *     line1(i+1:i+1).eq.' ') then
            iflag=1
            line2(i:i)=sunew
         end if
      end do
      if(iflag.eq.1) write (3,'(a)') line2
      return
      end
c
      subroutine optim_curv(nat,xyz,xyzc,solv,dmembr,emin,rmin,
     *  iprint,icurv)
c     -----------------------------------------------------------
      real xyz(3,1),solv(1),xyzc(3,1)
c
      emin=99.
      rmin=0.
      do radius=70.,201.,10.
         if(icurv.eq.1) then
            call locate2 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,4.,30.,30.,radius)
            call locate2 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *        0,1,shminim,phiminim,tetaminim,1.0,10.,10.,radius)
         end if
         if(icurv.eq.2) then
            call locate3 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,4.,30.,30.,radius)
            call locate3 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *        0,1,shminim,phiminim,tetaminim,1.0,10.,10.,radius)
         end if
         write (*,'(2f7.1)') ener,radius
         if(ener.lt.emin) then
            emin=ener
            rmin=radius
         end if
      end do
      return
      end
c
      subroutine optim_curv2(nat,xyz,xyzc,solv,dmin,emin,rmin,iprint,
     *  emism,dmatch,nlipid,icurv)
c     -----------------------------------------------------------------
      real xyz(3,1),solv(1),xyzc(3,1)
c
      dm1=dmin-3.
      dm2=dmin+2.
      do dm=dm1,dm2,1.
         call profile (dm)
         if(icurv.eq.1) then
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,4.,30.,30.,rmin)
            call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,1,shminim,phiminim,tetaminim,1.0,10.,10.,rmin)
         end if
         if(icurv.eq.2) then
            call locate3 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,0,shminim,phiminim,tetaminim,4.,30.,30.,rmin)
            call locate3 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *        0,1,shminim,phiminim,tetaminim,1.0,10.,10.,rmin)
         end if
         ener=ener+float(nlipid)*abs(dm-dmatch)**2
         write (*,'(''addit. thickn. optim:'',2f7.1)') ener,dm
         if(ener.lt.emin) then
            emin=ener
            dmin=dm
         end if
      end do
      return
      end
c
      subroutine optim_curv3(nat,xyz,xyzc,solv,dmin,emin,rmin,iprint,
     *  emism,dmatch,nlipid,icurv,model,sysinp)
c     -----------------------------------------------------------------
      real xyz(3,1),solv(1),xyzc(3,1)
      character*3 sysinp
c
      emin=99.
      rmin=0.
      dm1=dmatch-3.2
      dm2=dmatch+3.2
      if(sysinp.eq.'   ') then
         dm1=dmatch-5.0
         dm2=dmatch+5.0
      end if
      if(model.eq.1) then
         dm1=dmatch
         dm2=dmatch
      end if
c     write (*,'(i4)') model
      do dm=dm1,dm2,0.2
         call profile (dm)
         do radius=80.,601.,10.
c        do radius=20.,351.,10.
            if(model.ne.1) then
               call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *           0,0,shminim,phiminim,tetaminim,4.,30.,30.,radius)
               call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *           0,1,shminim,phiminim,tetaminim,1.0,5.,5.,radius)
            else
               call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *           0,0,shminim,phiminim,tetaminim,2.,20.,20.,radius)
               call locate2 (nat,xyz,xyzc,solv,dm,shift,ener,iprint,
     *           0,1,shminim,phiminim,tetaminim,0.5,2.,2.,radius)
            end if
            ener=ener+float(nlipid)*emism*(dm-dmatch)**2
c           write (*,'(''Hydr. thickn.='',f6.1,
c    *        ''A, Radius of curv.='',f6.1,
c    *        '' A, Energy='',f6.1, ''kca/mol'')') dm,radius,ener
c           write (*,'(''ener,dm,radius:'',3f7.1)') ener,dm,radius
            if(ener.lt.emin) then
               emin=ener
               dmin=dm
               rmin=radius
            end if
         end do
      end do
      return
      end
c
      subroutine fixtopo(pdbout)
c     -------------------------
      character*80 pdbout,line
      character*81 pdbout1
c
      ind1=index(pdbout,' ')-1
      pdbout1=pdbout(1:ind1)//'1'
      open (22,file=pdbout)
      open (26,file=pdbout1)
      do i=1,99999999
         read (22,'(a)',end=10) line
         if(line(18:20).eq.'DUM') then
            if(line(14:14).eq.'N') then
               line(14:14)='O'
            else
               line(14:14)='N'
            end if
            write (26,'(a)') line
         else
            write (26,'(a)') line
         end if
      end do
   10 continue
      close (22)
      close (26)
      open (22,file=pdbout)
      open (26,file=pdbout1)
      do i=1,99999999
         read (26,'(a)',end=20) line
         write (22,'(a)') line
      end do
   20 continue
      close (22)
      close (26)
      return
      end 
c
      subroutine checkdum (nat,xyz,a,b,c,indic)
c     ----------------------------------------
      real xyz(3,1)
      real dumcut1/2.00/,dumcut2/3.24/
      indic=1
      do i=1,nat
         cc=xyz(3,i)-c
         if(abs(cc).ge.dumcut1) go to 10
         aa=xyz(1,i)-a
         if(abs(aa).ge.dumcut1) go to 10
         bb=xyz(2,i)-b
         if(abs(bb).ge.dumcut1) go to 10
         indic=0
   10    continue
      end do
      return
      end
