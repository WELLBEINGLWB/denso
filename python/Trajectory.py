from numpy import *
import bisect
import pylab
import StringIO


from pylab import arange, array, double, plot, zeros

class NoTrajectoryFound(Exception):
    pass


class Polynomial(object):
    @staticmethod
    def FromString(polynomial_string):
        s = polynomial_string.strip(" \n")
        coeff_list = [double(x) for x in s.split(' ')]
        return Polynomial(coeff_list)

    def __init__(self, coeff_list):
        # NB: we adopt the weak-term-first convention for inputs
        self.coeff_list = coeff_list
        self.q = pylab.poly1d(coeff_list[::-1])
        self.qd = pylab.polyder(self.q)
        self.qdd = pylab.polyder(self.qd)
        self.degree = self.q.order

    def pad_coeff_string(self, new_degree):
        while len(self.coeff_list) <= new_degree:
            self.coeff_list.append(0.)

    def Eval(self, s):
        return self.q(s)

    def Evald(self, s):
        return self.qd(s)

    def Evaldd(self, s):
        return self.qdd(s)

    def Scale(self,coef):
        c = 1
        plist = []
        for i in range(0,len(self.coeff_list)):
            plist.append(c*self.coeff_list[i])
            c *= coef
        return Polynomial(plist)

    def __str__(self):
        return ' '.join(map(str, self.coeff_list))


class Chunk():
    def __init__(self, duration, poly_list):
        self.polynomialsvector = poly_list
        self.dimension = len(poly_list)
        self.duration = duration

        # TODO: current limitation in polynomials
        degrees = [poly.degree for poly in poly_list]
        self.degree = max(degrees)
        for poly in poly_list:
            poly.pad_coeff_string(self.degree)

    def Eval(self, s):
        q = zeros(self.dimension)
        for i in range(self.dimension):
            q[i] = self.polynomialsvector[i].Eval(s)
        return q

    def Evald(self, s):
        qd = zeros(self.dimension)
        for i in range(self.dimension):
            qd[i] = self.polynomialsvector[i].Evald(s)
        return qd

    def Evaldd(self, s):
        qdd = zeros(self.dimension)
        for i in range(self.dimension):
            qdd[i] = self.polynomialsvector[i].Evaldd(s)
        return qdd

    def Retime(self,coef):
        invcoef = 1./coef
        return Chunk(self.duration*coef,[p.Scale(invcoef) for p in self.polynomialsvector])

    def ExtractDOFs(self,dofindices):
        return Chunk(self.duration,[self.polynomialsvector[i] for i in dofindices])

    def __str__(self):
        chunks_str = '\n'.join(map(str, self.polynomialsvector))
        return '%f\n%d\n%s' % (self.duration, self.dimension, chunks_str)


class PiecewisePolynomialTrajectory():
    def __init__(self, chunkslist):
        self.chunkslist = chunkslist
        self.dimension = self.chunkslist[0].dimension
        self.degree = self.chunkslist[0].degree
        self.duration = 0
        self.chunkcumulateddurationslist = []
        for c in chunkslist:
            self.chunkcumulateddurationslist.append(self.duration)
            self.duration += c.duration

    @staticmethod
    def FromString(trajectorystring):
        buff = StringIO.StringIO(trajectorystring)
        chunkslist = []
        while buff.pos < buff.len:
            duration = double(buff.readline())
            dimension = int(buff.readline())
            poly_vector = []
            for i in range(dimension):
                poly_vector.append(Polynomial.FromString(buff.readline()))
            chunkslist.append(Chunk(duration, poly_vector))
        return PiecewisePolynomialTrajectory(chunkslist)

    def FindChunkIndex(self, s):
        if s == 0:
            s = 1e-10
        i = bisect.bisect_left(self.chunkcumulateddurationslist, s) - 1
        remainder = s - self.chunkcumulateddurationslist[i]
        return i, remainder

    def Eval(self, s):
        i, remainder = self.FindChunkIndex(s)
        return self.chunkslist[i].Eval(remainder)

    def Evald(self, s):
        i, remainder = self.FindChunkIndex(s)
        return self.chunkslist[i].Evald(remainder)

    def Evaldd(self, s):
        i, remainder = self.FindChunkIndex(s)
        return self.chunkslist[i].Evaldd(remainder)

    def Plot(self, dt, f='',tstart=0,c=1):
        tvect = arange(0, self.duration + dt, dt)
        qvect = array([self.Eval(t) for t in tvect])
        plot(c*tvect+tstart, qvect, f, linewidth=2)

    def Plotd(self, dt, f='',tstart=0,c=1):
        tvect = arange(0, self.duration + dt, dt)
        qdvect = array([self.Evald(t) for t in tvect])
        plot(c*tvect+tstart, qdvect, f, linewidth=2)

    def Plotdd(self, dt, f='',tstart=0,c=1):
        tvect = arange(0, self.duration + dt, dt)
        qddvect = array([self.Evaldd(t) for t in tvect])
        plot(c*tvect+tstart, qddvect, f, linewidth=2)

    def Retime(self,coef):
        return PiecewisePolynomialTrajectory([c.Retime(coef) for c in self.chunkslist])

    def ExtractDOFs(self,dofindices):
        return PiecewisePolynomialTrajectory([c.ExtractDOFs(dofindices) for c in self.chunkslist])


    def __str__(self):
        return '\n'.join([str(chunk) for chunk in self.chunkslist])


def SimpleInterpolate(q0,q1,qd0,qd1,T):
    a=((qd1-qd0)*T-2*(q1-q0-qd0*T))/T**3
    b=(3*(q1-q0-qd0*T)-(qd1-qd0)*T)/T**2
    c=qd0
    d=q0
    return [d,c,b,a]

def MakeChunk(q0v,q1v,qd0v,qd1v,T):
    polylist = []
    for i in range(len(q0v)):
        polylist.append(Polynomial(SimpleInterpolate(q0v[i],q1v[i],qd0v[i],qd1v[i],T)))
    return Chunk(T,polylist)


# Assumes that i0 < i1
def InsertIntoTrajectory(traj,traj2,s0,s1):
    i0,r0 = traj.FindChunkIndex(s0)
    i1,r1 = traj.FindChunkIndex(s1)
    c0 = traj.chunkslist[i0]
    c1 = traj.chunkslist[i1]
    chunk0 = MakeChunk(c0.Eval(0),c0.Eval(r0),c0.Evald(0),c0.Evald(r0),r0)
    chunk1 = MakeChunk(c1.Eval(r1),c1.Eval(c1.duration),c1.Evald(r1),c1.Evald(c1.duration),c1.duration-r1)
    tolerance = 0.05
    if linalg.linalg.norm(traj2.Eval(0)-c0.Eval(r0))>=tolerance :
        print "Position mismatch at s0 : ", linalg.linalg.norm(traj2.Eval(0)-c0.Eval(r0))
        return None
    if linalg.linalg.norm(traj2.Eval(traj2.duration)-c1.Eval(r1))>=tolerance:
        print "Position mismatch at s1 : ", linalg.linalg.norm(traj2.Eval(traj2.duration)-c1.Eval(r1))
        return None
    if linalg.linalg.norm(traj2.Evald(0)-c0.Evald(r0)) >= tolerance:
        print "Velocity mismatch at s0 : ", linalg.linalg.norm(traj2.Evald(0)-c0.Evald(r0))
        return None
    if linalg.linalg.norm(traj2.Evald(traj2.duration)-c1.Evald(r1)) >= tolerance:
        print "Velocity mismatch at s1: ", linalg.linalg.norm(traj2.Evald(traj2.duration)-c1.Evald(r1))
        return None
    newchunkslist = list(traj.chunkslist)
    for i in range(i1-i0+1):
        newchunkslist.pop(i0)
    newchunkslist.insert(i0,chunk1)
    traj2.chunkslist.reverse()
    for chunk in traj2.chunkslist:
        newchunkslist.insert(i0,chunk)
    newchunkslist.insert(i0,chunk0)
    return(PiecewisePolynomialTrajectory(newchunkslist))


def SubTraj(traj,s0,s1=-1):
    newchunkslist = []
    if s1 == -1:
        s1 = traj.duration
    i0,r0 = traj.FindChunkIndex(s0)
    i1,r1 = traj.FindChunkIndex(s1)
    c0 = traj.chunkslist[i0]
    c1 = traj.chunkslist[i1]
    if i0 == i1 :
        newchunkslist.append(MakeChunk(c0.Eval(r0),c0.Eval(r1),c0.Evald(r0),c0.Evald(r1),r1-r0))
    else:
        newchunkslist.append(MakeChunk(c0.Eval(r0),c0.Eval(c0.duration),c0.Evald(r0),c0.Evald(c0.duration),c0.duration-r0))
        i = i0+1
        while i < i1:
            newchunkslist.append(traj.chunkslist[i])
            i = i+1
        newchunkslist.append(MakeChunk(c1.Eval(0),c1.Eval(r1),c0.Evald(0),c0.Evald(r1),r1))
    return PiecewisePolynomialTrajectory(newchunkslist)


def Diff(traj1,traj2,nsamples):
    traja = traj1.Retime(traj2.duration/traj1.duration)
    trajb = traj2
    dpos = 0
    dvel = 0
    dacc = 0
    for t in linspace(0,traja.duration,nsamples):
        deltapos = traja.Eval(t) - trajb.Eval(t)
        deltavel = traja.Evald(t) - trajb.Evald(t)
        deltaacc = traja.Evaldd(t) - trajb.Evaldd(t)
        dpos += dot(deltapos,deltapos)
        dvel += dot(deltavel,deltavel)
        dacc += dot(deltaacc,deltaacc)
    return sqrt(dpos)/nsamples, sqrt(dvel)/nsamples, sqrt(dacc)/nsamples

def Diff2(traj1,traj2,nsamples):
    dpos = 0
    dvel = 0
    dacc = 0
    c = traj2.duration/traj1.duration
    for t in linspace(0,traj1.duration,nsamples):
        deltapos = traj1.Eval(t) - traj2.Eval(t*c)
        deltavel = traj1.Evald(t) - traj2.Evald(t*c)
        deltaacc = traj1.Evaldd(t) - traj2.Evaldd(t*c)
        dpos += dot(deltapos,deltapos)
        dvel += dot(deltavel,deltavel)
        dacc += dot(deltaacc,deltaacc)**2
    return sqrt(dpos)/nsamples, sqrt(dvel)/nsamples, sqrt(dacc)/nsamples
