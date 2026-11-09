      subroutine find_segm (nat,xyz,xyzca,numres,namat,namsu,
     *  namres,nsegm,isegm,namsegm,natsegm,dmax,itypess,icurv,radius)
c     -------------------------------------------------------------
c     Finding TM SS segments for a protein complex oriented in
c     the membrane coordinate system (z is membrane normal; z=0
c     in the center of membrane; +-dmax is hydrophobic thickness)
c
c     Sequential secondary structures of the same type and with the
c     same overall direction (with regard to memebrane normal)
c     are joined together if without gaps. Lengths of beta-strands 
c     can be overestimated because H-bonds were not used
c     for assignment of secondary structure.
c
c     TM SS may be shortened to avoid gaps and insertion within
c     secondary structures
c
c     TM SS are symmetrized for subunits with identical sequences
c     in secondary structures with identical residue numbers
c
c     Surface and re-entrance helices are excluded unless they
c     come close to the center of membrane
c
c     Note: secondary structures of water-soluble plug domains
c     of beta-barrels are currently included
c
c     itypess = 1 - TM alpha-helical protein
c               2 - TM beta-sheet protein
c
      parameter (maxsegm=900,maxca=30000,maxlen=65)
      real xyz(3,1),xyzca(3,maxsegm,1),xyzcat(3,maxca),
     * xyz_alpha(3,5)/-11.50,-25.51,38.97, -11.19,-29.01,37.46,
     * -14.98,-29.43,37.13, -15.16,-25.98,35.48, -12.41,-26.78,33.02/,
     * xyz_beta(3,4)/11.15,-5.95,35.67, 8.87,-4.99,32.80,
     * 8.08,-1.77,30.98, 6.11,-0.44,28.04/,xyz_310(3,4)/
     *-11.30,16.98,14.75,-7.54,17.47,15.21,
     *  -7.70,14.79,17.91,-8.91,12.28,15.29/
c
      integer numres(1),isegm(2,1),natsegm(1),itype(maxsegm),
     * icur(maxsegm),nwindcur(maxsegm),indca(maxca),
     * idirect(maxca),itopol(maxca),isecstr(maxca),numca(maxca),
     *numss(maxsegm,maxlen),itopss(maxsegm,maxlen),isecstr2(maxca)
c
      character*1 namsegm(1),namsu(1),namsuca(maxca),sucur
      character*4 namat(1),namres(1),seqca(maxca),seqss(maxsegm,maxlen)
c
      data dsurf/9./
c
c     idirect(i)= 0  - undefined
c                 1  +z
c                -1  -z
c     isecstr(i)= 0  - non-regular structure
c                 1  - alpha-helix
c                 2  - beta-sheet
c     itopol(i)=  0  - outside hydrophobic boundary
c                 1  - inside
c
      itypess=1
c
c     1. Prepare set of CA atoms with corresponding names of subunits
c
      m=0
      do i=1,nat
         if(namat(i).eq.'CA  ') then
            m=m+1
            if(m.gt.maxca) then
               write (*,'(''Too many CA atoms'')')
               stop
            end if
            xyzcat(1,m)=xyz(1,i)
            xyzcat(2,m)=xyz(2,i)
            xyzcat(3,m)=xyz(3,i)
            namsuca(m)=namsu(i)
            numca(m)=numres(i)
            seqca(m)=namres(i)
         end if
      end do
      nca=m
      if(nca.le.5) then
         nsegm=0
         go to 999
      end if
c
c     2. Superimpose each segment of the complex with beta-strand or
c     alpha-helix turn. If rmsd<rmsdmax, mark ALL residues of the segment
c     as alpha-helical or beta-strand, define +- dierction of the whole 
c     segment with respect to membrane normal, and mark resues of the
c     segment within hydrophobic boundaries.
c
c     The helices and strands will be broken at kinks, alpha-aneurisms,
c     beta-bulges or other irregularities, but treated as a single
c     helix/strand if without gaps (one residue gap can be allowed - check).
c
      thick=0.5*dmax
      do i=1,nca
         indca(i)=1
         idirect(i)=0
         isecstr(i)=0
         itopol(i)=0
         if(icurv.eq.1) then
            dr=abs(sqrt(xyzcat(1,i)*xyzcat(1,i)+
     *        xyzcat(2,i)*xyzcat(2,i)+xyzcat(3,i)*xyzcat(3,i))-radius)
         else
            dr=abs(xyzcat(3,i))
         end if
         if(dr.le.thick+3.) itopol(i)=1
      end do
c
c     3. Map secondary structure, including its direction and location
c     within the hydrocarbon core boundaries
c
      do i=1,nca
c        write (*,'(i5)') i
         n1=i-2
         n2=i+2
         if(i.lt.3) then
            n1=i
            n2=min(i+4,nca)
         end if
         if(i.gt.nres-2) then
            n1=max(i-4,1)
            n2=i
         end if
         if(namsuca(n1).ne.namsuca(i)) then
            n1=i
            n2=i+2
         end if
         if(namsuca(n2).ne.namsuca(i)) then
            n1=i-2
            n2=i
         end if
         dz=xyzcat(3,n2)-xyzcat(3,n1)
         if(dz.gt.0.) then
            idirect(i)=1
         else
            idirect(i)=-1
         end if
      end do
c
      call mapss(nca,xyzcat,4,xyz_beta,dmax,namsuca,numca,isecstr,
     *  idirect,itopol,2)
      call mapss(nca,xyzcat,5,xyz_alpha,dmax,namsuca,numca,isecstr,
     *  idirect,itopol,1)
      call mapss(nca,xyzcat,4,xyz_310,dmax,namsuca,numca,isecstr,
     *  idirect,itopol,1)
c
c     remove 1st and last residues from secondary structure segments
c
      isecstr(1)=0
      isecstr(nca)=0
      do i=2,nca-1
         if(namsuca(i-1).ne.namsuca(i)) isecstr(i)=0
         if(namsuca(i+1).ne.namsuca(i)) isecstr(i)=0
      end do
      do i=1,nca
         isecstr2(i)=isecstr(i)
      end do
      do i=2,nca-1
         if(isecstr(i-1).ne.isecstr(i)) isecstr2(i)=0
         if(isecstr(i+1).ne.isecstr(i)) isecstr2(i)=0
      end do
      do i=1,nca
         isecstr(i)=isecstr2(i)
      end do
c
c     do i=1,nca
c        write (*,'(a1,i5,i2,i3,i2)') namsuca(i),
c    *     numca(i),isecstr(i),idirect(i),itopol(i)
c     end do
c
c     4. Determine secondary structuires as continuous sequences of
c     residues which satisfy the following conditions:
c     1. All ot them are either alpha or beta, as defined by 'isecstr'
c     2. All of them have the same "direction", as defined by 'idirect'
c     3. All of them belong to the same subunit, as defined by 'namsuca'
c     4. At least 4 beta-sstrand residues or at least 8 alpha-helix
c        residues are within the hydrocarbon boundaries, as deined by 
c        'itopol'
c
      m=0
      iprin=0
      do nwind=60,5,-1
         do i1=1,nca-nwind+1
            sucur=namsuca(i1)
            idir=idirect(i1)
            isec=isecstr(i1)
            if(isec.eq.0.or.idir.eq.0.or.indca(i1).eq.0) go to 10
            ntop=0
            do j=i1+1,i1+nwind-1
               if(sucur.ne.namsuca(j).or.
     *            idir.ne.idirect(j).or.
     *            isec.ne.isecstr(j).or.indca(j).eq.0) go to 10
               if(itopol(j).eq.1) ntop=ntop+1
               if(numca(j).ne.numca(j-1)+1) then
                  if(iprin.eq.0) then
                     write (*,'(''non-sequential residue numbering or'',
     *                 '' gaps in TM sec. struct. '',a1,i5)')
     *                 namsuca(j),numca(j)
                     write(*,'(''this sec.struct. may be shortened'')')
                     iprin=1
                  end if
                  go to 10
               end if
            end do
c
c           eliminate surface helices and strands
c
            if(icurv.eq.1) then
               dr=sqrt(xyzcat(1,i1)**2+xyzcat(2,i1)**2
     *           +xyzcat(3,i1)**2)-radius
               dr2=sqrt(xyzcat(1,i1+nwind-1)**2+xyzcat(2,i1+nwind-1)**2
     *           +xyzcat(3,i1+nwind-1)**2)-radius
            else
               dr=xyzcat(3,i1)
               dr2=xyzcat(3,i1+nwind-1)
            end if
            if((dr.le.-thick+dsurf.and.
     *        dr2.le.-thick+dsurf).or.
     *         (dr.ge.thick-dsurf.and.
     *        dr2.ge.thick-dsurf)) go to 10
            if((isec.eq.1.and.ntop.ge.7).or.
     *         (isec.eq.2.and.ntop.ge.3)) then
               m=m+1
               if(m.gt.maxsegm) then
                  write (*,'(''Too many sec. str. segments'')')
                  stop
               end if
               icur(m)=i1
               nwindcur(m)=nwind
               itype(m)=isec
               mm=0
               do l=i1,i1+nwind-1
                  indca(l)=0
                  mm=mm+1
                  numss(m,mm)=numca(l)
                  seqss(m,mm)=seqca(l)
                  itopss(m,mm)=itopol(l)
               end do
            end if
   10       continue
         end do
      end do
      nsegm=m
      if(nsegm.eq.0) go to 999
c     do i=1,nsegm
c        write (*,'(2i5)') icur(i),nwindcur(i)
c     end do
c
c     Symmetrize secondary structure and TM segments of
c     identical subunits
c
      do i=1,10
         call secsymm (nsegm,icur,nwindcur,namsuca,
     *     numss,seqss,itopss,ichange)
         if(ichange.eq.0) go to 20
      end do
   20 continue
c
c     Shorten TM secondary structures
c
      do i=1,nsegm
         call cut_tm(i,icur,nwindcur,itype(i),itopss)
      end do
c
c     Sort SS and assigne their parameters
c
      m=0
      nalpha=0
      nbeta=0
      do i=1,nca
         do j=1,nsegm
            if(icur(j).eq.i) then
               m=m+1
               if(itype(j).eq.1) then
                  nalpha=nalpha+1
               else 
                  nbeta=nbeta+1
               end if
               namsegm(m)=namsuca(i)
               isegm(1,m)=numca(i)
               isegm(2,m)=numca(i+nwindcur(j)-1)
               natsegm(m)=nwindcur(j)
               if(natsegm(m).ne.isegm(2,m)-isegm(1,m)+1) then
                  write (*,'(''Non-continuous residue numbering in '',
     *              ''sec. structure'',3i4)') m,numca(isegm(1,m)),
     *              numca(isegm(2,m))
c                 stop
               end if
               mm=0
               do k=i,i+nwindcur(j)-1
                  mm=mm+1
                  do l=1,3
                     xyzca(l,m,mm)=xyzcat(l,k)
                  end do
               end do
            end if
         end do
      end do
      if(nalpha.lt.nbeta) itypess=2
  999 continue
      return
      end 
c
      subroutine mapss(nres,xyz,nrestmp,xyztmp,thickn,
     *  namsuca,numca,isecstr,idirect,itopol,isec)
c     -------------------------------------------------
c     Determine isecstr, itopol and idirect
c
      real xyz(3,1),xyztmp(3,1),xyzbuf(3,20),
     *  vshift1(3),vshift2(3),rot(3,3)
      integer isecstr(1),idirect(1),itopol(1),numca(1)
      character*1 namsuca(1)
      data rmsmax1/0.7/,rmsmax2/0.9/
c
      do i=1,nres-nrestmp+1
         dz=xyz(3,i+nrestmp-1)-xyz(3,i)
         m=0
         do j=i,i+nrestmp-1
            if(namsuca(i).ne.namsuca(j)) go to 10
            m=m+1
            do k=1,3
               xyzbuf(k,m)=xyz(k,j)
            end do
         end do
         call rmsd (m,xyzbuf,xyztmp,vshift1,vshift2,rot,rms)
         if((isec.eq.1.and.rms.le.rmsmax1).or.
     *      (isec.eq.2.and.rms.le.rmsmax2)) then
c           write (*,'(i2,1x,a1,1x,i5,1x,f7.2)') 
c    *        isec,namsuca(i),numca(i),rms
            do l=i,i+nrestmp-1
               isecstr(l)=isec
            end do
         end if
   10    continue
      end do
      return
      end 
c
      subroutine secsymm (nsegm,icur,nw,namsuca,
     *  numss,seqss,itopss,ichange)
c     ------------------------------------------
      parameter (maxsegm=900)
      integer icur(1),nw(1),numss(maxsegm,1),itopss(maxsegm,1)
      character*1 namsuca(1)
      character*4 seqss(maxsegm,1)
c
      do i=1,nsegm-1
         do j=i+1,nsegm
            if(namsuca(icur(i)).ne.namsuca(icur(j))) 
     *        call compss (i,j,icur,nw,numss,seqss,itopss,ichange)
         end do
      end do
      return
      end
c
      subroutine compss (i,j,icur,nw,numss,seqss,itopss,ichange)
c     ----------------------------------------------------------
      parameter (maxsegm=900,maxlen2=100)
      integer icur(1),nw(1),numss(maxsegm,1),itopss(maxsegm,1),
     *  numbuf1(maxlen2),numbuf2(maxlen2),
     *  itopbuf1(maxlen2),itopbuf2(maxlen2)
      character*4 seqss(maxsegm,1),seqbuf1(maxlen2),seqbuf2(maxlen2)
c
      ichange=0
c
c     1. Find areas of overlap (if any) based on residue numbering
c     in original PDB file  (numss)
c
      n1=max(numss(i,1),numss(j,1))
      n2=min(numss(i,nw(i)),numss(j,nw(j)))
      nover=n2-n1+1
      if(nover.lt.5) go to 999
c
c     create temporary arrawys for the areas of overlap
c
      m=0
      do k=1,nw(i)
         if(numss(i,k).ge.n1.and.numss(i,k).le.n2) then
            m=m+1
            if(m.eq.1) k01=k
            numbuf1(m)=numss(i,k)
            seqbuf1(m)=seqss(i,k)
            itopbuf1(m)=itopss(i,k)
         end if
      end do
      if(m.ne.nover) then
         write (*,'(''unusual residue numbering in PDB file'')') 
         nover=m
      end if
      m=0
      do k=1,nw(j)
         if(numss(j,k).ge.n1.and.numss(j,k).le.n2) then
            m=m+1
            if(m.eq.1) k02=k
            numbuf2(m)=numss(j,k)
            seqbuf2(m)=seqss(j,k)
            itopbuf2(m)=itopss(j,k)
         end if
      end do
      if(m.ne.nover) then
         write (*,'(''unusual residue numbering in PDB file'')') 
         nover=m
      end if
c
c     2. Check if amino acid sequences in the overlap area are identical
c
      do k=1,nover
         if(seqbuf1(k).ne.seqbuf2(k)) go to 999
      end do
c
c     3. Symmetrize TM segments by extending them
c
      do k=1,nover
         if(itopbuf1(k).eq.1.and.itopbuf2(k).eq.0) then
            ichange=1
            itopbuf2(k)=1
         end if
         if(itopbuf1(k).eq.0.and.itopbuf2(k).eq.1) then
            ichange=1
            itopbuf1(k)=1
         end if
      end do
c
c     4. Redefine parameters icur, nw, numss, seqss and itopss
c
      if(nover.ne.nw(i).or.nover.ne.nw(j).or.k01.ne.1.or.k02.ne.1) 
     *  ichange=1
      nw(i)=nover
      nw(j)=nover
      icur(i)=icur(i)+k01-1
      icur(j)=icur(j)+k02-1
      do k=1,nover
         numss(i,k)=numbuf1(k)
         seqss(i,k)=seqbuf1(k)
         itopss(i,k)=itopbuf1(k)
         numss(j,k)=numbuf2(k)
         seqss(j,k)=seqbuf2(k)
         itopss(j,k)=itopbuf2(k)
      end do
  999 continue
      return
      end
c
      subroutine cut_tm (i,icur,nw,ityp,itopss)
c     ------------------------------------------
      parameter (maxsegm=900)
      integer icur(1),nw(1),itopss(maxsegm,1)
c
      if(ityp.eq.1) nshift=7
      if(ityp.eq.2) nshift=3
      k1=1
      k2=nw(i)
c
      do k=2,nw(i)-1
         if(itopss(i,k-1).eq.0.and.
     *     itopss(i,k).eq.1) then
            k1=max(1,k-nshift)
            go to 10
         end if
      end do
   10 continue
      if(itopss(i,1).eq.1) k1=1
c
      do k=2,nw(i)-1
         if(itopss(i,k).eq.1.and.
     *     itopss(i,k+1).eq.0) k2=min(nw(i),k+nshift)
      end do
      if(itopss(i,nw(i)).eq.1) k2=nw(i)
      icur(i)=icur(i)+k1-1
      nw(i)=k2-k1+1
      return
      end
