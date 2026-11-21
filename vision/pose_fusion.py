"""Conservative position blending after external frame/scale alignment.

Noise values are prototype tuning assumptions, not calibrated covariances.
No prediction across tracking loss, no axis inference, no flight commands.
"""
import numpy as np

def blend_position(telemetry,visual,age_ms,speed_m_s,support,reprojection_px,alignment_error_m,gate_m):
    t=np.asarray(telemetry,float);v=np.asarray(visual,float)
    if t.shape!=(3,) or v.shape!=(3,) or not np.isfinite([*t,*v]).all():return None,'invalid position'
    if not np.isfinite([age_ms,speed_m_s,reprojection_px,alignment_error_m,gate_m]).all():return None,'invalid quality'
    if not 0<=age_ms<=400:return None,'stale telemetry'
    if support<12 or not 0<=reprojection_px<=3:return None,'weak visual geometry'
    disagreement=float(np.linalg.norm(t-v))
    if gate_m<=0 or disagreement>gate_m:return None,'pose disagreement'
    # Only speed magnitude is used: velocity coordinate axes are not aligned yet.
    telemetry_noise=.05+max(0,speed_m_s)*age_ms/1000+.00015*age_ms
    visual_noise=max(.03,alignment_error_m)+.02*reprojection_px+.08/np.sqrt(support)
    tw=float(np.clip(visual_noise**2/(telemetry_noise**2+visual_noise**2),.1,.9))
    return {'position':tw*t+(1-tw)*v,'telemetry_weight':tw,'visual_weight':1-tw,
            'disagreement_m':disagreement,'quality_basis':'heuristic; not probability or verified covariance'},None
