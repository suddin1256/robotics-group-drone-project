"""Combined mapper entry point; legacy association helpers retained for compatibility."""
import json
import math
import os
from pathlib import Path
import signal
import time


def inside(x, y, polygon):
    hit = False
    previous = polygon[-1]
    for current in polygon:
        ax, ay = previous
        bx, by = current
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            hit = not hit
        previous = current
    return hit


def match(detection, observation):
    # Never associate results merely because they were the latest available.
    if abs(detection['source_stamp']-observation['source_stamp']) > 0.000002:
        return []
    candidates = []
    for item in detection['objects']:
        polygon = item['polygon']
        if len(polygon) < 3 or item['label'] == 'person':
            continue  # Moving people must not become static floor-plan objects.
        ids = {feature[0] for feature in observation['features']
               if inside(feature[1], feature[2], polygon)}
        if len(ids) >= 6:
            candidates.append({'label': item['label'], 'ids': ids,
                               'confidence': item['confidence']})
    return candidates


def merge(tracks, candidate):
    for track in tracks:
        common = len(track['ids'] & candidate['ids'])
        if track['label'] == candidate['label'] and common >= 3 and common/min(len(track['ids']),len(candidate['ids'])) >= .25:
            track['ids'].update(candidate['ids'])
            track['observations'] += 1
            return
    tracks.append(dict(candidate, observations=1))


def summarize(tracks, data):
    coordinates = dict(zip(data.get('landmark_ids', []), data['points']))
    objects = []
    for index, track in enumerate(tracks):
        points = [coordinates[i] for i in track['ids'] if i in coordinates]
        points = [p for p in points if len(p)==3 and all(math.isfinite(v) for v in p)]
        if len(points) < 6:
            continue
        # Trim isolated support points; these extents are visible support, not full object dimensions.
        axes = [sorted(p[i] for p in points) for i in range(3)]
        low = [a[int((len(a)-1)*.1)] for a in axes]
        high = [a[math.ceil((len(a)-1)*.9)] for a in axes]
        objects.append({'id': index, 'label': track['label'], 'min': low, 'max': high,
                        'support': len(points), 'observations': track['observations'],
                        'tentative': track['observations'] < 2})
    return objects


def main():
    from fused_floorplan import run
    return run()


if __name__ == '__main__':
    main()
