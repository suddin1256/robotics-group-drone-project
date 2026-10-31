"""Experimental frame/scale alignment. All output units remain native and unverified."""
import numpy as np

def similarity(source,target):
    x=np.asarray(source,float);y=np.asarray(target,float)
    xc=x-x.mean(0);yc=y-y.mean(0)
    u,s,vt=np.linalg.svd(yc.T@xc/len(x))
    signs=np.ones(3);signs[-1]=np.sign(np.linalg.det(u@vt))
    rotation=(u*signs)@vt
    variance=np.mean(np.sum(xc*xc,axis=1))
    if variance<1e-12:raise ValueError('Insufficient displacement')
    scale=np.sum(s*signs)/variance
    return scale,rotation,y.mean(0)-scale*rotation@x.mean(0)

def fit_similarity(source,target):
    x=np.asarray(source,float);y=np.asarray(target,float)
    if len(x)<8:return None
    if not np.isfinite(x).all() or not np.isfinite(y).all():return None
    for points in [x,y]:
        s=np.linalg.svd(points-points.mean(0),compute_uv=False)
        if s[0]<1e-5 or s[1]/s[0]<.02:return None
    spread=float(np.median(np.linalg.norm(y-np.median(y,axis=0),axis=1)))
    if spread<1e-4:return None
    threshold=.18*spread
    rng=np.random.default_rng(7);best=None
    for indices in [np.arange(len(x))]+[rng.choice(len(x),3,replace=False) for _ in range(64)]:
        try:
            scale,r,t=similarity(x[indices],y[indices])
            if not 1e-6<scale<1e6:continue
            errors=np.linalg.norm(scale*x@r.T+t-y,axis=1)
            good=errors<threshold
            score=int(good.sum())
            if best is None or score>best[0]:best=(score,good)
        except (np.linalg.LinAlgError,ValueError):continue
    if best is None or best[0]<max(6,int(np.ceil(.65*len(x)))):return None
    good=best[1];scale,r,t=similarity(x[good],y[good])
    errors=np.linalg.norm(scale*x[good]@r.T+t-y[good],axis=1)
    error=float(np.median(errors))
    if error>.12*spread:return None
    return {'scale':float(scale),'rotation':r,'translation':t,'error':error,
            'spread':spread,'inliers':good,'pairs':len(x)}

def quaternion_matrix(imu):
    try:q=np.asarray([imu['q'+str(i)] for i in range(4)],float)
    except (KeyError,TypeError,ValueError):return None
    n=np.linalg.norm(q)
    if not np.isfinite(q).all() or not .9<n<1.1:return None
    w,x,y,z=q/n
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def rotation_mean(rotations):
    u,_,vt=np.linalg.svd(np.sum(rotations,axis=0))
    d=np.eye(3);d[2,2]=np.sign(np.linalg.det(u@vt))
    return u@d@vt

def orientation_alignment(native_rotations,visual_rotations,world_rotation):
    if len(native_rotations)<5:return None
    change=[np.arccos(np.clip((np.trace(native_rotations[0].T@q)-1)/2,-1,1)) for q in native_rotations]
    if max(change)<np.deg2rad(5):return None
    best=None
    for transpose in [False,True]:
        qs=[q.T if transpose else q for q in native_rotations]
        offset=rotation_mean([q.T@world_rotation@v for q,v in zip(qs,visual_rotations)])
        errors=[np.arccos(np.clip((np.trace((q@offset).T@world_rotation@v)-1)/2,-1,1)) for q,v in zip(qs,visual_rotations)]
        error=float(np.median(errors))
        if best is None or error<best['error']:best={'offset':offset,'transpose':transpose,'error':error}
    return best if best['error']<np.deg2rad(20) else None

def fit_inverse_depth(signal,z):
    x=np.asarray(signal,float);z=np.asarray(z,float)
    valid=np.isfinite(x)&np.isfinite(z)&(z>1e-5);x=x[valid];z=z[valid]
    if len(x)<16 or np.std(x)<1e-5:return None
    inv=1/z;threshold=.25*np.median(inv);rng=np.random.default_rng(11);best=None
    for pair in [np.arange(len(x))]+[rng.choice(len(x),2,replace=False) for _ in range(48)]:
        a,b=np.linalg.lstsq(np.column_stack([x[pair],np.ones(len(pair))]),inv[pair],rcond=None)[0]
        if a<=0:continue
        good=np.abs(a*x+b-inv)<threshold
        if best is None or good.sum()>best.sum():best=good
    if best is None or best.sum()<max(12,.6*len(x)):return None
    a,b=np.linalg.lstsq(np.column_stack([x[best],np.ones(best.sum())]),inv[best],rcond=None)[0]
    error=float(np.median(np.abs(a*x[best]+b-inv[best])/inv[best]))
    if a<=0 or error>.25:return None
    lo,hi=np.quantile(x[best],[.02,.98]);pad=.1*(hi-lo)
    return {'a':float(a),'b':float(b),'min_signal':float(lo-pad),'max_signal':float(hi+pad),
            'min_z':float(np.quantile(z[best],.02)*.5),'max_z':float(np.quantile(z[best],.98)*2),
            'error':error,'support':int(best.sum())}

def native_sample(metadata):
    log=metadata.get('log',{})
    if not log.get('valid') or not log.get('sample'):return None
    raw=log['sample'].get('data',{});mvo=raw.get('mvo',{})
    if not mvo.get('count'):return None
    try:position=np.array([mvo['pos_'+i] for i in 'xyz'],float)
    except (KeyError,ValueError,TypeError):return None
    if not np.isfinite(position).all():return None
    age=log.get('age_ms')
    if age is None:return None
    if raw.get('recv_time') is not None and mvo.get('recv_time') is not None:
        age+=max(0,raw['recv_time']-mvo['recv_time'])*1000
    if age>400:return None
    flight=metadata.get('flight',{}).get('sample') or {}
    airborne=metadata.get('phase')=='airborne' or flight.get('data',{}).get('em_sky')==1
    imu=raw.get('imu',{});rotation=quaternion_matrix(imu)
    imu_age=log.get('age_ms',0)
    if raw.get('recv_time') is not None and imu.get('recv_time') is not None:
        imu_age+=max(0,raw['recv_time']-imu['recv_time'])*1000
    if not imu.get('count') or imu_age>250:rotation=None
    return {'position':position,'rotation':rotation,
            'count':mvo['count'],'age_ms':age,'airborne':airborne}
