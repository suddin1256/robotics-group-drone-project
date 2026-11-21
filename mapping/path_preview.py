"""Offline 3D A* preview only. Never publishes a path or commands to the drone."""
import heapq,itertools,math

def plan_preview(occupancy,start,goal,clearance_cells=2,max_expansions=100000):
    if clearance_cells<1:raise ValueError('Require at least one cell of clearance')
    cells={tuple(row['cell']):row['state'] for row in occupancy.get('cells',[])}
    free={p for p,state in cells.items() if state=='free_candidate'}
    # Unknown and occupied cells are blocked, including unknown space outside the map.
    offsets=[o for o in itertools.product(range(-clearance_cells,clearance_cells+1),repeat=3) if sum(v*v for v in o)<=clearance_cells**2]
    def clear(p):return all(tuple(p[i]+o[i] for i in range(3)) in free for o in offsets)
    start=tuple(start);goal=tuple(goal)
    if not clear(start) or not clear(goal):raise ValueError('Start/goal lacks observed clearance; unknown space is blocked')
    queue=[(0,start)];cost={start:0};parent={};expanded=0
    while queue and expanded<max_expansions:
        _,point=heapq.heappop(queue);expanded+=1
        if point==goal:
            path=[point]
            while point in parent:point=parent[point];path.append(point)
            return {'cells':list(reversed(path)),'preview_only':True,'autonomous_allowed':False,'units':occupancy.get('units'),'expanded':expanded}
        for axis in range(3):
            for step in [-1,1]:
                neighbour=list(point);neighbour[axis]+=step;neighbour=tuple(neighbour)
                if not clear(neighbour):continue
                distance=cost[point]+1
                if distance<cost.get(neighbour,math.inf):
                    cost[neighbour]=distance;parent[neighbour]=point
                    heapq.heappush(queue,(distance+sum(abs(neighbour[i]-goal[i]) for i in range(3)),neighbour))
    raise ValueError('No path with observed clearance (or preview search limit reached)')
