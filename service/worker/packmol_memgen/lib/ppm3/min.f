      SUBROUTINE ENERGY (VAR,ETOT,GR,MSW)
c     ----------------------------------
c     Calculation of energy and derivatives
c
c     variables: 1 - shift, 2 - phi, 3 - teta
c     dc(i) are derivatives of atomic transfer energies by
c     z coordinate
c
      parameter (maxvar=3,n_var=3,maxat=200000)
c
      common /coord/ nat,xyz(3,maxat),prod(maxat),ifunc,z0
      common/params/ accs(maxat),iat(maxat),dip(maxat),eioniz(maxat),
     *  charge(maxat),asaref(maxat),hbond(maxat),charge2(maxat)
c
c     xyz are initial (input) coordinates; they are kept unchanged
c
      real VAR(maxvar),GR(maxvar),xyzc(3,maxat),
     *  eal(maxat),eal1(maxat),dc(maxat),eatom(maxat)
c
      alpha=1.11
c
c     Transform coordinates:
c
      shift=var(1)
      phi=var(2)
      teta=var(3)
      call tilting (phi,teta,nat,xyz,xyzc)
c
      do i=1,nat
         eatom(i)=0.
         dc(i)=0.
      end do
c
      do i=1,nat
         xyzc(3,i)=xyzc(3,i)+shift
         if(prod(i).ne.0.) then
            zc=xyzc(3,i)
            if(ifunc.eq.1) then
               eal(i)=exp(alpha*(abs(zc)-z0))
               eal1(i)=1./(1.+eal(i))
            else
               call ener_at(zc,accs(i),dip(i),iat(i),
     *           charge(i),charge2(i),eioniz(i),asaref(i),
     *           hbond(i),eatom(i),dc(i))
            end if
         end if
      end do
c
c     Calculate energy
c
      if(msw.ne.2) then
         e=0.
         if(ifunc.eq.1) then
            do i=1,nat
               if(prod(i).ne.0.) e=e+eal1(i)*prod(i)
            end do
         else
            do i=1,nat
               if(prod(i).ne.0.) e=e+eatom(i)
            end do
         end if
         etot=e
c        write (*,'(i1,f7.1,4f8.2)') msw,etot,(var(j),j=1,3)
      end if
c
c     Calculate derivatives
c
      if(msw.ge.2) then
         si=sin(phi)
         co=cos(phi)
         if(ifunc.eq.1) then
            do i=1,nat
               if(prod(i).ne.0.) dc(i)=eal1(i)*eal1(i)*eal(i)*
     *           prod(i)*alpha
            end do
         end if
         do j=1,3
            gr(j)=0.
         end do
         do i=1,nat
            if(prod(i).ne.0.) then
               zc=xyzc(3,i)
               if(ifunc.eq.1) then
                  if(zc.gt.0.) then
                     gr(1)=gr(1)-dc(i)
                  else
                     gr(1)=gr(1)+dc(i)
                  end if
               else
                  gr(1)=gr(1)+dc(i)
               end if
               gr(2)=gr(2)+dc(i)*(xyzc(1,i)*co+xyzc(2,i)*si)
               gr(3)=gr(3)+dc(i)*(xyzc(2,i)*co-xyzc(1,i)*si)
            end if
         end do
         gr(2)=-sin(teta)*gr(2)
c        write (*,'(i1,f7.1,4f8.2)') msw,etot,(var(j),j=1,3)
      end if
      return
      end

c
      SUBROUTINE MIN12(KOD,N,X,FX,G,GM,DS,EST,FG,MINLN,OUTN,H,B,IER)
C
      EXTERNAL FG
      DIMENSION FX(1),H(1),B(1),DS(1),GM(1),G(1),EST(8),KOD(8),X(1)
C
      M=0
      M1=KOD(6)
      MET=KOD(7)
      KN=KOD(8)
      N2=N+N
      N3=N2+N
      N31=N3+1
C
 101  CALL ROUTE (KOD,N,X,FX)
C
      CALL FG (X,FX,G,2)
C
      IER=4
      DO 102 I=1,N
      IF(ABS(G(I)).GT.GM(I)) GO TO 105
 102  CONTINUE
      GO TO 104     
 105  IF (M.EQ.KN) M=0
      IF (M1.EQ.2) GO TO 21
      IF (MET.NE.0.AND.M.GT.0) GO TO 5
    1 K=N31
      DO 4 J=1,N
      H(K)=1.
      NJ=N-J
      IF(NJ)21,21,2
    2 DO 3 L=1,NJ
      KL=K+L
    3 H(KL)=.0
    4 K=KL+1
    5 DO 6 J=1,N
      K=N+J
      H(K)=G(J)-H(K)
      K=N+K
    6 H(K)=X(J)-H(K)
      Z=.0
      DO 7 J=1,N
      K=N+J
      W=H(K)
      K=K+N
   7  Z=Z+W*H(K)
      ALFA=.0
      DO 11 J=1,N
      K=J+N3
      W=0.
      DO 10 L=1,N
      KL=N+L
      W=W+H(KL)*H(K)
      IF(L-J) 8,9,9
    8 K=K+N-L
      GO TO 10
    9 K=K+1
   10 CONTINUE
      K=N+J
      ALFA=ALFA+W*H(K)
   11 H(J)=W
      GO TO (12,13,14,15,12),MET
  12  IF (ALFA) 16,1,16
  13  IF (Z*ALFA)16,1,16
  14  IF (Z-ALFA)16,1,16
  15  IF (Z) 16,1,16
   16 K=N31
      DO 20 L=1,N
      HKL=H(N2+L)
      HL=H(L)
      DO 20 J=L,N
      HK=H(K)
      HJ=H(J)
      HNJ=H(N2+J)
      GO TO (17,19,18,26,27),MET
  17  HK=HK-HL*HJ/ALFA
      GO TO 28
  18  HK=HK+(HKL-HL)*(HNJ-HJ)/(Z-ALFA)
      GO TO 28
  19  HK=HK+HKL*HNJ/Z-HL*HJ/ALFA
      GO TO 28                        
  26  HK=HK+(HKL-HL)*HNJ/Z
      GO TO 28
  27  HK=HK+(HKL-HL)*HJ/ALFA
  28  H(K)=HK
   20 K=K+1
   21 DO 25 J=1,N
      K=N+J
      H(K)=G(J)
      K=K+N
      H(K)=X(J)
      K=J+N3
      T=0.
      DO 24 L=1,N
      T=T-G(L)*H(K)
      IF(L-J)22,23,23
   22 K=K+N-L
      GO TO 24
   23 K=K+1
   24 CONTINUE
   25 H(J)=T
      M1=0
      M=M+1
      IF (M.EQ.1) GO TO 103
      DY=0.
      DO 29 J=1,N
  29  DY=DY+H(J)*G(J)
      IF (DY) 103,30,30
  30  M=0
      GO TO 1
C
  103 CALL MINLN(KOD,N,X,FX,H,FG,EST,B,IER)
C
      IF(IER.EQ.1) GO TO 104
      IF (KOD(4).LE.0) GO TO 106
C
      CALL OUTN(KOD,N,X,FX,DS,EST,IER)
C
      IF (IER) 101,104,104
C
 106  IER=3
 104  RETURN
      END
C
      SUBROUTINE MINL2(KOD,N,X,FX,S,F,EST,Y,IER)
C      -------------------------------------------.
C    O  PO-PAMMA B   C EH   M H M MA B |A AHHOM HA PAB EH     TEM
C   KBA PAT  HO  A  POKC MA    C  PE BAP TE  HO   OKA  |A  E
C
      DIMENSION  X(N),Y(N),S(N)
      DIMENSION  EST(8),KOD(8)
      LIM=MIN0(KOD(3),KOD(4))
      L1=LIM
      H=0.
      DO 66 I=1,N
   66 H=H+S(I)*S(I)
      GN=SQRT(H)
      H=EST(2)*EST(5)/GN
      DL=EST(4)/GN
      D=H
      D1=0.
      D2=0.
      F1=FX
      F2=FX
      K=LIM-1
    5 DO 1 I=1,N
    1 Y(I)=X(I)+D*S(I)
      CALL F(Y,FY,1,1)
      LIM=LIM-1
      IF(LIM) 20,20,2
    2 IF(FY-F2) 3,4,4
    3 D1=D2
      D2=D
      F1=F2
      F2=FY
      D=2.*D+H
      GO TO 5
    4 IF(K-LIM) 100,6,7
    7 D3=D
      F3=FY
      GO TO 50
    6 IF(ABS(D)-DL) 8,8,9
    8 EST(2)=0.
      GO TO 100
    9 D3=D
      F3=FY
      D=D/2.
      DO 33 I=1,N
   33 Y(I)=X(I)+D*S(I)
      CALL F(Y,FY,1,1)
      LIM=LIM-1
      IF(LIM) 20,20,11
   11 IF(FY-F1) 12,6,6
   12 F2=FY
      D2=D
      H=D
      GO TO 15
   50 D=(D2+D3)/2.
      H=D2-D1
      DO 13 I=1,N
   13 Y(I)=X(I)+D*S(I)
      CALL F(Y,FY,1,1)
      LIM=LIM-1
      IF(LIM) 20,20,10
   10 IF(FY-F2) 16,16,17
   16 D1=D2
      D2=D
      F1=F2
      F2=FY
      GO TO 15
   17 D3=D
      F3=FY
   15 R=F1-2.*F2+F3
      IF(R) 40,41,40
   40 D=D2+H* (F1-F3)/(2.*R)
   41 DO 18 I=1,N
   18 Y(I)=X(I)+D*S(I)
      CALL F(Y,FY,1,1)
      LIM=LIM-1
      IER=0
      IF(LIM) 20,20,19
   19 IF(FY-F1) 21,22,22
   21 H=FY
   25 IF(H-F2) 23,24,24
   23 IF(H-F3) 26,32,32
   26 IF(H-F1) 28,29,28
   28 FX=FY
      D0=D
   90 DO 91 I=1,N
   91 X(I)=X(I)+D0*S(I)
      EST(2)=D0*GN
  100 KOD(4)=KOD(4)-L1+LIM
      RETURN
   22 H=F1
      GO TO 25
   29 D0=D1
      FX=F1
      GO TO 90
   24 IF(F2-F3) 31,31,32
   31 D0=D2
      FX=F2
      GO TO 90
   32 D0=D3
      FX=F3
      GO TO 90
   20 IF(FY-F2) 36,31,31
   36 FX=FY
      D0=D
      GO TO 90
      END
C
      SUBROUTINE OUT2(KOD,N,X,FX,DS,EST,IER)
C     ----------------------------------*
      DIMENSION KOD(6),EST(6)
      DIMENSION X(N,2),FX(2),DS(N)
      DF=EST(6)
      KOD(5)=KOD(5)-1
      IER=-1
      IF(KOD(5).LE.0) IER=2
      R=ABS(FX(1)-FX(2))
      IF(R-DF) 1,1,2
    1 DO5   I=1,N
      R=ABS(X(I,1)-X(I,2))
      IF(R-DS(I)) 5,5,2
    5 CONTINUE
      IER=0
    2 RETURN
      END
C
      SUBROUTINE ROUTE(KOD,N,X,FX)
C     ------------------------------
      DIMENSIONX(N,1),FX(1),KOD(2)
      IF(KOD(2).EQ.KOD(1))KOD(2)=KOD(2)-1
      J=KOD(2)
    1 IF(J) 4,4,2
    2 DO 3 I=1,N
    3 X(I,J+1)=X(I,J)
      FX(J+1)=FX(J)
      J=J-1
      GO TO 1
    4 KOD(2)=KOD(2)+1
      RETURN
      END
