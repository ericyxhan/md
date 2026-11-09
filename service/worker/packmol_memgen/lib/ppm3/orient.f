      subroutine orient (nat,xyz,solv,phimax,tetamax,v,
     *  dmax,zcenter,emin)
c     --------------------------------------------------
c     a preliminary approximate positioning of transmembrane protein in
c     membrane with simultaneous identification of lipid-facing residues
c    
      parameter (maxat=200000)
c
      real xyz(3,1),solv(1),v(3),xyzb(3,maxat)
c
      data step1/2./,step2/0.5/,step3/0.1/
c
c     Calculate center of masses and move coordinates
c
      do i=1,nat
         xyzb(1,i)=xyz(1,i) 
         xyzb(2,i)=xyz(2,i) 
         xyzb(3,i)=xyz(3,i) 
      end do
c
      v(1)=0.
      v(2)=0.
      v(3)=0.
      do i=1,nat
         do j=1,3
            v(j)=xyzb(j,i)+v(j)
         end do
      end do
      v(1)=v(1)/float(nat)
      v(2)=v(2)/float(nat)
      v(3)=v(3)/float(nat)
      do i=1,nat
         xyzb(1,i)=xyzb(1,i)-v(1)
         xyzb(2,i)=xyzb(2,i)-v(2)
         xyzb(3,i)=xyzb(3,i)-v(3)
      end do
c
c     4. Find optimal orientation (as defined by two angles)
c
      call optrot (0.,179.,step1,-90.,90.,step1,
     *  nat,xyzb,solv,phimax,tetamax,dmax,zcenter,emin)
      phi1=phimax-step1*2.
      phi2=phimax+step1*2.
      teta1=tetamax-step1*2.
      teta2=tetamax+step1*2.
      call optrot (phi1,phi2,step2,teta1,teta2,step2,
     *  nat,xyzb,solv,phimax,tetamax,dmax,zcenter,emin)
c     phi1=phimax-step2*2.
c     phi2=phimax+step2*2.
c     teta1=tetamax-step2*2.
c     teta2=tetamax+step2*2.
c     call optrot (phi1,phi2,step3,teta1,teta2,step3,
c    *  nat,xyzb,solv,phimax,tetamax,dmax,zcenter,emin)
      return
      end
c
      subroutine optrot (phi1,phi2,stepphi,teta1,teta2,stepteta,
     *  nat,xyzb,solv,phimax,tetamax,dmax,zcenter,emin)
c     ----------------------------------------------------------
c     Finding optimal rotation angles and thickness
c     The center of hydrophobic slab is moving within +-50 A from
c     the center of mass of protein
c
c     Hydrophobic thickness: from 14 to 37 A
c
c     This is true hydrophobic slab, without sigmoidal transition area
c
      parameter (maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real xyzb(1),asares(1),xyzc(3,maxat),eslice(1000),solv(1)
      integer ienvat(maxat)
c
      data pi/3.14159/
c
      alpha=1.11
      emin=100.
      do phi0=phi1,phi2,stepphi
         phi=phi0*pi/180.
         do teta0=teta1,teta2,stepteta
            teta=teta0*pi/180.
            call tilting (phi,teta,nat,xyzb,xyzc)
c           write (*,'(2f8.2)') phi0,teta0
            call rectang (nat,xyzc,ienvat,accs)
            nslice=281
            do i=1,nslice
               eslice(i)=0.
            end do
            do i=1,nat
               zc=xyzc(3,i)
               if(ienvat(i).eq.1.and.zc.gt.-140.) then
                  m=int(zc)+141.
                  eslice(m)=eslice(m)+solv(i)*accs(i)
               end if
            end do
c
            do nwind=18,40
               do i1=1,nslice-nwind
                  e=0. 
                  do j=i1,i1+nwind
                     e=e+eslice(j)
                  end do
                  if(e.lt.emin-0.01) then
                     emin=e
                     imin=i1
                     nwindmin=nwind
                     phimax=phi
                     tetamax=teta
                  end if
               end do
            end do
         end do
      end do
      dmax=float(nwindmin)
      zcenter=float(imin)-140.5+dmax/2.
      phimax=phimax*180./pi
      tetamax=tetamax*180./pi
      return
      end
c
      subroutine rectang (nat,xyz,ienvat,accs)
c     ---------------------------------------------------------
c     The procedure to identify lipid-facing atoms as proposed
c     by Tusnady
c 
c     envat(i) =1 - lipid-facing
c               0 - not
c
c     Commented out: untested version for more precise determination
c     of lipid-facing atoms by using rectangula mesh
c
      parameter (maxat=200000,maxatsl=5000,maxpnt=10000,
     *  maxpnt2=1000)
c
      integer ienvat(1),numat(maxatsl),matxy(maxpnt2,maxpnt2)
      real xyz(3,1),accs(1),xat(maxatsl),yat(maxatsl),
     * xb(maxpnt),yb(maxpnt)
c
      data zstep/1./,xstep/1.0/
c
      do i=1,nat
         ienvat(i)=0
      end do
c
c     For each slice:
c
      m=0
      do zsl=-140.,140.,zstep
         z1=zsl
         z2=zsl+zstep
c
c        1. Define boundary recatangle and the set
c        of atoms in the slice, with their x,y coordinates 
c        and numbers in the complete coordinate set
c
         m=0
         xmin0=1000.
         xmax0=-1000.
         ymin0=1000.
         ymax0=-1000.
         do i=1,nat
            x=xyz(1,i)
            y=xyz(2,i)
            z=xyz(3,i)
            if(z.gt.z1.and.z.le.z2.and.accs(i).gt.0.) then
               if(x.lt.xmin0) xmin0=x
               if(x.gt.xmax0) xmax0=x
               if(y.lt.ymin0) ymin0=y
               if(y.gt.ymax0) ymax0=y
               m=m+1
               if(m.gt.maxatsl) then
                  write (*,'(''Too many boundary rectangle atoms'')') 
                  stop
               end if
               numat(m)=i
               xat(m)=x
               yat(m)=y
            end if
         end do
         natsl=m
c        write (*,'(i8)') natsl
         xmin=xmin0-1.
         xmax=xmax0+1.
         ymin=ymin0-1.
         ymax=ymax0+1.
c
c        2. Determine continuous arrays of x,y coordinates  
c        for boundary dummy atoms
c
         xm=5.*xstep
         if(natsl.gt.3.and.xmax0-xmin0.gt.xm.and.
     *     ymax0-ymin0.gt.xm) then
c
c           Move set of xy coordinates
c
c           do i=1,natsl
c              xat(i)=xat(i)-xmin
c              yat(i)=yat(i)-ymin
c           end do
c           xmax=xmax0-xmin0+1.
c           ymax=ymax0-ymin0+1.
c           xmin=1.
c           ymin=1.
c
c           determine matrix
c
c           do i=1,maxpnt2
c              do j=1,maxpnt2
c                 matxy(i,j)=0
c              end do
c           end do
c           do i=1,natsl
c              ix=int(xat(i))
c              iy=int(yat(i))
c              if(ix.gt.maxpnt2.or.iy.gt.maxpnt2) then
c                 write (*,'(''Too many atoms in coordinate matrix'')')
c                 stop
c              end if
c              matxy(ix,iy)=1
c           end do
c
c           determine boundary atoms
c
            m=0
            do xc=xmin,xmax,xstep
               m=m+1
               xb(m)=xc
               yb(m)=ymin 
c
c              ix=int(xc)
c              do yc=ymin,ymax,xstep
c                 iy=int(yc)
c                 if(matxy(ix,iy+1).eq.1) then
c                    yb(m)=yc
c                    go to 10
c                 end if
c              end do
c  10          continue
c
               m=m+1
               if(m.gt.maxpnt) then
                  write (*,'(''Too many boundary dummy atoms'')')
                  stop
               end if
               xb(m)=xc
               yb(m)=ymax 
c
c              do yc=ymin,ymax,xstep
c                 iy=int(yc)
c                 if(matxy(ix,iy).eq.1.and.
c    *              matxy(ix,iy+1).eq.0) yb(m)=yc
c              end do
c
            end do
            ym1=ymin+xstep
            ym2=ymax-xstep
            do yc=ym1,ym2,xstep
               m=m+1
               xb(m)=xmin 
               yb(m)=yc
c
c              iy=int(yc)
c              do xc=xmin,xmax,xstep
c                 ix=int(xc)
c                 if(matxy(ix+1,iy).eq.1) then
c                    xb(m)=xc
c                    go to 20
c                 end if
c              end do
c  20          continue
c
               m=m+1
               if(m.gt.maxpnt) then
                  write (*,'(''Too many boundary dummy atoms'')')
                  stop
               end if
               xb(m)=xmax 
               yb(m)=yc
c
c              do xc=xmin,xmax,xstep
c                 ix=int(xc)
c                 if(matxy(ix,iy).eq.1.and.
c    *              matxy(ix+1,iy).eq.0) xb(m)=xc
c              end do
            end do
            npoint=m
c
c           Move boundary atoms back
c
c           xmax=xmax0
c           xmin=xmin0
c           ymax=ymax0
c           ymin=ymin0
c           do i=1,npoint
c              xb(i)=xb(i)+xmin
c              yb(i)=yb(i)+ymin
c           end do
c
c           3. Determine the atom closest to each boundary atom
c
            do k=1,npoint
               num=0
               dmin=1000000.
               do j=1,natsl
                  a=xat(j)-xb(k)
                  b=yat(j)-yb(k)
                  d=a*a+b*b
                  if(d.lt.dmin) then
                     dmin=d
                     num=numat(j)
                  end if
               end do
               if(num.eq.0) then
                  write (*,'(''!'')') 
                  stop
               end if
               ienvat(num)=1
            end do
         end if
      end do
      return
      end 
