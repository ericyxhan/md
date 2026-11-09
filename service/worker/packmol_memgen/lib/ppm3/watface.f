      subroutine watface0 (nat,ienvat,nres,ienv)
c     -----------------------------------------
c     Determine "water-facing" atoms and residues.  
c
c     ienvat= 1 - lipid-accessible atom
c             0 - lipid-inaccessible atom
c
      integer ienvat(1),ienv(1)
c
      do i=1,nat
         ienvat(i)=1
      end do
      do i=1,nres
         ienv(i)=1
      end do
      return
      end
c
      subroutine watface (nat,xyz,numres,namsu,nres,ifirst,ilast,
     *  ienv,iprint,pdbtempl,nsegm,natsegm,xyzca,model,
     *  ienvat,namat,namres,nlipid)
c     ---------------------------------------------------------------
c     Determine "water-facing" atoms and residues.  
c
c     ASA of water-facing atoms are nullified.  
c
c     A residue is lipid-inaccessible if ALL its atoms
c     are lipid-inaccessible
c
c     ienvat= 1 - lipid-accessible atom
c             0 - lipid-inaccessible atom
c
      parameter (maxat=200000,maxsegm=900)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      character*1 namsu(1),count
      character*80 namfile,line,pdbtempl
      character*4 namat(1),namres(1)
c
      integer numres(1),ienvat(1),natsegm(1),
     *  ifirst(1),ilast(1),ienv(1),ienvat1(maxat)
      real xyz(3,1),xyzca(3,maxsegm,1)
c
c     define environments of atoms:
c
      do i=1,nat
         ienvat(i)=1
      end do
c
      if(nsegm.gt.2) then
         distmax=0.
         do j=1,nsegm
            do k=1,natsegm(j)
               x=xyzca(1,j,k)
               y=xyzca(2,j,k)
               z=xyzca(3,j,k)
               dist=sqrt(x*x+y*y)
               if(dist.gt.distmax.and.abs(z).lt.4.) distmax=dist
            end do
         end do
         do i=1,nat
            ienvat(i)=0
            ienvat1(i)=0
         end do
c
c        call rectang (nat,xyz,ienvat,accs)
c
         call stagger (0.,0.,nat,xyz,ienvat,accs,ienvat1)
         s0=distmax-15.
         step0=(2.*s0)/15.
         step=amax1(2.,step0)
         nstep=int(s0/step)
         if(nstep.ge.1) then
            do l1=-nstep,nstep
               sh1=float(l1)*step
               do l2=-nstep,nstep
                  sh2=float(l2)*step
                  shift=sqrt(sh1*sh1+sh2*sh2)
                  if(shift.le.distmax-15.)
     *              call stagger (sh1,sh2,nat,xyz,ienvat,accs,ienvat1)
               end do
            end do
         end if
         do i=1,nat
            if(accs(i).eq.0.) ienvat(i)=0
         end do
      end if
c
c     Determine number of interacting lipid molecules
c
      surf=0.
      do i=1,nat
         if(xyz(3,i).ge.-10.and.xyz(3,i).le.10.and.
     *     ienvat(i).ne.0) surf=surf+accs(i)
      end do
      perim=surf/20.
      nlipid=int(perim/6.0)
c
c     define environments of residues (including hetero-groups):
c
      do i=1,nres
         ienv(i)=0
         ir=ifirst(i)
         if(namres(ir).eq.'ALA ') then
            do j=ifirst(i),ilast(i)
               if(namat(j).eq.'CB  '.and.ienvat(j).eq.1) then
                  ienv(i)=1
                  go to 30
               end if
            end do
         end if
         if(namres(ir).eq.'GLY ') then
            do j=ifirst(i),ilast(i)
               if(namat(j).eq.'CA  '.and.ienvat(j).eq.1) then
                  ienv(i)=1
                  go to 30
               end if
            end do
         end if
         if(namres(ir).eq.'LEU '.or.namres(ir).eq.'ILE '.or.
     *      namres(ir).eq.'VAL '.or.namres(ir).eq.'PHE '.or.
     *      namres(ir).eq.'TRP '.or.namres(ir).eq.'MET '.or.
     *      namres(ir).eq.'PRO '.or.namres(ir).eq.'CYS '.or.
     *      namres(ir).eq.'TYR '.or.namres(ir).eq.'THR '.or.
     *      namres(ir).eq.'SER '.or.namres(ir).eq.'HIS '.or.
     *      namres(ir).eq.'LYS '.or.namres(ir).eq.'GLN '.or.
     *      namres(ir).eq.'GLU '.or.namres(ir).eq.'ASN '.or.
     *      namres(ir).eq.'ASP '.or.namres(ir).eq.'ARG ') then
            do j=ifirst(i),ilast(i)
               if(namat(j).ne.'N   '.and.namat(j).ne.'CA  '.and.
     *           namat(j).ne.'CB  '.and.namat(j).ne.'C   '.and.
     *           namat(j).ne.'O   '.and.ienvat(j).eq.1) then
                  ienv(i)=1
                  go to 30
               end if
            end do
         else
            do j=ifirst(i),ilast(i)
               if(ienvat(j).eq.1) then
                  ienv(i)=1
                  go to 30
               end if
            end do
         end if
   30    continue
      end do
c
c     nullify ASA of lipid-inaccessible atoms
c
      if(nsegm.gt.2) then
         do i=1,nat
            if(ienvat1(i).eq.0) then
               accs(i)=0.
               ienvat(i)=0
            end if
         end do
      end if
c
c     nullify ASA of atoms that belong to lipid-inaccessible
c     amino acid residues:
c
c     do i=1,nres
c        if(ienv(i).eq.0) then
c           do j=ifirst(i),ilast(i)
c              accs(j)=0.
c              ienvat(j)=0
c           end do
c        end if
c     end do
c
c     File to color residues by environments for QUANTA:
c
c     if(nsegm.gt.2) then
c        i1=index(pdbtempl,'.pdb')-1
c        namfile=pdbtempl(1:i1)//'_1.csd'
c        open (14,file=namfile)
c        write (14,'(''ALL = COL  1'')')
c        do i=1,nres
c           if(ienv(i).eq.1) then
c              icol=3
c              nn=numres(ifirst(i))
c              write (line,'(''ZONE'',1x,a1,'':'',i5,
c    *           '' = COL'',i5)') namsu(ifirst(i)),nn,icol
c              do j=1,4
c                 if(line(8:8).eq.' ') line=line(1:7)//line(9:80)//' '
c              end do
c              write (14,'(a)') line
c           end if
c        end do
c
c        do i=1,nat
c           if(ienvat(i).eq.1) then
c              icol=3
c              nn=numres(i)
c              write (line,'(''ATOM'',1x,a4,5x,a4,1x,a1,'':'',i5,
c    *           '' = COL'',i5)') namat(i),namres(i),namsu(i),nn,icol
c              do j=1,4
c                 if(line(22:22).eq.' ') 
c    *              line=line(1:21)//line(23:80)//' '
c              end do
c              write (14,'(a)') line
c           end if
c        end do
c        close (14)
c     end if
      return
      end
c
      subroutine stagger (sh1,sh2,nat,xyz0,ienvat,accs,ienvat1)
c     --------------------------------------------------------
c     Mark all atoms that are not staggered by other atoms 
c     as ienvat=1
c
c     sh1 and sh2 are shifts of the axis defining "viewpoint"
c
      parameter (maxat=200000)
c
      data pi/3.14159/,distcut/2.0/,zcut/2.0/,acut/0./,
     * d2cut/13./
c
      integer ienvat(1),ienvat1(1)
      real xyz0(3,1), xyz(3,maxat),rc(maxat),
     *  accs(1)
c
      do i=1,nat
         xyz(1,i)=xyz0(1,i)+sh1
         xyz(2,i)=xyz0(2,i)+sh2
         xyz(3,i)=xyz0(3,i)
         x=xyz(1,i)
         y=xyz(2,i)
         rc(i)=sqrt(x*x+y*y)
      end do
c
      do i=1,nat
         if(accs(i).eq.0..or.abs(xyz(3,i)).gt.40..or.
     *      rc(i).lt.0.01) go to 10
c        if(accs(i).eq.0.) go to 10
         nj=0
         zi=xyz(3,i)
         do j=1,nat
            if(j.ne.i.and.rc(j).gt.0.01) then
               if(rc(j)-rc(i).gt.distcut) then
                  zj=xyz(3,j)
                  tn=abs(zi-zj)/(rc(j)-rc(i))
                  if(abs(xyz(3,j)-xyz(3,i)).lt.zcut.or.
     *              (((zj.gt.zi.and.zj.lt.-8.).or.
     *                (zj.lt.zi.and.zj.gt.8.)).and.tn.lt.1.)) then
c                    xj=xyz(1,i)*rc(j)/rc(i)
c                    yj=xyz(2,i)*rc(j)/rc(i)
c                    a=xyz(1,j)-xj
c                    b=xyz(2,j)-yj
c                    d2=a*a+b*b
c                    if(d2.lt.d2cut) nj=nj+1
                     co=(xyz(1,i)*xyz(1,j)+xyz(2,i)*xyz(2,j))
     *                 /(rc(i)*rc(j))
                     ang=acos(co)
                     rr=rc(j)*tan(ang)
                     if(rr.gt.0..and.rr.lt.3.6) nj=nj+1
                  end if
               end if
            end if
         end do
         if(accs(i).gt.acut.and.nj.lt.1) ienvat(i)=1
         if(nj.lt.1) ienvat1(i)=1
   10    continue
      end do
      return
      end
