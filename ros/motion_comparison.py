"""Bounded replay diagnostics in original recording time; no control or fusion."""
from collections import deque
import math

def number(value):
    return value if type(value) in {int,float} and math.isfinite(value) else None

class MotionComparison:
    def __init__(self, limit=6000):
        self.start_ns=None
        self.imu=deque(maxlen=limit)
        self.mvo=deque(maxlen=limit)
        self.ages=deque(maxlen=limit)
        self.phases=deque(maxlen=limit)
        self.image_times=deque(maxlen=limit)
        self.last_counts={}

    def relative(self, stamp_ns):
        if self.start_ns is None:self.start_ns=stamp_ns
        return (stamp_ns-self.start_ns)/1e9

    def image(self,stamp_ns):
        self.image_times.append(self.relative(stamp_ns))

    def observe(self,topic,data,recording_stamp):
        self.relative(recording_stamp)
        if topic=='/tello/control_status':
            self.phases.append([self.relative(data.get('stamp_ns',recording_stamp)),data.get('phase','unknown')])
        elif topic=='/tello/image_metadata':
            row=[self.relative(data['image_stamp_ns'])]
            for name in ['flight','log']:
                sample=data.get(name,{})
                row.extend([number(sample.get('age_ms')),bool(sample.get('valid'))])
            self.ages.append(row)
        elif topic=='/tello/raw_log':
            t=self.relative(data.get('received_stamp_ns',recording_stamp))
            native=data.get('data',{})
            for name,target,fields in [
                ('imu',self.imu,['acc_x','acc_y','acc_z','gyro_x','gyro_y','gyro_z','q0','q1','q2','q3']),
                ('mvo',self.mvo,['pos_x','pos_y','pos_z','vel_x','vel_y','vel_z'])]:
                sample=native.get(name,{})
                count=sample.get('count')
                if count is None or count==0 or count==self.last_counts.get(name):continue
                self.last_counts[name]=count
                target.append([t]+[number(sample.get(field)) for field in fields])

    def snapshot(self,current_image_ns):
        return {'start_stamp_ns':self.start_ns,'image_stamp_ns':current_image_ns,
                'image_time':self.relative(current_image_ns) if current_image_ns else None,
                'imu':list(self.imu),'mvo':list(self.mvo),'ages':list(self.ages),
                'phases':list(self.phases),'images':list(self.image_times),
                'note':'Original host timestamps; source axes/units unverified. No telemetry fusion or trajectory alignment.'}
