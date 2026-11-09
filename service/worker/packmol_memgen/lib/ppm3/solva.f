      subroutine solva(nats,xyz,rads,accs,probe,zslice)
c     ------------------------------------------------
c ncube = maximum number of cubes allowed for placing of atoms
c nac   = maximum number of atoms per cube
c nint  = maximum number of sphere intersections
c
      integer     ncube,nac,nint
      parameter (ncube=1700000,nac=250,nint=3000,maxs=200000)
c
c     the following are dimensioned to the max no of atoms (maxs)
c
      integer cube(maxs)
      real    xyz(maxs,3),
     -        rads(maxs),
     -        rad(maxs),
     -        radsq(maxs) 
c     
c     the following are dimensioned to the max no of intersections
c     of neighbouring spheres (nint)
c     
      dimension
     -        inov(nint),
     -        tag(nint),
     -        arci(nint),
     -        arcf(nint),
     -        dx(nint),
     -        dy(nint),
     -        d(nint),
     -        dsq(nint)
c
      integer    natm(nac,ncube), 
     -           itab(ncube)
      integer    nats, tag    
      real       probe, zslice, accs(maxs), b
      real       trig_test
c
      data xmin,ymin,zmin,xmax,ymax,zmax/3*9999.,3*-9999./
c
c     initialise variables, constants
c
      ict=nint
      pi=acos(-1.0)
      pix2=2.0*pi
c
c     -- Radius of an atom sphere = atom radius + probe radius
c     -- Find maxima and minima
c
      rmax=0.0
      karc=ict
      do i = 1, nats
         rad(i)   = rads(i) + probe
         radsq(i) = rad(i)**2
         if (rad(i).gt.rmax)rmax = rad(i)
         if (xmin.gt.xyz(i,1))  xmin = xyz(i,1)
         if (ymin.gt.xyz(i,2))  ymin = xyz(i,2)
         if (zmin.gt.xyz(i,3))  zmin = xyz(i,3)
         if (xmax.lt.xyz(i,1))  xmax = xyz(i,1)
         if (ymax.lt.xyz(i,2))  ymax = xyz(i,2)
         if (zmax.lt.xyz(i,3))  zmax = xyz(i,3)
      enddo
c
c     rmax = max diameter
c
      rmax = rmax*2.
c
c     -- Cubicals containing the atoms are setup. 
c     -- The dimension of an edge equals the largest atom sphere radius
c     -- The cubes have a single index
c     -- Minimum of 3 by 3 cubic grid
c     -- EXIT if max cubes exceeded
c
      idim=(xmax-xmin)/rmax+1.
      if(idim.lt.3)idim=3
      jidim=(ymax-ymin)/rmax+1.
      if(jidim.lt.3)jidim=3
      jidim=idim*jidim
      kjidim=(zmax-zmin)/rmax+1.
      if(kjidim.lt.3)kjidim=3
      kjidim=jidim*kjidim
      if(kjidim.gt.ncube)STOP'SOLVA_ERROR: max cubes exceeded'
c
c     -- Prepare upto ncube cubes each containing upto nac atoms. The cube index
c     -- is kji. The atom index for each cube is in itab
c
      do l = 1, ncube
         itab(l)=0
      enddo
      do l = 1, nats
         i = (xyz(l,1)-xmin)/rmax+1.
         j = (xyz(l,2)-ymin)/rmax
         k = (xyz(l,3)-zmin)/rmax
         kji = k*jidim + j*idim+i
         n = itab(kji)+1
         if(n.gt.nac)STOP'SOLVA_ERROR: max atoms per cube exceeded'
         itab(kji) = n
         natm(n,kji) = l
         cube(l) = kji
      enddo
c
c     -- Process each atom in turn
c
      nzp=1./zslice+0.5
      do  ir = 1, nats
         kji=cube(ir)
         io=0
         area=0.
         xr=xyz(ir,1)
         yr=xyz(ir,2)
         zr=xyz(ir,3)
         rr=rad(ir)
         rrx2=rr*2.
         rrsq=radsq(ir)
c
c     -- Find the 'mkji' cubes neighboring the kji cube
c
         do k = -1, 1, 1
            do j = -1, 1, 1
               do i = -1, 1, 1
                  mkji=kji+k*jidim+j*idim+i
                  if(mkji.ge.1)then
                     if(mkji.gt.kjidim)goto14
                     nm=itab(mkji)
                     if(nm.ge.1)then
c     
c     -- record the atoms in inov that neighbor atom ir
c
                        do m = 1, nm
                           in=natm(m,mkji)
                           if (in.ne.ir)then
                              io=io+1
                              if (io.gt.ict)then
                                 STOP'SOLVA_ERROR: intrsctns > max'
                              endif
                              dx(io)=xr-xyz(in,1)
                              dy(io)=yr-xyz(in,2)
                              dsq(io)=dx(io)**2+dy(io)**2
                              d(io)=sqrt(dsq(io))
                              inov(io)=in
                           endif
                        enddo
                     endif
                  endif
               enddo
            enddo
         enddo
c
 14      if(io.ge.1)then
c     
c     z resolution determined
c     
            zres=rrx2/nzp
            zgrid=xyz(ir,3)-rr-zres/2.            
         else
            area=pix2*rrx2
            goto 18
         endif
c     
c     section atom spheres perpendicular to the z axis
c
         do i = 1, nzp
            zgrid=zgrid+zres
c
c     find the radius of the circle of intersection of 
c     the ir sphere on the current z-plane
c
            rsec2r=rrsq-(zgrid-zr)**2
            rsecr=sqrt(rsec2r)
            do k = 1, karc
               arci(k)=0.0
            enddo
            karc=0
            do j = 1, io
               in=inov(j)
c     
c     find radius of circle locus
c     
               rsec2n=radsq(in)-(zgrid-xyz(in,3))**2
               if (rsec2n.le.0.0) goto10
               rsecn=sqrt(rsec2n)
c
c     find intersections of n.circles with ir circles in section
c
               if (d(j).ge.rsecr+rsecn) goto10
c
c     do the circles intersect, or is one circle completely inside the other?
c
               b=rsecr-rsecn
               if (d(j).gt.abs(b)) goto20
               if (b.le.0.0) goto9
               goto10
c
c     if the circles intersect, find the points of intersection
c
 20            karc=karc+1
               if(karc.ge.ict)then
                  STOP'SOLVA_ERROR: max intersections exceeded2'
               endif
c
c     Initial and final arc endpoints are found for the ir circle intersected
c     by a neighboring circle contained in the same plane. The initial endpoint
c     of the enclosed arc is stored in arci, and the final arc in arcf
c     law of cosines
c     
               trig_test=(dsq(j)+rsec2r-rsec2n)/(2.*d(j)*rsecr)
               if(trig_test.ge.1.0)trig_test=0.99999
               if(trig_test.le.-1.0)trig_test=-0.99999
               alpha=acos(trig_test)
c     
c     alpha is the angle between a line containing a point of intersection and
c     the reference circle center and the line containing both circle centers
c     
               beta=atan2(dy(j),dx(j))+pi
c     
c     beta is the angle between the line containing both circle centers and the x-axis
c     
               ti=beta-alpha
               tf=beta+alpha
               if(ti.lt.0.0)ti=ti+pix2
               if(tf.gt.pix2)tf=tf-pix2
               arci(karc)=ti
               if(tf.ge.ti)go to 3
c     
c     if the arc crosses zero, then it is broken into two segments.
c     the first ends at pix2 and the second begins at zero
c     
               arcf(karc)=pix2
               karc=karc+1
 3             arcf(karc)=tf
 10         enddo
c
c     find the accessible surface area for the sphere ir on this section
c     
            if(karc.ne.0)goto19
            arcsum=pix2
            go to 25
c     
c     The arc endpoints are sorted on the value of the initial arc endpoint
c
 19         call sortag(arci(1),karc,tag)
c
c***************************************
c     calculate the accessible area
c***************************************
c     
            arcsum=arci(1)
            t=arcf(tag(1))
            if(karc.eq.1) go to 11
            do k = 2, karc
               if(t.lt.arci(k))arcsum=arcsum+arci(k)-t
               tt=arcf(tag(k))
               if(tt.gt.t)t=tt
            enddo
 11         arcsum=arcsum+pix2-t
c     
c     The area/radius is equal to the accessible arc length x the section thickness.
c     
 25         parea=arcsum*zres
c     
c     Add the accessible area for this atom in this section to the area for this
c     atom for all the section encountered thus far
c     
            area=area+parea
 9       enddo
c     
c     scale area to vdw shell
c     
 18      b=area*rr
         accs(ir)=b
c------------------------------------------------------------------
c The following line converts from accessible to contact surface
c         c=(b*(rad(ir)-probe)**2)/(rad(ir)**2)
c------------------------------------------------------------------     
      enddo
c
      write(4,'(a)')' SOLVA: PROGRAM ENDS CORRECTLY'
      return
      end
c
      subroutine sortag(a,n,tag)
      integer tag,tg
      dimension a(n),iu(16),il(16),tag(n)
      do i = 1, n
         tag(i)=i
      enddo
      m=1
      i=1
      j=n
 5    if(i.ge.j) go to 70
 10   k=i
      ij=(j+i)/2
      t=a(ij)
      if(a(i).le.t) go to 20
      a(ij)= a(i)
      a(i)=t
      t=a(ij)
      tg=tag(ij)
      tag(ij)=tag(i)
      tag(i)=tg
 20   l=j
      if(a(j).ge.t) go to 40
      a(ij)=a(j)
      a(j)=t
      t=a(ij)
      tg=tag(ij)
      tag(ij)=tag(j)
      tag(j)=tg
      if(a(i).le.t) go to 40
      a(ij)=a(i)
      a(i)=t
      t=a(ij)
      tg=tag(ij)
      tag(ij)=tag(i)
      tag(i)=tg
      go to 40
 30   a(l)=a(k)
      a(k)=tt
      tg=tag(l)
      tag(l)=tag(k)
      tag(k)=tg
 40   l=l-1
      if(a(l).gt.t) go to 40
      tt=a(l)
 50   k=k+1
      if(a(k).lt.t) go to 50
      if(k.le.l) go to 30
      if(l-i.le.j-k) go to 60
      il(m)=i
      iu(m)=l
      i=k
      m=m+1
      go to 80
 60   il(m)=k
      iu(m)=j
      j=l
      m=m+1
      go to 80
 70   m=m-1
      if(m.eq.0) return
      i=il(m)
      j=iu(m)
 80   if(j-i.ge.1) go to 10
      if(i.eq.1) go to 5
      i=i-1
 90   i=i+1
      if(i.eq.j) go to 70
      t=a(i+1)
      if(a(i).le.t) go to 90
      tg=tag(i+1)
      k=i
 100  a(k+1)=a(k)
      tag(k+1)=tag(k)
      k=k-1
      if(t.lt.a(k)) go to 100
      a(k+1)=t
      tag(k+1)=tg
      go to 90
      end
