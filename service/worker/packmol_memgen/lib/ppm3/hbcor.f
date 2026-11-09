      subroutine hbcor(nat,xyz,idon,nres,ifirst,ilast,ibb)
c     -----------------------------------------------------
c     Approximations
c     --------------
c     1. Include only H-bonds formed by at least one solvent-accessible
c        side-chain (backbone-backbone H-bonds are not included; H-bonds
c        by accessible side-chains are included even if they have zero ASA).
c     2. H-bond criteria as in Quanta (pseudo-valent angles >90 deg. and 
c        distance < 3.5A)
c     3. Hbond is assigned to side-chain atom with largest ASA, rather thn
c        distrbuted equally to each H-bond partner
c     4. H-bond energy considered a function of solvent parameter alpha
c     5. No correction for energies of H-bonds involving charged groups
c
      parameter(maxres=30000,maxat=200000)
c
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
      data pi/3.14159/,angcut/90./,dcut/3.5/
c
      real xyz(3,1)
      integer idon(1),ifirst(1),ilast(1),ipair(maxres),ibb(1),
     *  iresacc(maxres)
c
      
      do i=1,nres
         ipair(i)=0
      end do
      do i=1,nat 
         hbond(i)=0.
      end do
c
c     Identify solvent-accessible side-chains:
c
c     do i=1,nres
c        acc=0.
c        do k=ifirst(i),ilast(i)
c           if(ibb(k).ne.1) acc=acc+accs(k)
c        end do
c        if(acc.gt.10.) then
c           iresacc(i)=1
c        else
c           iresacc(i)=0
c        end if
c     end do
c
c     Setting up non-zero ASA for atoms of the solvent-accessible 
c     side-chains. ASA of atoms that do not face lipid 
c     will be nullified later in 'watface' for TM proteins
c
c     do i=1,nres
c        do k=ifirst(i),ilast(i)
c           if(iresacc(i).eq.1.and.ibb(k).eq.0) then
c              if(accs(k).eq.0.) accs(k)=0.05
c           end if
c        end do
c     end do
c
c     Hydrogen bonds
c
      do i=1,nat-2
         do j=i+1,nat
            if(accs(i).gt.0..or.accs(j).gt.0.) then
               if(ibb(i).eq.1.and.ibb(j).eq.1) go to 25
               if(idon(i).eq.0.or.idon(j).eq.0) go to 25
               if(idon(i).eq.1.and.idon(j).eq.1) go to 25
               if(idon(i).eq.2.and.idon(j).eq.2) go to 25
               call dist(xyz,i,j,r23,1)
               if(r23.le.dcut) then
                  k0=max(1,i-30)
c
c                 check valent angles:
c
                  do k=k0,i-1
                     call dist(xyz,k,i,r12,1)
                     if(r12.le.1.8) then
                        call dist(xyz,k,j,r13,2)
                        go to 10
                     end if
                  end do
                  go to 30
   10             continue
                  l0=max(1,j-30)
                  do l=l0,j-1
                     call dist(xyz,l,j,r34,1)
                     if(r34.le.1.8) then
                        call dist(xyz,l,i,r24,2)
                        go to 20
                     end if
                  end do
                  go to 30
   20             continue
                  ph1=acos((r12*r12+r23*r23-r13)/(2.*r12*r23))*180./pi
                  ph2=acos((r23*r23+r34*r34-r24)/(2.*r23*r34))*180./pi
c                 write (*,'(2f8.1)') ph1,ph2
c
                  if(ph1.gt.angcut.and.ph2.gt.angcut) then
c
c                    equal distribution of energy between two partners:
c
                     if(ibb(i).eq.0.and.ibb(j).eq.1) then
                        hbond(i)=1.0
                        go to 22
                     end if
                     if(ibb(j).eq.0.and.ibb(i).eq.1) then
                        hbond(j)=1.0
                        go to 22
                     end if
                     if(accs(i).gt.accs(j)) then
                        hbond(i)=1.0
                     else
                        hbond(j)=1.0
                     end if
   22                continue
                  end if
               end if
   25          continue
            end if
   30       continue
         end do
      end do
c
c     ion pairs
c             
      do i=1,nres-1
         do j=i+1,nres
            do k=ifirst(i),ilast(i)
               do l=ifirst(j),ilast(j)
                  if((iat(k).eq.9.and.iat(l).eq.10).or.
     *               (iat(l).eq.9.and.iat(k).eq.10)) then
                     call dist(xyz,k,l,r12,1)
                     if(r12.le.dcut) then
                        ipair(i)=1
                        ipair(j)=1
                        go to 40
                     end if
                  end if
               end do
            end do
   40       continue
         end do
      end do
c
      do i=1,nres
         if(ipair(i).eq.1) then
            do k=ifirst(i),ilast(i)
               if(iat(k).eq.9.or.iat(k).eq.10) then
                  charge(k)=0.5*charge(k)
               end if
            end do
         end if
      end do
      return
      end
c                 
      subroutine dist(xyz,i,j,d,ind)
c     -----------------------------
      real xyz(3,1)
c
      a=xyz(1,i)-xyz(1,j)
      b=xyz(2,i)-xyz(2,j)
      c=xyz(3,i)-xyz(3,j)
      d=a*a+b*b+c*c
      if(ind.eq.1) d=sqrt(d)
      return
      end
