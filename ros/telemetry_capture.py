"""Loss-aware JSON telemetry and image association helpers; no hardware imports."""
import math

def plain(value, depth=0):
    if depth > 5:
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return {'hex': value.hex()}
    if isinstance(value, (tuple,list)):
        return [plain(v,depth+1) for v in value]
    fields = value if isinstance(value,dict) else vars(value) if hasattr(value,'__dict__') else {}
    return {str(k):plain(v,depth+1) for k,v in fields.items()
            if not str(k).startswith('_') and k not in {'log'}}

def previous_sample(samples, stamp_ns, max_age_ns=250_000_000):
    for item in reversed(samples):
        age=stamp_ns-item['received_stamp_ns']
        if age >= 0:
            return {'sample':item if age<=max_age_ns else None,
                    'age_ms':age/1e6,'valid':age<=max_age_ns}
    return {'sample':None,'age_ms':None,'valid':False}
