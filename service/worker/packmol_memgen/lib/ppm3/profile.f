      subroutine profile (dmembr)
c     ---------------------------
c     creating transmembrane profiles:
c     sig_pro - atomic solvation parameters 
c     edip_pro - dipole energy per 1D of a fully exposed group, cfdiel(1)*dpibil
c                  
c     echarge_pro - Abe function cfdiel(2)*func_abe
c     ehbond_pro  - hydrogen bond contribution to atom transfer energy, -3./epsbil
c
      parameter (ntypes=17)
      common/tables/sig_pro(ntypes,15000),edip_pro(15000),
     *  echarge_pro(15000),ehbond_pro(15000),
     *  d_sig_pro(ntypes,15000),d_edip_pro(15000),
     *  d_echarge_pro(15000),d_ehbond_pro(15000),
     *  eclm_pro(15000),d_eclm_pro(15000)
c
      data pro1/-50./,pro2/50./,prostep/0.01/,delta/0.1/
c
c     make profiles from -50. to 50 A, with step 0.01 A
c
      nstep=int(delta/prostep)
c
c     1. Profile for eps and pi*
c
      m=0
      do zcur=pro1,pro2,prostep
         m=m+1
         do iat=1,10
            call profile_point(m,zcur,iat,dmembr)
         end do
      end do
      mmax=m
c
c     Derivatives by z
c
      do m=1,mmax-1
         do iat=1,ntypes
            d_sig_pro(iat,m)=(sig_pro(iat,m+1)-sig_pro(iat,m))/prostep
         end do
         d_echarge_pro(m)=(echarge_pro(m+1)-echarge_pro(m))/prostep
         d_edip_pro(m)=(edip_pro(m+1)-edip_pro(m))/prostep
         d_ehbond_pro(m)=(ehbond_pro(m+1)-ehbond_pro(m))/prostep
         d_eclm_pro(m)=(eclm_pro(m+1)-eclm_pro(m))/prostep
      end do
      do iat=1,ntypes
         d_sig_pro(iat,mmax)=0.
      end do
      d_echarge_pro(mmax)=0.
      d_edip_pro(mmax)=0.
      d_ehbond_pro(mmax)=0.
      d_eclm_pro(mmax)=0.
      return
      end
c
      subroutine profile_point(mcur,zcur,iat,dmembr)
c     ---------------------------------------------
      parameter (ncurve=4,ncompon=ncurve+2,ntypes=17)
c
c     Recent changes: 
c     1. Pi* values in PCN and CHO region are considered the same as
c        in water, similar to dielectric constant (this is 
c        essentially an aqueous solution of ions)   
c     2. Include H-bonds for atoms with zero ASA if they are formed
c        by flexible (water-accessible side-chains)
c     3. Beta were slightly inccreased to reflect ~10% of serine lipids
c     4. Membrane considered as symmetric DOPC bilayer
c
      common/tables/sig_pro(ntypes,15000),edip_pro(15000),
     *  echarge_pro(15000),ehbond_pro(15000),
     *  d_sig_pro(ntypes,15000),d_edip_pro(15000),
     *  d_echarge_pro(15000),d_ehbond_pro(15000),
     *  eclm_pro(15000),d_eclm_pro(15000)
c
      data epair/-1.5/
c
c     DOPC:
c                        C=C   CG   PCN  CHO
      real sigma0(ncurve)/3.05,2.05,2.41,2.98/,
     *     Zc0(ncurve)   /9.6, 14.8, 19.1, 20.6/,
     *    vmol0(ncurve)/44.0,139.,  86., 106./,
c                        C=C   CH2   CG   PCN  CHO  water
     *     alp(ncompon)/0.00, 0.00, 0.00,0.82,0.83,0.82/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,1.74,0.0,0.35/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,1.99,1.99,0.35/,
     *     bet(ncompon)/0.07, 0.00, 0.88,1.74,1.74,0.35/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,1.99,0.42,0.35/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,2.74,1.70,0.35/,
     *     pia(ncompon)/0.34, 0.00, 0.60, 0.73,0.14,1.09/,
c    *     eps(ncompon)/2.00, 2.24, 6.94,21.3, 2.6,78.4/,
     *     eps(ncompon)/2.00, 2.24, 6.94,78.4,78.4,78.4/,
c    *    vmol(ncompon)/44.0, 52.0,139.,192.,106.,18./,
     *    vmol(ncompon)/44.0,108.0,139.,86.,106.,18./,
     *  sigma(ncurve),zc(ncurve),
c
c     DLPE:
c     real sigma0(ncurve)/3.05,2.05,2.41,2.98/,
c    *     Zc0(ncurve)   /9.6, 14.2, 18.5, 20.6/,
c    *    vmol0(ncurve)/ 0.0,129., 123.,   0./,
c                        C=C   CH2   CG   PCN  CHO  water
c    *     alp(ncompon)/0.00, 0.00, 0.00,0.87,0.87,0.82/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,1.74,0.0,0.35/,
c    *     pia(ncompon)/0.34, 0.00, 0.60, 0.73,0.73,1.09/,
c    *     eps(ncompon)/2.00, 2.24, 6.94,78.4,78.4,78.4/,
c    *    vmol(ncompon)/44.0,110.8,139.,123.,106.,18./,
c    *  sigma(ncurve),zc(ncurve),
c
c     DOPS:
c     real sigma0(ncurve)/3.05,2.05,2.41,2.98/,
c    *     Zc0(ncurve)   /9.6, 15.9, 20.2, 20.6/,
c    *    vmol0(ncurve)/44.0,132., 132.,   0./,
c                        C=C   CH2   CG   PCN  CHO  water
c    *     alp(ncompon)/0.00, 0.00, 0.00,0.87,0.87,0.82/,
c    *     bet(ncompon)/0.07, 0.00, 0.88,4.24,0.0,0.35/,
c    *     pia(ncompon)/0.34, 0.00, 0.60, 0.73,0.73,1.09/,
c    *     eps(ncompon)/2.00, 2.24, 6.94,78.4,78.4,78.4/,
c    *    vmol(ncompon)/44.0,110.8,139.,132.,106.,18./,
c    *  sigma(ncurve),zc(ncurve),
c
c     Use vmol0=0 for "CHO" group of PE and PS
c
c     Volume of CH2 group for calculating molar fractions
c     was taken as 4*Vch2=110.8 instead of 27.7
c
c     Dielectric constants of PCN and CHO were taken as 78.4,
c     rather than 21.3 and 2.45
c
c     44. is the volume of CH=CH group
c     Volumes of CH2 group and water are used only for
c     calculating mole fractions
c     zi0 -position of hydrocarbon boundary;
c     si - width of error function describing the hydrocarbon boundary
c
     *  amp(ncompon),fm(ncompon),xlip(6),xaq(6),amplip(6),amp0(6),
     *  awat/0.066/,bwat/0.010/,z0wat/9.0/,alam_wat/1.10/,
c    *  awat/0.040/,bwat/0.007/,z0wat/8.2/,alam_wat/0.53/,
     *  deltaz(4)/-4.8,0.4,4.7,6.2/,
c
c      amp and fm - volume and molar fractions in total water-lipid mixture
c      xlip and xaq - molar fractions in non-aqueous and aqueous parts
c      amplip - volume fractions in non-aqueous part
c
c       Signs are changed:
     *  cfsigma(29)/
c
c      Pi* model:
c    *  -0.017, 0.008,-0.015, 0.007,-0.076,-0.017,
c    *  -0.115,-0.004,-0.021,-0.027,-0.075,
c    *  -0.067,-0.013,-0.001, 0.007,-0.221,-0.023/,
c    *  cfdiel(2)/0.773,0.198/
c
c      Block-Walker model
     *  -0.017, 0.008,-0.013, 0.010,-0.088, 0.000,
     *  -0.124, 0.000,-0.028,-0.027,-0.063,
     *  -0.044,-0.019, 0.002, 0.010,-0.221,-0.023,
     *  -0.002, 0.008,-0.007, 0.010,-0.010, 0.010,
     *  -0.013, 0.010,-0.012, 0.010,-0.016, 0.010/,
     *  cfdiel(2)/1.865,0.198/,cfpol/0.001/
c    *  -0.017, 0.007,-0.016, 0.005,-0.074,-0.020,
c    *  -0.093,-0.013,-0.030,-0.020,-0.087,
c    *  -0.071,-0.010,-0.003, 0.005,-0.221,-0.023/,
c    *  cfdiel(2)/0.807,0.198/
c
c     Different parameter set can be used based on data
c     for transfer from only nonpolar solvents to water
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
c    10  - NH3+
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
c     DOPC:
c
c     zi0=14.4
      area=67.4
      zi0=dmembr/2.
      do j=1,4
         Zc(j)=zi0+deltaz(j)
         sigma(j)=sigma0(j)
      end do
      z0wat=zi0-6.00
      si=2.48
c
c     DLPE:
c
c     zi0=12.9
c     area=51.2
c
c     DOPS:
c
c     zi0=15.4
c     area=64.1
c
      p0=sqrt(2.*3.14159)
c
c     Volume concentrations of lipid components:
c
      do i=1,ncurve
         amp0(i)=(vmol0(i)/(p0*area*sigma(i)))*
     *    (exp(-0.5*((zcur-Zc(i))/sigma(i))**2)+
     *    exp(-0.5*((zcur+Zc(i))/sigma(i))**2))
         if(i.eq.1) amp0(i)=2.*amp0(i)
      end do
c
c     Volume concentration of hydrocarbon:
c
      a=(zcur+zi0)/sqrt(2.*si)
      b=(zcur-zi0)/sqrt(2.*si)
      amphdc=0.5*(erf(a)-erf(b))
c
c     Volume concentration of CH2 groups
c
      amp0(5)=amphdc-amp0(1)
      if(amp0(5).lt.0.) amp0(5)=0.
c
c     Volume concentration of water:
c
      amptot=0.
      do i=1,ncompon-1
         amptot=amptot+amp0(i)
      end do
      if(amptot.gt.1.) amptot=1.
      ampwat=1.-amptot
c
c     Correction for penetration water per ESR data:
c
      cwat=(abs(zcur)-z0wat)/alam_wat
      wat_pen=awat-(awat-bwat)/(1.+exp(cwat))
      if(ampwat.lt.wat_pen) then
         amp0(5)=amp0(5)-(wat_pen-ampwat)
         ampwat=wat_pen
      end if
      amp0(6)=ampwat
c
      amp(1)=amp0(1)
      amp(2)=amp0(5)
      amp(3)=amp0(2)
      amp(4)=amp0(3)
      amp(5)=amp0(4)
      amp(6)=amp0(6)
c
c     Molar fraction of water depends on volumes of all groups
c     including aliphatic segment
c
c     Molar fractions of all components
c
      fmtot=0.
      do i=1,ncompon
         fmtot=fmtot+amp(i)/vmol(i)
      end do
c
      do i=1,ncompon
         fm(i)=(amp(i)/vmol(i))/fmtot
      end do
c
c     Molar fractions of lipid components
c
      fmtot=0.
      do i=1,3
         fmtot=fmtot+amp(i)/vmol(i)
      end do
c
      do i=1,3
         xlip(i)=(amp(i)/vmol(i))/fmtot
      end do
c
c     Molar fractions of aqueous components
c
      fmtot=0.
      do i=4,ncompon
         fmtot=fmtot+amp(i)/vmol(i)
      end do
c
      do i=4,ncompon
         xaq(i)=(amp(i)/vmol(i))/fmtot
      end do
c
c     renormalization of volume fractions for
c     all components excluding water
c
      amptot=0
      do i=1,ncompon-1
         amptot=amptot+amp(i)
      end do
      do i=1,ncompon-1
         amplip(i)=amp(i)/amptot
      end do
c
c     Polarity profiles
c
      alplip=0.
      alpbil=0.
      betlip=0.
      alpaq=0.
      betaq=0.
      pibil=0.
      epsbil=0.
c
c     dielectric constant and Pi*
c
      do i=1,ncompon-1
         epsbil=epsbil+amplip(i)/eps(i)
      end do
      epsbil=1./epsbil
      fmwat=fm(ncompon)
      if(fmwat.gt.0.10) epsbil=epsbil+(eps(ncompon)-epsbil)*
     * (fmwat-0.10)/0.90
c
      do i=1,ncompon
         pibil=pibil+fm(i)*pia(i)
         alpbil=alpbil+fm(i)*alp(i)
      end do
c
      do i=1,3
         alplip=alplip+amplip(i)*alp(i)
         betlip=betlip+amplip(i)*bet(i)
      end do
c
      do i=4,6
         alpaq=alpaq+xaq(i)*alp(i)
         betaq=betaq+xaq(i)*bet(i)
      end do
c
      call func0(epsbil,78.4,func_1)
      call func2(epsbil,78.4,func_2)
      call func3(epsbil,78.4,func_abe)
c
c     we try volume fraction of lipid, but this should be checked:
c
      ampnonp=1.-ampwat
      dbetlip=betlip-0.35
      dbetaq=betaq-0.35
      dalplip=alplip-0.82
      dalpaq=alpaq-0.82
      dpibil=pibil-1.09
c
c     ASA-dependent and dipole-dependent solvation energies
c
      sig_aq=0.
      sig_lip=0.
      sig_bil=0.
c
c     Modulation of the hydrophobic effect by solvent polarity was 
c     neglected together withhydrophobic effect for the transfer
c     of nonpolar atoms to the aqueous lipid headgroup region
c     Hence sig_aq=0 for nonpolar (non-hydrogen-bonding) types of atoms.
c
c     Csp3:
      if(iat.eq.1) then
         sig_lip=cfsigma(1)-cfsigma(2)*func_1
         sig_aq=0.
      end if
c     Csp2:
      if(iat.eq.2) then
         sig_lip=cfsigma(3)+cfsigma(4)*dalplip
         sig_aq=0.
      end if
c     NH:
      if(iat.eq.3) then
         sig_lip=-cfsigma(5)*func_1+cfsigma(6)*dbetlip
         sig_aq=cfsigma(6)*dbetaq
      end if
c     N:
      if(iat.eq.4) then
         sig_lip=-cfsigma(7)*func_1+cfsigma(8)*dalplip
         sig_aq=cfsigma(8)*dalpaq
      end if
c     OH:
      if(iat.eq.5) then
         sig_lip=-cfsigma(9)*func_1+cfsigma(10)*dalplip+
     *     cfsigma(11)*dbetlip
         sig_aq=cfsigma(10)*dalpaq+cfsigma(11)*dbetaq
      end if
c     O:
      if(iat.eq.6) then
         sig_lip=-cfsigma(12)*func_1+cfsigma(13)*dalplip
            sig_aq=cfsigma(13)*dalpaq
      end if
c     S:
      if(iat.eq.7) then
         sig_lip=cfsigma(14)+cfsigma(15)*dalplip
         sig_aq=0.
      end if
c     Cpol
      if(iat.eq.8) then
         sig_lip=cfpol
         sig_aq=0.
      end if
c     C=-C
      if(iat.eq.11) then
         sig_lip=cfsigma(18)
         sig_aq=0.
      end if
c     N (C=-N)
      if(iat.eq.12) then
         sig_lip=cfsigma(19)
         sig_aq=0.
      end if
c     F 
      if(iat.eq.13) then
         sig_lip=cfsigma(20)+cfsigma(21)*dalplip
         sig_aq=0.
      end if
c     Cl
      if(iat.eq.14) then
         sig_lip=cfsigma(22)+cfsigma(23)*dalplip
         sig_aq=0.
      end if
c     Br
      if(iat.eq.15) then
         sig_lip=cfsigma(24)+cfsigma(25)*dalplip
         sig_aq=0.
      end if
c     I 
      if(iat.eq.16) then
         sig_lip=cfsigma(26)+cfsigma(27)*dalplip
         sig_aq=0.
      end if
c     N=O
      if(iat.eq.17) then
         sig_lip=cfsigma(28)+cfsigma(29)*dalplip
         sig_aq=0.
      end if
c
c     COO-
c
      if(iat.eq.9) then
         sig_lip=cfsigma(16)*dalplip
         sig_aq=cfsigma(16)*dalpaq
         sig_lip1=0.5*(-cfsigma(9)*func_1+cfsigma(10)*dalplip+
     *     cfsigma(11)*dbetlip-cfsigma(12)*func_1+cfsigma(13)*dalplip)
         sig_aq1=0.5*(cfsigma(10)*dalpaq+cfsigma(11)*dbetaq+
     *     cfsigma(13)*dalpaq)
      end if
c
c     NH4+
c
      if(iat.eq.10) then
         sig_lip=cfsigma(17)*dbetlip
         sig_aq=cfsigma(17)*dbetaq
         sig_lip1=-cfsigma(5)*func_1+cfsigma(6)*dbetlip
         sig_aq1=cfsigma(6)*dbetaq
      end if
c
c     Calculate binary sigmas:
c
      fmaq=fm(4)+fm(5)+fm(6)
      surf_h2o=14.0
      rt=0.592
      if(fmaq.gt.0.9999) then
        sig_bil=sig_aq
        if(iat.ge.9) sig_bil1=sig_aq
      else
         dg= (sig_lip-sig_aq)*surf_h2o/rt
         xsl=1./(exp(dg)*fmaq/(1.-fmaq)+1.)
         sig_bil=sig_aq*(1.-xsl)+sig_lip*xsl
c        sig_bil=sig_aq*fmaq+sig_lip*(1.-fmaq)
         if(iat.ge.9) then
            dg= (sig_lip1-sig_aq1)*surf_h2o/rt
            xsl=1./(exp(dg)*fmaq/(1.-fmaq)+1.)
            sig_bil1=sig_aq1*(1.-xsl)+sig_lip1*xsl
c           sig_bil1=sig_aq1*fmaq+sig_lip1*(1.-fmaq)
         end if
      end if
c
c     ehbond= -3./epsbil+0.038
      ehbond=1.30*(alpbil-alp(6))/alp(6)
      if(ehbond.gt.0.) ehbond=0.
c
      sig_pro(iat,mcur)=sig_bil
      if(iat.eq.9) sig_pro(11,mcur)=sig_bil1
c     edip_pro(mcur)=-cfdiel(1)*dpibil
c
c     Block-Walker function:
      edip_pro(mcur)= cfdiel(1)*func_2
c     Abe function:
      echarge_pro(mcur)=func_abe*cfdiel(2)
      ehbond_pro(mcur)=ehbond
c     eclm_pro(mcur)=amp(4)*epair
c     eclm_pro(mcur)=amp(3)*epair
      eclm_pro(mcur)=0.
      return
      end
c
      subroutine func3(eps1,eps2,del)
c     ------------------------------
c     Abe function
c
      del1=1./alog(eps1)-1./(eps1*alog(eps1))-1.
      del2=1./alog(eps2)-1./(eps2*alog(eps2))-1.
      del=del1-del2
      return
      end
c
      subroutine func0(eps1,eps2,del)
c     -------------------------------
c      1/eps difference function
c
      del1=1./eps1
      del2=1./eps2
      del=del1-del2
      return
      end
c
      subroutine func2(eps1,eps2,del)
c     ------------------------------
c     Block-Walker dielectric function
c
      if(eps1.le.1.05) then
         del1=(1./6.)*alog(eps1)
      else
         del1=3.*eps1*alog(eps1)/(eps1*alog(eps1)-eps1+1.)-
     *     6./alog(eps1)-2.
      end if
      if(eps2.le.1.05) then
         del2=(1./6.)*alog(eps2)
      else
         del2=3.*eps2*alog(eps2)/(eps2*alog(eps2)-eps2+1.)-
     *     6./alog(eps2)-2.
      end if
      del=del2-del1
      return
      end
c
      subroutine ener_at(zcur,accs,dipol,iat,charge1,charge2,
     *  eioniz,asaref,hbond,etot,d_etot)
c     -----------------------------------------------------
      parameter (ntypes=17)
      common/tables/sig_pro(ntypes,15000),edip_pro(15000),
     *  echarge_pro(15000),ehbond_pro(15000),
     *  d_sig_pro(ntypes,15000),d_edip_pro(15000),
     *  d_echarge_pro(15000),d_ehbond_pro(15000),
     *  eclm_pro(15000),d_eclm_pro(15000)
c
      easa=0.
      d_easa=0.
      edip=0.
      d_edip=0.
      echarge=0.
      d_echarge=0.
      ehbond=0.
      d_ehbond=0.
      eclm=0.
      d_eclm=0.
      etot=0.
      d_etot=0.
c
      if(accs.eq.0..or.zcur.lt.-50..or.zcur.gt.50.) return
      mcur=(zcur+50.)*100
c
      if(hbond.ne.0.) then
         ehbond=ehbond_pro(mcur)
         d_ehbond=d_ehbond_pro(mcur)
      end if
      if(charge2.ne.0.) then
         eclm=eclm_pro(mcur)
         d_eclm=d_eclm_pro(mcur)
      end if
c
      if(iat.le.8.or.iat.ge.11) then
         easa=sig_pro(iat,mcur)*accs
         echarge=0.
         d_easa=d_sig_pro(iat,mcur)*accs
         d_echarge=0.
      else
         if(asaref.gt.0.) then
            if(accs.ge.asaref) then
               eion=sig_pro(iat,mcur)*accs+echarge_pro(mcur)*charge1
               d_eion=d_sig_pro(iat,mcur)*accs+
     *           d_echarge_pro(mcur)*charge1
            else
               eion=sig_pro(iat,mcur)*accs+charge1*echarge_pro(mcur)
     *          *(accs/asaref)
               d_eion=d_sig_pro(iat,mcur)*accs+
     *           charge1*d_echarge_pro(mcur)
     *          *(accs/asaref)
            end if
         end if
         if(iat.eq.9) then
            eneutr=eioniz+sig_pro(11,mcur)*accs
            d_eneutr=d_sig_pro(11,mcur)*accs
         else
            eneutr=eioniz+sig_pro(3,mcur)*accs
            d_eneutr=d_sig_pro(3,mcur)*accs
         end if
         if(eion.lt.eneutr) then
            echarge=eion
            d_echarge=d_eion
c           ehbond=2.0*ehbond
c           d_ehbond=2.0*d_ehbond
         else
            echarge=eneutr
            d_echarge=d_eneutr
         end if
      end if
c     write (*,'(i4,f6.1,f7.2)') iat, accs,dipol
      if(asaref.gt.0.) then
         if(accs.ge.asaref) then
            edip=edip_pro(mcur)*dipol
            d_edip=d_edip_pro(mcur)*dipol
         else
            edip=edip_pro(mcur)*dipol*(accs/asaref)
            d_edip=d_edip_pro(mcur)*dipol*(accs/asaref)
         end if
      end if
      etot=easa+edip+echarge+ehbond+eclm
      d_etot=d_easa+d_edip+d_echarge+d_ehbond+d_eclm
      return
      end
