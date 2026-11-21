"""Native TelloPy -> prototype metric values. Never mutates raw messages or axes."""
import math

UNIT_AUDIT = {
    'revision': '2026-11-21', 'status': 'units_checked_for_prototype',
    'recordings': 14, 'motion_samples': 5949, 'imu_samples': 11882,
    'accuracy_verified': False, 'coordinate_alignment_verified': False,
    'position_scale_m': 1.0, 'decoded_velocity_scale_m_s': 0.1,
    'acceleration_scale_m_s2': 9.80665, 'gyro_scale_rad_s': 1.0,
    'native_height_scale_m': 0.1, 'light_strength_usable': False,
}

def vector(sample, prefix, scale=1.):
    values=[sample.get(prefix+axis) for axis in 'xyz']
    if not all(type(x) in (int,float) and math.isfinite(x) for x in values):return None
    return [x*scale for x in values]

def metric_log(raw):
    """Convert decoded log values once, retaining the native local coordinate frame."""
    mvo=raw.get('mvo',{});imu=raw.get('imu',{})
    q=[imu.get(k) for k in ['q0','q1','q2','q3']]
    norm=math.sqrt(sum(x*x for x in q)) if all(type(x) in (int,float) and math.isfinite(x) for x in q) else 0
    return {
        'position_native_m':vector(mvo,'pos_') if mvo.get('count') else None,
        'velocity_native_m_s':vector(mvo,'vel_',.1) if mvo.get('count') else None,
        'acceleration_native_m_s2':vector(imu,'acc_',9.80665) if imu.get('count') else None,
        'angular_velocity_native_rad_s':vector(imu,'gyro_') if imu.get('count') else None,
        'quaternion_native_wxyz':[x/norm for x in q] if imu.get('count') and .9<norm<1.1 else None,
        'coordinate_frame':'native_local_axes_not_aligned',
        'z_convention':'observed_down_positive',
        'units_audit':dict(UNIT_AUDIT),
    }

def metric_metadata(metadata):
    log=metadata.get('log',{});sample=log.get('sample') or {}
    raw=sample.get('data',{});result=metric_log(raw)
    result['image_stamp_ns']=metadata.get('image_stamp_ns')
    result['log_age_ms']=log.get('age_ms')
    for name,keys,max_age in [('mvo',['position_native_m','velocity_native_m_s'],400),
                              ('imu',['acceleration_native_m_s2','angular_velocity_native_rad_s','quaternion_native_wxyz'],250)]:
        age=log.get('age_ms');record=raw.get(name,{})
        if age is not None and raw.get('recv_time') is not None and record.get('recv_time') is not None:
            age+=max(0,raw['recv_time']-record['recv_time'])*1000
        valid=bool(log.get('valid') and age is not None and 0<=age<=max_age and record.get('count'))
        result[name+'_valid']=valid;result[name+'_age_ms']=age
        if not valid:
            for key in keys:result[key]=None
    return result
