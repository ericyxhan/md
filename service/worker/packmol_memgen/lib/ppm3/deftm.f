      subroutine deftm (nres,ifirst,ilast,nsegm,namsegm,isegm,nat,xyz,
     *  dmembr,numres,namsu,iprint,namat,xyzca,ienvat,
     * solv,pdbtempl,tiltot,icurv,radius)
c     ------------------------------------------------------------
c     Setermine borders of TM segments
c
      parameter (maxres=30000,maxsegm=900,maxlen=65,maxsub=95,
     *  maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      character*4 namat(1)
      character*80 pdbtempl
      character*600 string0
c
      real xyz(3,1),xyzca(3,maxsegm,1),tilthel(maxsegm),asatm(maxsegm),
     *  solv(1),tiltsu(maxsegm)
c
      integer ifirst(1),ilast(1),isegm(2,1),ilip(maxres),
     *  numtm(2,maxsegm),numtmbuf(2,maxsegm),numres(1),ienvat(1),
     *  natstm(maxsegm),num1(maxsub),num2(maxsub)
c
      character*1 namsegm(1),namsu(1),namtm(maxsegm),
     *  namtmbuf(maxsegm),namesu(maxsub)
c
      data cutin /0.20/
c
      alpha=1.11
      dmem=(dmembr+0.8)/2.
      do i=1,nres
         ilip(i)=0
         nin=0
         do j=ifirst(i),ilast(i)
            if(icurv.eq.1) then
               dr=sqrt(xyz(1,j)*xyz(1,j)+xyz(2,j)*xyz(2,j)+
     *           xyz(3,j)*xyz(3,j))-radius
               if(dr.ge.-dmem.and.dr.le.dmem) then
                  nin=nin+1
                  if(namat(j).eq.'CA  ') ilip(i)=1
               end if
            else 
               if(xyz(3,j).ge.-dmem.and.xyz(3,j).le.dmem) then
                  nin=nin+1
                  if(namat(j).eq.'CA  ') ilip(i)=1
               end if
            end if
         end do
         if(float(nin)/float(ilast(i)-ifirst(i)+1).gt.cutin) ilip(i)=1
      end do
c
      ilip(1)=0
      ilip(nres)=0
      do i=2,nres
         if(namsu(ifirst(i)).ne.namsu(ifirst(i-1))) then
            ilip(i-1)=0
            ilip(i)=0
         end if
      end do
c
      do i=4,nres
         do j=1,i-2
            if(namsu(ifirst(i)).eq.namsu(ifirst(j)).and.
     *         namsu(ifirst(j)).ne.namsu(ifirst(j+1))) then
               ilip(i)=0 
               go to 5
            end if
         end do
    5    continue
      end do
c
      ntm=0
      do i=2,nres
         if(namsu(ifirst(i)).eq.namsu(ifirst(i-1))) then
            if(ilip(i).eq.1.and.ilip(i-1).eq.0) then
               ntm=ntm+1
               if(ntm.ge.maxsegm) then
                  write (*,'(''Too many potential '',
     *              ''TM segments'')')
                  stop
               end if
               namtm(ntm)=namsu(ifirst(i))
               numtm(1,ntm)=numres(ifirst(i))
            end if
            if(ilip(i).eq.0.and.ilip(i-1).eq.1) 
     *        numtm(2,ntm)=numres(ifirst(i-1))
         end if
      end do
      if(iprint.ge.2) then
         write (*,'(''deftm:'')')
         do i=1,nres
            write (*,'(4i5,1x,a1)') i,ilip(i),numres(ifirst(i)),
     *        numres(ilast(i)),namsu(ifirst(i))
         end do
      end if
c
      if(iprint.ge.2) then
         write (*,'('' '')')
         do i=1,ntm
            write (*,'(1x,i5,1x,a1,2i5)') i,namtm(i),(numtm(j,i),j=1,2)
         end do
      end if
      m=0
      do i=1,ntm
         if(numtm(2,i)-numtm(1,i).ge.3) then
            m=m+1
            numtm(1,m)=numtm(1,i)
            numtm(2,m)=numtm(2,i)
            namtm(m)=namtm(i)
         end if
      end do
      ntm=m
      if(iprint.ge.2) then
         write (*,'('' '')')
         do i=1,ntm
            write (*,'(1x,i5,1x,a1,2i5)') i,namtm(i),(numtm(j,i),j=1,2)
         end do
      end if
c
c     For each secondary structure, determine the corresponding
c     transmembrane segment with maximal overlap:
c
c     do i=1,nsegm
c        write (*,'(''S.s. '',a1,2i5)')
c    *     namsegm(i),isegm(1,i),isegm(2,i)
c     end do
      m=0
      do i=1,nsegm
         maxover=3
         do j=1,ntm
            if(namtm(j).eq.namsegm(i)) then
               i1=max(isegm(1,i),numtm(1,j))
               i2=min(isegm(2,i),numtm(2,j))
               lover=i2-i1+1
               if(lover.gt.maxover) then
                  maxover=lover
                  jmem=j
                  m=m+1
                  numtmbuf(1,m)=max(isegm(1,i),numtm(1,jmem))
                  numtmbuf(2,m)=min(isegm(2,i),numtm(2,jmem))
                  namtmbuf(m)=namtm(jmem)
c                 write (*,'(''Sec str: '',a1,2i5)')
c    *              namsegm(i),isegm(1,i),isegm(2,i)
               end if
            end if
         end do
         if(maxover.eq.3) then 
            write (*,'(''Secondary structure  '',a1,2i4,
     *        '' has no TM segment'')') namsegm(i),isegm(1,i),
     *        isegm(2,i)
         end if
      end do
      ntm=m
      if(ntm.eq.0) then
         nsegm=0
         return
      end if
      do i=1,ntm
         numtm(1,i)=numtmbuf(1,i)
         numtm(2,i)=numtmbuf(2,i)
         namtm(i)=namtmbuf(i)
      end do
      do i=1,ntm
         write (41,'(a1,2i4)') namtm(i),numtm(1,i),numtm(2,i)
c        write (*,'(a1,2i4)') namtm(i),numtm(1,i),numtm(2,i)
      end do
c
c     Select coordinates of CA-atoms of TM helices
c
      do i=1,ntm
         natstm(i)=numtm(2,i)-numtm(1,i)+1
         asatm(i)=0.
         m=0
         do j=numtm(1,i),numtm(2,i)
            do k=1,nat
               if(namsu(k).eq.namtm(i)) then
                  if(numres(k).eq.j) then
c                    if(ienvat(k).eq.1) asatm(i)=asatm(i)+accs(k)
                     if(accs(k).gt.0.) then
                        zc=xyz(3,k)
                        al=alpha*(abs(zc)-dmem)
                        c=1./(1.+exp(al))
                        asatm(i)=asatm(i)+c*accs(k)*solv(k)
                     end if
                     if(namat(k).eq.'CA  ') then
                        m=m+1
                        if(m.gt.natstm(i)) then
                           write (*,'(''Problem with definition of '',
     *                       ''sec. structure'',a2,3i5)') namtm(i),
     *                       (numtm(l,i),l=1,2),m
                           write (*,'(''Check residue numbering in '',
     *                       ''PDB file'')')
                           go to 10
                        end if
                        if(m.gt.maxlen) then
                           write (*,'(''Too many residues in helix'',
     *                      a2,2i5)') namtm(i),(numtm(l,i),l=1,2)
                           stop
                        end if
                        xyzca(1,i,m)=xyz(1,k)
                        xyzca(2,i,m)=xyz(2,k)
                        xyzca(3,i,m)=xyz(3,k)
                     end if
                  end if
               end if
            end do
         end do
   10    continue
      end do
c
c     Define list of names of subunits:
c
      namesu(1)=namtm(1)
      nsu=1
      do i=2,ntm
         if(namtm(i).ne.namtm(i-1)) then
            nsu=nsu+1
            namesu(nsu)=namtm(i)
         end if
      end do
c
c     determine tilt angles (relative to the membrane plane)
c     of the transmembrane segments - for individual helices and
c     entire alpha-bundle
c
      call deftilts (xyzca,ntm,natstm,namtm,tilthel,tiltsu,
     *  tiltot,iprint,nsu,namesu,pdbtempl)
c
      sum=0.
      do i=1,ntm
         if(tilthel(i).gt.90.) tilthel(i)=180.-tilthel(i)
         write (*,'(a1,2i4,f7.0,f7.1)') namtm(i),numtm(1,i),
     *     numtm(2,i),tilthel(i),asatm(i)
         sum=sum+asatm(i)
      end do
      write (*,'(''TMH contribution:'',f8.1)') sum
      if(nsu.gt.1) then
         do i=1,nsu
            if(tiltsu(i).gt.90.) tiltsu(i)=180.-tiltsu(i)
            write (*,'(''Subunit '',a1,f7.0)') namesu(i),tiltsu(i)
         end do
      end if
      if(tiltot.gt.90.) tiltot=180.-tiltot
      write (*,'(''Tilt angle:'',f7.1)') tiltot
c
      do l=1,nsu
         ns=0
         do i=1,ntm
            if(namtm(i).eq.namesu(l)) then
               ns=ns+1
               num1(ns)=numtm(1,i)
               num2(ns)=numtm(2,i)
            end if
         end do
         isu=int(tiltsu(l))
         write (string0,'(a14,'';'',a1,'';'',
     *     i2,'';'',40(i2,''('',i4,''-'',i4,''),''))')
     *     pdbtempl(1:14),namesu(l),isu,(m,num1(m),num2(m),m=1,ns)
         ind0=index(string0,',    ')
         write (23,'(a)') string0(1:ind0-1)
      end do
      return
      end
c
      subroutine deftilts (xyz,nsegm,natsegm,namsegm,tilthel,
     *  tiltsu,tiltot,iprint,nsu,namesu,pdbtempl)
c     ---------------------------------------------------------
c     determine tilt angles (relative to the membrane plane)
c     for transmembrane segments of individual helices and  
c     entire alpha-bundle
c
c     'xyz' are CA-atom coordinates of TM segments
c     nat - number of CA-atoms
c
      parameter (maxsegm=900,maxlen=65)
c
      character*1 namsegm(1),namesu(1)
      character*80 pdbtempl,vectpdb
c
      real xyz(3,maxsegm,1),vs(3,maxsegm),v(3),xyzs(3,maxlen),
     * xyzc(3,maxlen),vc(3),vt(3),tilthel(1),tiltsu(1),
     * vect(3,maxsegm),v1(3),v2(3)
c
      integer natsegm(1)
c
      data eps/0.001/,maxiter/99/,pi/3.14159/
c
      if(iprint.ge.2) then
         i1=index(pdbtempl,'.pdb')-1
         vectpdb=pdbtempl(1:i1)//'vect.pdb'
      end if
c
c     1. Re-determine axes of helices using only their TM segments
c
      do l=1,nsegm
c
c        Center of the helix:
c
         do j=1,3
            vt(j)=0.
         end do
         do i=1,natsegm(l)
            do j=1,3
               vt(j)=vt(j)+xyz(j,l,i)
            end do
         end do
         do j=1,3
            vt(j)=vt(j)/float(natsegm(l))
         end do
c
c        Helix vector:
c
         do k=1,3
            v1(k)=0.
            v2(k)=0.
         end do
         nref=7
         ll=natsegm(l)
         if(ll.ge.7.and.ll.le.15) nref=4
         if(ll.ge.5.and.ll.le.6) nref=3
         if(ll.le.4) then
            do k=1,3
               vs(k,i)=xyz(k,i,ll)-xyz(k,i,1)
            end do
         else  
            do j=1,nref
               nn=natsegm(l)-nref+j
               do k=1,3
                  v1(k)=v1(k)+xyz(k,l,j)
                  v2(k)=v2(k)+xyz(k,l,nn)
               end do
            end do
            do k=1,3
               v1(k)=v1(k)/float(nref)   
               v2(k)=v2(k)/float(nref)   
               vs(k,l)=v2(k)-v1(k)
            end do
         end if  
         r=sqrt(vs(1,l)**2+vs(2,l)**2+vs(3,l)**2)
         do k=1,3
            vs(k,l)=vs(k,l)/r
         end do
c
         tilthel(l)=180.*acos(vs(3,l))/pi
      end do
c
c     Choose signs of helix vectors 
c
      do i=1,nsegm
         if(vs(3,i).lt.0.) then
            do k=1,3
               vs(k,i)=-vs(k,i)
            end do
         end if
      end do
c
c     Vector of alpha-bundle:
c
      do k=1,3
         v(k)=0.
      end do
      do i=1,nsegm
         do k=1,3
            v(k)=v(k)+vs(k,i)
         end do
      end do
      rn=sqrt(v(1)*v(1)+v(2)*v(2)+v(3)*v(3))
      tiltot=180.*acos(v(3)/rn)/pi
c
c     Vectors for PDB subunits:
c
      do j=1,nsu
         do k=1,3
            vect(k,j)=0.
         end do
      end do
      do i=1,nsegm
         do j=1,nsu
            if(namsegm(i).eq.namesu(j)) then
               do k=1,3
                  vect(k,j)=vect(k,j)+vs(k,i)
               end do
            end if
         end do
      end do
      do m=1,nsu
         rn=sqrt(vect(1,m)**2+vect(2,m)**2+vect(3,m)**2)
         tiltsu(m)=180.*acos(vect(3,m)/rn)/pi
      end do
      return
      end
