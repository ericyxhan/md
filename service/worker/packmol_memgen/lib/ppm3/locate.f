      subroutine locate (nat,xyz,xyzc,solv,numres,namsu,dmembr,
     *  shift,tilt,ener,iprint,namat,namres,
     *  pdbtempl,ifunc,s12,t12,itransform)
c     ----------------------------------------------------------------
c     Transform coordinates to minimize transfer energy. 
c     Optimized parameters: 
c     dmembr - membrane thickness; 
c     shift  - shift of center of mass along Z axis; 
c     tilt,phi   - rotation angles arond OX and OY axes.
c
      EXTERNAL ENERGY,OUT2,MINL2
c
      parameter (maxat=200000,maxvar=3,maxhpr=maxvar*(maxvar+7)/2,
     * maxmem=800000,maxsolut=8000)
c
      common /coord/ nat0,xyzmin(3,maxat),prod(maxat),ifunc0,dmem
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real xyz(3,1),xyzc(3,1),solv(1),
     * xyzb(3,maxat),vc(3),vmin(3),emem(maxmem),
     * E2(2),DS(maxvar),EST(8),BMIN(maxvar),HPR(maxhpr),ESTM(8),
     * GR(maxvar),VAR(maxvar,2),GRM(maxvar),
     * tetaar(maxsolut),shiftar(maxsolut),
     * enerar(maxsolut),phiar(maxsolut)
c
      integer numres(1),KOD(8),KODM(8)
c
      character*80 namfile,pdbtempl
      character*4 namat(1),namres(1)
      character*1 namsu(1)
c
c     data shint/90./,shstep/1.0/,
      data shint/100./,shstep/2.0/,
c    *  pi/3.14159/,step1/4./,step2/2./,
     *  pi/3.14159/,step1/10./,step2/5./,
     *  EST/4.,.02,0.,.0001,.5,.0001,.001,.01/,
     *  KOD/2,1,3*100,1,2,20/,ecut1/4.0/,ecut2/1.0/,
     *  tetacut/60./,shiftcut/5.0/
c
c     Locate global minimum of transfer energy
c     using grid scan
c
      ifunc0=ifunc
      nat0=nat
      alpha=1.11
      do i=1,nat
         prod(i)=accs(i)*solv(i)
         do j=1,3
            xyzmin(j,i)=xyz(j,i)
         end do
      end do
c
c     Grid scan without local energy minimization.
c     All energies are placed to array 'emem'
c
      m=0
      do phi0=0.,179.,step1
         phi=phi0*pi/180.
         do teta0=-90.,90.,step2
            teta=teta0*pi/180.
            call tilting (phi,teta,nat,xyz,xyzc)
            do sh=-shint,shint,shstep
               do i=1,nat
                  xyzb(1,i)=xyzc(1,i)
                  xyzb(2,i)=xyzc(2,i)
                  xyzb(3,i)=xyzc(3,i)+sh
               end do
               dmem=dmembr/2.
               en=0.
               do i=1,nat
                  if(accs(i).gt.0.) then
                     zc=xyzb(3,i)
                     if(ifunc.eq.1) then
                        al=alpha*(abs(zc)-dmem)
                        c=1./(1.+exp(al))
                        en=en+c*prod(i)
                     else
                        call ener_at(zc,accs(i),dip(i),iat(i),
     *                    charge(i),charge2(i),eioniz(i),asaref(i),
     *                    hbond(i),etot,d_etot)
                        en=en+etot
                     end if
                  end if
               end do
               m=m+1
               if(m.gt.maxmem) then
                  write (*,'(''Too many steps of grid scan'')')
                  stop
               end if
               emem(m)=en
            end do
         end do
      end do
c
c     Lowest (reference) energy obtained during grid scan - 'eref'
c
      eref=99.
      m=0
      do phi0=0.,179.,step1
         do teta0=-90.,90.,step2
            do sh=-shint,shint,shstep
               m=m+1
               if(emem(m).lt.eref) then                         
                  eref=emem(m)
               end if
            end do
         end do
      end do
      if(iprint.ge.2) write (*,'(''eref='',f7.2)') eref
c
c     Local energy minimization for all low-energy 
c     positions within ecut1 energy interval
c
      ms=0
      eminsol=9999.
      do isol=1,maxsolut
c        write (*,'(i10)') isol
         m=0
c
c        Find the lowest energy point, among the remaining points,
c        for local energy minimization:
c
         emin=9999.
         do phi0=0.,179.,step1
            phi=phi0*pi/180.
            do teta0=-90.,90.,step2
               teta=teta0*pi/180.
               do sh=-shint,shint,shstep
                  m=m+1
                  if(emem(m).lt.emin) then
                     emin=emem(m)
                     phimin0=phi
                     tetamin0=teta
                     shift0=sh
                     mem=m
                  end if
               end do
            end do
         end do
c        discard the point that has been used:
         emem(mem)=99.
         if(emin.gt.eref+ecut1.or.emin.gt.-0.1) go to 10
c
c        local energy minimization:
c
         nvar=3
         var(1,1)=shift0 
         var(2,1)=phimin0
         var(3,1)=tetamin0
         if(iprint.ge.2) write (*,'(f7.2,4f8.2)') 
     *    ener,(var(j,1),j=1,3)
         CALL ENERGY (VAR,E2(1),GR,1)
         DO M=1,8
            KODM(M)=KOD(M)
            ESTM(M)=EST(M)
         END DO
         do i=1,maxvar
            GRM(i)=0.
            DS(i)=0.001
         end do
         if(iprint.ge.2) write (*,'(''e initial='',f6.2)') E2(1)
c
         CALL MIN12 (KODM,NVAR,VAR,E2,GR,GRM,DS,ESTM,
     *      ENERGY,MINL2,OUT2,HPR,BMIN,IER)
c
c        write (*,'(''ESTM: '',8f6.3)') (ESTM(i),i=1,8)
c        if(ier.ne.0) write (*,'(''ier='',i4)') ier
c
         K1=KOD(4)-KODM(4)
         K2=KOD(5)-KODM(5)
         if(iprint.ge.2) then
            WRITE (*,'(I4,'' calculations of function,'',I4,
     *        '' iterations'')') K1,K2
            tlt=(var(3,1)/pi)*180.
            phimn=(var(2,1)/pi)*180.
c           write (*,'(''  shift='',f7.1,
c    *        ''  tilt='',f7.1,'' phimin'',f7.1,''  ener='',
c    *        f7.1)') var(1,1),tlt,phimn,e2(1)
         end if
         if(e2(1).lt.eminsol) then
            eminsol=e2(1)
            shift=var(1,1)
            phimin=var(2,1)
            tetamin=var(3,1)
            ener=e2(1)
         end if
         ms=ms+1
         shiftar(ms)=var(1,1)
         phiar(ms)=var(2,1)
         tetaar(ms)=(var(3,1)/pi)*180.
         enerar(ms)=e2(1)
      end do
   10 continue
c
c     Transform coordinates
c
      if(itransform.ne.0) then
         call tilting (phimin,tetamin,nat,xyz,xyzc)
         do i=1,nat
            xyz(1,i)=xyzc(1,i)
            xyz(2,i)=xyzc(2,i)
            xyz(3,i)=xyzc(3,i)+shift
         end do
      end if
      tilt=(tetamin/pi)*180.
      tilt=abs(tilt)
      if(tilt.gt.90.) tilt=180.-tilt
c
c     Minimal, maximal, average and rmsd of variables
c     for solutions with relative energies < ecut2
c
      smin=100.
      smax=-50.
      sav=0.
      tmin=360.
      tmax=-360.
      tav=0.
      srms=0.
      trms=0.
      m=0
      do i=1,ms
         tetaar(i)=abs(tetaar(i))
         if(tetaar(i).gt.90.) tetaar(i)=180.-tetaar(i)
      end do
      do i=1,ms
         if(enerar(i).le.ener+ecut2) then
            if(abs(tetaar(i)-tilt).gt.tetacut.or.
     *        abs(shiftar(i)-shift).gt.shiftcut) then
c           if(abs(shiftar(i)-shift).gt.shiftcut) then
c
c             exclude and output significantly different
c             arrangements (currently unused)
c
c              if(abs(abs(tetaar(i))-abs(tilt)).gt.tetacut)
c    *           write (*,'(''  shift='',f7.1,
c    *           ''  tilt='',f7.1,''  ener='',f7.1)') 
c    *           shiftar(i),tetaar(i),enerar(i)
            else
               m=m+1
               if(tetaar(i).lt.tmin) tmin=tetaar(i)
               if(tetaar(i).gt.tmax) tmax=tetaar(i)
               tav=tav+tetaar(i)
               if(shiftar(i).lt.smin) smin=shiftar(i)
               if(shiftar(i).gt.smax) smax=shiftar(i)
               sav=sav+shiftar(i)
               srms=srms+(shiftar(i)-shift)**2
               trms=trms+(tetaar(i)-tilt)**2
            end if
         end if
      end do
      sav=sav/float(m)
      tav=tav/float(m)
      srms=sqrt(srms/float(m))
      trms=sqrt(trms/float(m))
c
      phimin=(phimin/pi)*180.
c
c*    write (*,'('' '')')
c*    write (*,'(i5,'' minima'')') m
c     s12=0.5*(smax-smin)
      s12=srms
c*    write (*,'(''shift=  '',f7.1,1x,f7.1,'' +-'',4(1x,f7.1))')
c*   * shift,sav,srms,smin,smax,s12
c     t12=0.5*(tmax-tmin)
      t12=trms
c*    write (*,'(''tilt= '',f5.0,f5.0,''  +-'',4f5.1)')
c*   * tilt,tav,trms,tmin,tmax,t12
c     write (*,'(''energy='',f9.1)') ener
c     write (*,'(a10,f9.1,f5.1,f6.0)') pdbtempl(1:10),ener,s12,t12
      return
      end
c
      subroutine rotate (nat,xyz,phi,v1,vt)
c     -------------------------------------
      real xyz(3,1),v1(3),vt(3),x(3)
c
      do i=1,nat
         x(1)=xyz(1,i)
         x(2)=xyz(2,i)
         x(3)=xyz(3,i)
         call axrot(x,phi,v1,vt)
         xyz(1,i)=x(1)
         xyz(2,i)=x(2)
         xyz(3,i)=x(3)
      end do
      return
      end 
c
      SUBROUTINE AXROT (X,FI,V,VT)
C     ---------------------------
      REAL X(3),V(3),VT(3),H1(3),H2(3),H3(3),VB(3)
C
C     rotation of the point X(3) around line V(3) 
c     that crosses point VT(3)
C
      R=SQRT(V(1)*V(1)+V(2)*V(2)+V(3)*V(3))
C
      FF=0.5*FI
      A=COS(FF)
      P=SIN(FF)/R
      B=P*V(1)
      C=P*V(2)
      D=P*V(3)
      AA=A*A
      BB=B*B
      CC=C*C
      DD=D*D
      BC=B*C*2.
      AD1=A*D*2.
      BD1=B*D*2.
      AC=A*C*2.
      CD=C*D*2.
      AB=A*B*2.
      H1(1)=AA+BB-CC-DD
      H2(1)=BC-AD1
      H3(1)=BD1+AC
      H1(2)=BC+AD1
      H2(2)=AA-BB+CC-DD
      H3(2)=CD-AB
      H1(3)=BD1-AC
      H2(3)=CD+AB
      H3(3)=AA-BB-CC+DD
C
C     rotation:
C
      DO I=1,3
        VB(I)=VT(I) + H1(I)*(X(1)-VT(1)) + H2(I)*(X(2)-VT(2)) +
     *                H3(I)*(X(3)-VT(3))
      end do  
C
      DO I=1,3
        X(I)=VB(I)
      end do   
      RETURN
      END
c
      subroutine locate2 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *  itransform,iopt,shminim,phiminim,tetaminim,shstep,step1,step2,
     *  radius)
c     ---------------------------------------------------------------
c     Optimization of transfer energy for spherical lipid bilayer.
c     Variables:
c     Optimized parameters: 
c     dmembr - membrane thickness; 
c     shift  - shift of center of mass along Z axis; 
c     tilt,phi   - rotation angles arond OX and OY axes.
c
c     This is a simplified version, without mechanic energy terms, 
c     local energy minimization, and calculation of errors;
c     use only new energy functions.
c
      parameter (maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real xyz(3,1),xyzc(3,1),solv(1),xyzb(3,maxat)
c
      data shint/90./,pi/3.14159/,
     *  delsh/5./,delphi/40./,delteta/40./
c
c     data shstep/4.0/,step1/30./,step2/30./
c
      csurf= 0.000
c
      if(iopt.eq.0) then
         sh1=-shint
         sh2=shint
         phi1=0.
         phi2=179.
c        teta1=-90.
c        teta2=90.
         teta1=-180.
         teta2=180.
      end if
      if(iopt.eq.1) then
         sh1=shminim-delsh
         sh2=shminim+delsh
         phi1=phiminim-delphi
         phi2=phiminim+delphi
         teta1=tetaminim-delteta
         teta2=tetaminim+delteta
      end if
      if(iopt.eq.2) then
c        sh1=shminim-1.
c        sh2=shminim+1.
c        phi1=phiminim-10.
c        phi2=phiminim+10.
c        teta1=tetaminim-10.
c        teta2=tetaminim+10.
         sh1=shminim
         sh2=shminim
         phi1=phiminim
         phi2=phiminim
         teta1=tetaminim
         teta2=tetaminim
      end if
c
c     Locate global minimum of transfer energy
c     using grid scan
c
      dmem=dmembr/2.
c
      emin=99.
c     do phi0=phi1,phi2,step1
      phi0=phi1
      do while (phi0.le.phi2)
         phi=phi0*pi/180.
c        do teta0=teta1,teta2,step2
         teta0=teta1
         do while (teta0.le.teta2)
            teta=teta0*pi/180.
            call tilting (phi,teta,nat,xyz,xyzc)
c           do sh=sh1,sh2,shstep
            sh=sh1
            do while (sh.le.sh2)
               do i=1,nat
                  xyzb(1,i)=xyzc(1,i)
                  xyzb(2,i)=xyzc(2,i)
                  xyzb(3,i)=xyzc(3,i)+sh+radius
               end do
               en=0.
               asatot=0.
               do i=1,nat
                  if(accs(i).gt.0.) then
                     a=xyzb(1,i)
                     b=xyzb(2,i)
                     c=xyzb(3,i)
                     zc=sqrt(a*a+b*b+c*c)
                     zc=zc-radius
c                    if(zc.lt.dmem) 
c    *                 asatot=asatot+accs(i)
                     call ener_at(zc,accs(i),dip(i),iat(i),
     *                 charge(i),charge2(i),eioniz(i),asaref(i),
     *                 hbond(i),etot,d_etot)
                     en=en+etot
                  end if
               end do
               en=en+csurf*asatot
               if(en.lt.emin) then                         
                  emin=en
                  shift=sh
                  phimin=phi
                  tetamin=teta
               end if
               sh=sh+shstep
            end do
            teta0=teta0+step2
         end do
         phi0=phi0+step1
      end do
c
      ener=emin
      shminim=shift
      phiminim=(phimin/pi)*180.
      tetaminim=(tetamin/pi)*180.
c
c     Transform coordinates
c
      if(itransform.ne.0) then
         call tilting (phimin,tetamin,nat,xyz,xyzc)
         do i=1,nat
            xyz(1,i)=xyzc(1,i)
            xyz(2,i)=xyzc(2,i)
            xyz(3,i)=xyzc(3,i)+shift+radius
         end do
      end if
      return
      end
c
      subroutine locate3 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *  itransform,iopt,shminim,phiminim,tetaminim,shstep,step1,step2,
     *  radius)
c     ---------------------------------------------------------------
c     Optimization of transfer energy for cylindrical lipd bilayer
c     (currently unused)
c     Variables:
c     Optimized parameters: 
c     dmembr - membrane thickness; 
c     shift  - shift of center of mass along Z axis; 
c     tilt,phi   - rotation angles arond OX and OY axes.
c
c     This is a simplified version, without mechanic energy terms, 
c     local energy minimization, and calculation of errors;
c     use only new energy functions.
c
      parameter (maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real xyz(3,1),xyzc(3,1),solv(1),xyzb(3,maxat)
c
      data shint/70./,pi/3.14159/,
     *  delsh/1./,delphi/30./,delteta/30./
c
c     data shstep/4.0/,step1/30./,step2/30./
c
      csurf= 0.000
c
      if(iopt.eq.0) then
         sh1=-shint
         sh2=shint
         phi1=0.
         phi2=179.
c        teta1=-90.
c        teta2=90.
         teta1=-180.
         teta2=180.
      end if
      if(iopt.eq.1) then
         sh1=shminim-delsh
         sh2=shminim+delsh
         phi1=phiminim-delphi
         phi2=phiminim+delphi
         teta1=tetaminim-delteta
         teta2=tetaminim+delteta
      end if
      if(iopt.eq.2) then
c        sh1=shminim-1.
c        sh2=shminim+1.
c        phi1=phiminim-10.
c        phi2=phiminim+10.
c        teta1=tetaminim-10.
c        teta2=tetaminim+10.
         sh1=shminim
         sh2=shminim
         phi1=phiminim
         phi2=phiminim
         teta1=tetaminim
         teta2=tetaminim
      end if
c
c     Locate global minimum of transfer energy
c     using grid scan
c
      dmem=dmembr/2.
c
      emin=99.
c     do phi0=phi1,phi2,step1
      phi0=phi1
      do while (phi0.le.phi2)
         phi=phi0*pi/180.
c        do teta0=teta1,teta2,step2
         teta0=teta1
         do while (teta0.le.teta2)
            teta=teta0*pi/180.
            call tilting (phi,teta,nat,xyz,xyzc)
c           do sh=sh1,sh2,shstep
            do xcoor=-50.,50.,2.
               sh=sh1
               do while (sh.le.sh2)
                  do i=1,nat
                     xyzb(1,i)=xyzc(1,i)+xcoor
                     xyzb(2,i)=xyzc(2,i)
                     xyzb(3,i)=xyzc(3,i)+sh+radius
                  end do
                  en=0.
                  asatot=0.
                  do i=1,nat
                     if(accs(i).gt.0.) then
                        a=xyzb(1,i)
                        b=xyzb(2,i)
                        c=xyzb(3,i)
                        zc=sqrt(a*a+c*c)
                        zc=zc-radius
c                       if(zc.lt.dmem) 
c    *                    asatot=asatot+accs(i)
                        call ener_at(zc,accs(i),dip(i),iat(i),
     *                    charge(i),charge2(i),eioniz(i),asaref(i),
     *                    hbond(i),etot,d_etot)
                        en=en+etot
                     end if
                  end do
                  en=en+csurf*asatot
                  if(en.lt.emin) then                         
                     emin=en
                     shift=sh
                     phimin=phi
                     tetamin=teta
                     xcoormin=xcoor
                  end if
                  sh=sh+shstep
               end do
            end do
            teta0=teta0+step2
         end do
         phi0=phi0+step1
      end do
c
      ener=emin
      shminim=shift
      phiminim=(phimin/pi)*180.
      tetaminim=(tetamin/pi)*180.
c
c     Transform coordinates
c
      if(itransform.ne.0) then
         call tilting (phimin,tetamin,nat,xyz,xyzc)
         do i=1,nat
            xyz(1,i)=xyzc(1,i)+xcoormin
            xyz(2,i)=xyzc(2,i)
            xyz(3,i)=xyzc(3,i)+shift+radius
         end do
      end if
      return
      end
c
      subroutine locate4 (nat,xyz,xyzc,solv,dmembr,shift,ener,iprint,
     *  itransform,iopt,shminim,phiminim,tetaminim,shstep,step1,step2)
c     ---------------------------------------------------------------
c     Optimization of transfer energy for spherical micelle. 
c     Variables:
c     Optimized parameters: 
c     dmembr - membrane thickness; 
c     shift  - shift of center of mass along Z axis; 
c     tilt,phi   - rotation angles arond OX and OY axes.
c
c     This is a simplified version, without mechanic energy terms, 
c     local energy minimization, and calculation of errors;
c     use only new energy functions.
c
      parameter (maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      real xyz(3,1),xyzc(3,1),solv(1),xyzb(3,maxat)
c
      data shint/70./,pi/3.14159/,
     *  delsh/2./,delphi/30./,delteta/30./
c
c     data shstep/4.0/,step1/30./,step2/30./
c
      csurf= 0.003
c
      if(iopt.eq.0) then
         sh1=-shint
         sh2=shint
         phi1=0.
         phi2=179.
         teta1=-90.
         teta2=90.
      end if
      if(iopt.eq.1) then
         sh1=shminim-delsh
         sh2=shminim+delsh
         phi1=phiminim-delphi
         phi2=phiminim+delphi
         teta1=tetaminim-delteta
         teta2=tetaminim+delteta
      end if
      if(iopt.eq.2) then
c        sh1=shminim-1.
c        sh2=shminim+1.
c        phi1=phiminim-10.
c        phi2=phiminim+10.
c        teta1=tetaminim-10.
c        teta2=tetaminim+10.
         sh1=shminim
         sh2=shminim
         phi1=phiminim
         phi2=phiminim
         teta1=tetaminim
         teta2=tetaminim
      end if
c
c     Locate global minimum of transfer energy
c     using grid scan
c
      dmem=dmembr/2.
      z0wat=dmem-1.0
c
      emin=99.
c     do phi0=phi1,phi2,step1
      phi0=phi1
      do while (phi0.le.phi2)
         phi=phi0*pi/180.
c        do teta0=teta1,teta2,step2
         teta0=teta1
         do while (teta0.le.teta2)
            teta=teta0*pi/180.
            call tilting (phi,teta,nat,xyz,xyzc)
c           do sh=sh1,sh2,shstep
            sh=sh1
            do while (sh.le.sh2)
               do i=1,nat
                  xyzb(1,i)=xyzc(1,i)
                  xyzb(2,i)=xyzc(2,i)
                  xyzb(3,i)=xyzc(3,i)+sh
               end do
               en=0.
               asatot=0.
               do i=1,nat
                  if(accs(i).gt.0.) then
                     a=xyzb(1,i)
                     b=xyzb(2,i)
                     c=xyzb(3,i)
                     zc=sqrt(a*a+b*b+c*c)
                     if(zc.lt.dmem) 
     *                 asatot=asatot+accs(i)
                     call ener_at(zc,accs(i),dip(i),iat(i),
     *                 charge(i),charge2(i),eioniz(i),asaref(i),
     *                 hbond(i),etot,d_etot)
                     en=en+etot
                  end if
               end do
               en=en+csurf*asatot
               if(en.lt.emin) then                         
                  emin=en
                  shift=sh
                  phimin=phi
                  tetamin=teta
               end if
               sh=sh+shstep
            end do
            teta0=teta0+step2
         end do
         phi0=phi0+step1
      end do
c
      ener=emin
      shminim=shift
      phiminim=(phimin/pi)*180.
      tetaminim=(tetamin/pi)*180.
c
c     Transform coordinates
c
      if(itransform.ne.0) then
         call tilting (phimin,tetamin,nat,xyz,xyzc)
         do i=1,nat
            xyz(1,i)=xyzc(1,i)
            xyz(2,i)=xyzc(2,i)
            xyz(3,i)=xyzc(3,i)+shift
         end do
      end if
      return
      end
