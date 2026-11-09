      subroutine tilting (phi,teta,nat,xyz,xyzc)
c     ------------------------------------------
c     rotate coordinate set 'xyz' by angle 'teta' around axis in OXY
c     plane that forms phi anglr with OX axis
c     
      real xyz(3,1),xyzc(3,1),rot(3,3)
c
      a=sin(phi)
      b=cos(phi)
      si=sin(teta)
      co=cos(teta)
      co1=1.-co
      rot(1,1)=co+a*a*co1
      rot(1,2)=a*b*co1
      rot(1,3)=b*si
      rot(2,1)=rot(1,2)
      rot(2,2)=co+b*b*co1
      rot(2,3)=-a*si
      rot(3,1)=-rot(1,3)
      rot(3,2)=-rot(2,3)
      rot(3,3)=co
      do i=1,nat
         xyzc(1,i)=rot(1,1)*xyz(1,i)+rot(1,2)*xyz(2,i)+rot(1,3)*xyz(3,i)
         xyzc(2,i)=rot(2,1)*xyz(1,i)+rot(2,2)*xyz(2,i)+rot(2,3)*xyz(3,i)
         xyzc(3,i)=rot(3,1)*xyz(1,i)+rot(3,2)*xyz(2,i)+rot(3,3)*xyz(3,i)
      end do
      return
      end
c
      subroutine bundle_axis0 (nat,namat,xyz)
c     --------------------------------------
c     Origin of coordinates corresponds
c     to center of mass of the set of CA atoms.
c
      real v(3),xyz(3,1)
c
      character*4 namat(1)
c
c     Define center of mass of CA atoms and
c     move all coordinates accordingly:
c
      do j=1,3
         v(j)=0.
      end do
c
      nca=0
      do i=1,nat
c**      if(namat(i).eq.'CA  ') then
            nca=nca+1
            do k=1,3
               v(k)=v(k)+xyz(k,i)
            end do
c**      end if
      end do
c
      do k=1,3
         v(k)=v(k)/float(nca)
         do i=1,nat
            xyz(k,i)=xyz(k,i)-v(k)
         end do
      end do
c
      return
      end
c
      subroutine bundle_axis (nat,xyz,xyzc,nsegm,isegm,
     *  natsegm,xyzca,iprint,numres,namsu,namat,namres)
c     -------------------------------------------------------
c     Determine axes of all individual helices and axis of the entire
c     alpha-bundle.  Transform all coordinates to make this axis
c     coincide with Z axis.  Origin of coordinates corresponds
c     to center of mass of the set of CA atoms.
c
      parameter (maxsegm=900,maxlen=65,maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real v(3),xyz(3,1),xyzca(3,maxsegm,1),xyzc(3,1),
     *  vt(3),vs(3,maxsegm),xyzbuf(3,maxlen),v1(3),v2(3)
c
      integer numres(1),natsegm(1),isegm(2,1)
c
      character*80 namfile
      character*1 namsu(1)
      character*4 namat(1),namres(1)
c
      data pi/3.14159/
c
c     Define center of mass of CA atoms and
c     move all coordinates accordingly:
c
      do j=1,3
         v(j)=0.
      end do
      nca=0
c
c     do i=1,nat
c        if(namat(i).eq.'CA  ') then
c           nca=nca+1
c           do k=1,3
c              v(k)=v(k)+xyz(k,i)
c           end do
c        end if
c     end do
c
c     do k=1,3
c        v(k)=v(k)/float(nca)
c        do i=1,nat
c           xyz(k,i)=xyz(k,i)-v(k)
c        end do
c     end do
c
      do i=1,nsegm
         nca=nca+natsegm(i)
         do j=1,natsegm(i)
            do k=1,3
               v(k)=v(k)+xyzca(k,i,j)
            end do
         end do
      end do
c 
      do k=1,3
         v(k)=v(k)/float(nca)
         do i=1,nsegm
            do j=1,natsegm(i)
               xyzca(k,i,j)=xyzca(k,i,j)-v(k)
            end do
         end do
         do i=1,nat
            xyz(k,i)=xyz(k,i)-v(k)
         end do
      end do
c
c     Determine axis of each helix:
c
      do i=1,nsegm
         do k=1,3
            v1(k)=0.
            v2(k)=0.
         end do
         nref=7
         l=isegm(2,i)-isegm(1,i)+1
         if(l.ge.7.and.l.le.15) nref=4
         if(l.ge.5.and.l.le.6) nref=3
         if(l.le.4) then
            do k=1,3
               vs(k,i)=xyzca(k,i,l)-xyzca(k,i,1)
            end do
         else
            do j=1,nref
               nn=natsegm(i)-nref+j
               do k=1,3
                  v1(k)=v1(k)+xyzca(k,i,j)
                  v2(k)=v2(k)+xyzca(k,i,nn)
               end do
            end do
            do k=1,3
               v1(k)=v1(k)/float(nref)   
               v2(k)=v2(k)/float(nref)   
               vs(k,i)=v2(k)-v1(k)
            end do
         end if  
         r=sqrt(vs(1,i)**2+vs(2,i)**2+vs(3,i)**2)
         do k=1,3
            vs(k,i)=vs(k,i)/r
         end do
      end do
c
c     Choose sign/directions of axis for each TM secondary
c     structure relative to OZ axis so that all SS vectors 
c     are facing roughtly in the same direction
c
      do i=1,nsegm
         r=sqrt(vs(1,i)*vs(1,i)+vs(2,i)*vs(2,i)+vs(3,i)*vs(3,i))
         ang=(acos(vs(3,i)/r)/pi)*180.
         if(ang.gt.90.) then
            do k=1,3
               vs(k,i)=-vs(k,i)
            end do
         end if
      end do
c
c     Vector of alpha-bundle axis:
c
      do k=1,3
         v(k)=0.
      end do
      do i=1,nsegm
         do k=1,3
            v(k)=v(k)+vs(k,i)
         end do
      end do
c
c     Angle betwen this axis and OZ:
c
      r=sqrt(v(1)*v(1)+v(2)*v(2)+v(3)*v(3))
      phi=acos(v(3)/r)
c     do k=1,3
c        v(k)=v(k)/r
c     end do
c
c     Perpendicular axis:
c
      v1(3)=0.
c     if((v(1).gt.0.and.v(2).gt.0.).or.(v(1).lt.0.and.v(2).lt.0.)) then
c        v1(1)=-v(2)
c        v1(2)= v(1)
c     else
         v1(1)= v(2)
         v1(2)=-v(1)
c     end if
c
c     Rotation:
c
      vt(1)=0.
      vt(2)=0.
      vt(3)=0.
      call rotate (nat,xyz,phi,v1,vt) 
      do i=1,nsegm
         do j=1,natsegm(i)
            do k=1,3
               xyzbuf(k,j)=xyzca(k,i,j)
            end do
         end do
         call rotate (natsegm(i),xyzbuf,phi,v1,vt)
         do j=1,natsegm(i)
            do k=1,3
               xyzca(k,i,j)=xyzbuf(k,j)
            end do
         end do
      end do
      return
      end
c
      subroutine depth_angle (nat,xyz,tetamin,dmembr,dmax,icurv,radius)
c     ----------------------------------------------------------------
c     Determine tilt angle and maximal membrane penetration depth
c     for a protein with undefined secondary structure.
c     Tilt angle is the angle between protein inertia axis
c     and membrane normal (this is different from a protein with
c     defined TM secondary structure)
c
      parameter (maxat=200000)
      real xyz(3,1),xyz0(3,maxat)
      data pi/3.14159/
c
c     center of mass:
c
      xc=0.
      yc=0.
      zc=0.
      do j=1,nat
         xc=xc+xyz(1,j)
         yc=yc+xyz(2,j)
         zc=zc+xyz(3,j)
      end do
      xc=xc/float(nat)
      yc=yc/float(nat)
      zc=zc/float(nat)
      do j=1,nat
         xyz0(1,j)=xyz(1,j)-xc
         xyz0(2,j)=xyz(2,j)-yc
         xyz0(3,j)=xyz(3,j)-zc
      end do
c
c     Determine depth of immersion of peripheral protein
c     as maximal depth of its atoms
c
      dmax=0.
      d=0.5*dmembr
      do i=1,nat
         if(icurv.eq.1) then
            r=sqrt(xyz(1,i)*xyz(1,i)+xyz(2,i)*xyz(2,i)+
     *        xyz(3,i)*xyz(3,i))
            rc=sqrt(xc*xc+yc*yc+zc*zc)
         else
            z=xyz(3,i)
         end if
         if(icurv.eq.1) then
            if(rc.gt.radius) db=radius+d-r
            if(rc.le.radius) db=r-radius+d
         else
            if(zc.gt.0.) db=d-z
            if(zc.le.0.) db=d+z
         end if
         if(db.gt.dmembr) db=dmembr
         if(db.gt.dmax) dmax=db
      end do
c
c     2. Angle between inertia axis of the protein and Z axis
c     Choose an axis with minimal momentum
c
      tetamin=999.
      rmsdmin=99999.
      xmin=99.
      ymin=99.
      zmin=99.
      do teta=0.,90.,1.
         rteta=pi*teta/180.
         do phi=0.,359.,1.
            rphi=pi*phi/180.
            x=sin(rteta)*cos(rphi)
            y=sin(rteta)*sin(rphi)
            z=cos(rteta)
            rmsd=0.
            do j=1,nat
               a=xyz0(1,j)*y-xyz0(2,j)*x
               b=xyz0(2,j)*z-xyz0(3,j)*y
               c=xyz0(3,j)*x-xyz0(1,j)*z
               rmsd=rmsd+a*a+b*b+c*c
            end do
            rmsd=rmsd/float(nat)
            if(rmsd.lt.rmsdmin) then
               rmsdmin=rmsd
               tetamin=teta
               xmin=x        
               ymin=y        
               zmin=z        
            end if
c           write (*,'(2f8.0,f10.1)') teta,phi,rmsd
         end do
      end do
      r1=sqrt(xmin*xmin+ymin*ymin+zmin*zmin)
      r2=sqrt(xc*xc+yc*yc+zc*zc)
      rr=(xmin*xc+ymin*yc+zmin*zc)/(r1*r2)
      tetamin=(acos(rr)/pi)*180.
c     rmsdmin=sqrt(rmsdmin)
      return
      end
c
      subroutine project (nat,xyz0)
c     -----------------------------
c     Rotate the coordinate set to obtain the maximum
c     cross-section area in ZY plane, with the image tilted
c     in the right-upper direction
c
      parameter (maxat=200000)
c
      real xyz0(3,1),xyz(3,maxat)
      data pi/3.1459/
c
      smax=0.
      do phi=0.,359.,1.
         ang=(phi/180.)*pi
         co=cos(ang)
         si=sin(ang)
         do i=1,nat
            xyz(1,i)=co*xyz0(1,i)-si*xyz0(2,i)
            xyz(2,i)=si*xyz0(1,i)+co*xyz0(2,i)
            xyz(3,i)=xyz0(3,i)
         end do
         yzmin=1000.
         ymin=1000.
         ymax=-1000.
         s=0.
         do zsl=-60.,60.,2. 
            zsl2=zsl+2.
            do i=1,nat
               if(xyz(3,i).gt.zsl.and.xyz(3,i).le.zsl2) then
                 if(xyz(1,i).lt.ymin) ymin=xyz(1,i)
                 if(xyz(1,i).gt.ymax) ymax=xyz(1,i)
               end if
            end do
            if(ymin.ne.1000.) then
               yzmax=ymax
               if(yzmin.eq.1000.) yzmin=ymin
               s=s+ymax-ymin
            end if
         end do
         if(s.gt.smax.and.yzmax.gt.yzmin) then
c        if(s.gt.smax) then
            smax=s
            phimax=phi
         end if
      end do
c
c     write (*,'(f7.1)') phimax
      ang=(phimax/180.)*pi
      co=cos(ang)
      si=sin(ang)
      do i=1,nat
         xyz(1,i)=co*xyz0(1,i)-si*xyz0(2,i)
         xyz(2,i)=si*xyz0(1,i)+co*xyz0(2,i)
         xyz(3,i)=xyz0(3,i)
      end do
      do i=1,nat
         xyz0(1,i)=xyz(1,i)
         xyz0(2,i)=xyz(2,i)
         xyz0(3,i)=xyz(3,i)
      end do
      return
      end
c
      subroutine depth_angle2 (nat1,xyz1,tetamin,
     *  dmembr,dmax,namat1,numres1,namsu,namesu,pdbtempl)
c     --------------------------------------------------
c     Determine tilt angle and maximal membrane penetration depth
c     for a protein with undefined secondary structure.
c     Tilt angle is the angle between protein inertia axis
c     and membrane normal (this is different from a protein with
c     defined TM secondary structure)
c
      parameter (maxat=200000,maxbur=2000)
c
      integer numbur(maxbur),numres(maxat),numres1(1)
      character*1 namsu(1),namesu,sbur(maxbur)
      character*4 namat(maxat),namat1(1)
      character*2000 string
      character*80 pdbtempl
      real xyz1(3,1),xyz0(3,maxat),xyz(3,maxat)
c
      data pi/3.14159/
c
c     Select atoms of given subunit
c
      m=0
      do i=1,nat1
         if(namsu(i).eq.namesu) then
            m=m+1
            namat(m)=namat1(i)
            numres(m)=numres1(i)
            xyz(1,m)=xyz1(1,i)
            xyz(2,m)=xyz1(2,i)
            xyz(3,m)=xyz1(3,i)
         end if
      end do
      nat=m
c
c     center of mass:
c
      xc=0.
      yc=0.
      zc=0.
      do j=1,nat
         xc=xc+xyz(1,j)
         yc=yc+xyz(2,j)
         zc=zc+xyz(3,j)
      end do
      xc=xc/float(nat)
      yc=yc/float(nat)
      zc=zc/float(nat)
      do j=1,nat
         xyz0(1,j)=xyz(1,j)-xc
         xyz0(2,j)=xyz(2,j)-yc
         xyz0(3,j)=xyz(3,j)-zc
      end do
c
c     Determine depth of immersion of peripheral protein
c     as maximal depth of its atoms
c
      dmax=0.
      d=0.5*dmembr
      mbur=0
      do i=1,nat
         z=xyz(3,i)
         if(z.ge.-d.and.z.le.d) then
            if(zc.gt.0.) db=d-z
            if(zc.le.0.) db=d+z
            if(db.gt.dmax) dmax=db
         end if
c
c        consider residue "buried in hydrocarbon core" if at least
c        one of its atoms buried 
c
         if(z.ge.-d.and.z.le.d) then
            if(mbur.ge.1) then
               if(numres(i).ne.numbur(mbur)) then
                  mbur=mbur+1
                  numbur(mbur)=numres(i)
               end if
            else
               mbur=mbur+1
               numbur(mbur)=numres(i)
            end if
         end if
         if(mbur.gt.maxbur) then
            write (*,'(''Too many membrane-embedded residues'',
     *        '' in protein'',a30)') pdbtempl(1:30)
            stop
         end if
      end do
      nbur=mbur
c
c     2. Angle between inertia axis of the protein and Z axis
c     Choose an axis with minimal momentum
c
      tetamin=999.
      rmsdmin=99999.
      do teta=0.,90.,1.
         rteta=pi*teta/180.
         do phi=0.,359.,1.
            rphi=pi*phi/180.
            x=sin(rteta)*cos(rphi)
            y=sin(rteta)*sin(rphi)
            z=cos(rteta)
            rmsd=0.
            do j=1,nat
               a=xyz0(1,j)*y-xyz0(2,j)*x
               b=xyz0(2,j)*z-xyz0(3,j)*y
               c=xyz0(3,j)*x-xyz0(1,j)*z
               rmsd=rmsd+a*a+b*b+c*c
            end do
            rmsd=rmsd/float(nat)
            if(rmsd.lt.rmsdmin) then
               rmsdmin=rmsd
               tetamin=teta
            end if
c           write (*,'(2f8.0,f10.1)') teta,phi,rmsd
         end do
      end do
c     rmsdmin=sqrt(rmsdmin)
c
c     3. Output of membrane-embedded residues
c
      if(nbur.eq.0) go to 10
      do i=1,maxbur
         string(i:i)=' '
      end do
      do i=1,nbur-1
         sbur(i)=','
         if(numbur(i+1).eq.numbur(i)+1) sbur(i)='-'
      end do
      sbur(nbur)=' '
c     do i=1,nbur
c        write (*,'(i4,1x,a1)') numbur(i),sbur(i)
c     end do
c
      call addnum (string,numbur(1),sbur(1))
      do i=2,nbur
         if(sbur(i-1).ne.'-'.or.sbur(i).ne.'-')
     *     call addnum (string,numbur(i),sbur(i))
      end do
      i1=index(string,' ')
      tetamin=abs(tetamin)
      isu=int(tetamin)
      write (*,'(''#'',a4,'';'',a1,'';'',i3,'';'',a)')
     * pdbtempl(1:4),namesu,isu,string(1:i1-1)
   10 continue
      return
      end
c
      subroutine addnum (string,num,sbur)
c     -----------------------------------
      character*2000 string
      character*1 sbur
      character*4 abc1,abc2 
c
      abc1=' '
      abc2=' '
      i1=index(string,' ')
      write (abc1,'(i4)') num
      m=0
      do i=1,4
         if(abc1(i:i).ne.' ') then
            m=m+1
            abc2(m:m)=abc1(i:i)
         end if
      end do
      string=string(1:i1-1)//abc2
      i1=index(string,' ')
      string=string(1:i1-1)//sbur
      return
      end
