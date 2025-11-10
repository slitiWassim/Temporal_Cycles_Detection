from collections import defaultdict
import numpy as np 
from itertools import chain
from raphtory import algorithms as rp
from bisect import bisect_right


def temporal_cycles_(rolling_g, max_length=None, max_cycles=None, max_duration=None):
    """
    Enumerate **temporal cycles** in a Raphtory temporal directed graph.
    
    """

    # Extract strongly connected components with >1 node (only these can contain cycles)
    components = [list(value.name) for _, value in rp.strongly_connected_components(rolling_g).groups() if len(value) > 1]

    # Restrict graph to nodes eligible for cycles
    nodes = list(chain.from_iterable(components))
    rolling_g = rolling_g.subgraph(nodes)

    cycle_count = [0]
    adjacency = defaultdict(dict)

    # ---- Pre-build adjacency with sorted timestamp histories (performance-critical) ----
    for node in rolling_g.nodes:
        for edge in node.out_edges:
            times = sorted(edge.history().tolist())
            if times:
                adjacency[node.name][edge.dst.name] = times

    # ---- Iterate components and start temporal Johnson search for each start node ----
    for comp in components:
        for start in comp:
            for cycle in johnson_temporal_cycle_search(start, adjacency, max_length, max_cycles, max_duration, cycle_count):
                yield cycle
                if max_cycles and cycle_count[0] >= max_cycles:
                    return


#  Iterate over temporal neighbors respecting time order
# ------------------------------------------------------------
def _out_neighbors(node_id, prev_time, adjacency):
    """
    Yields (neighbor, timestamp) pairs for a given node, constrained by temporal ordering.
    If prev_time is None, yields all timestamps. Otherwise, yields only timestamps >= prev_time.
    """
    for nbr, times in adjacency[node_id].items():
        if prev_time is None:
            for t in times:
                yield nbr, t
        else:
            idx = bisect_right(times, prev_time)
            for t in times[idx:]:
                yield nbr, t



#  Johnson-like temporal cycle search for a given start node
# ------------------------------------------------------------
def johnson_temporal_cycle_search(start, adjacency, max_length, max_cycles, max_duration, cycle_count):
    """
    Perform temporal cycle search starting from `start`, following timestamp ordering rules,
    and applying cycle length and temporal duration constraints.
    """

    path, times_path = [start], []
    blocked = set()
    B = defaultdict(set)

    # --- Classic Johnson unblock logic ---
    def unblock(u):
        if u in blocked:
            blocked.remove(u)
            for v in list(B[u]):
                B[u].remove(v)
                unblock(v)

    # --- Depth-first temporal cycle exploration ---
    def backtrack(v, last_time):
        closed = False
        blocked.add(v)

        for w, t_next in _out_neighbors(v, last_time, adjacency):

            # Duration filter check
            if times_path and max_duration and t_next - times_path[0] > max_duration:
                continue

            # Found a cycle
            if w == start:
                duration = t_next - times_path[0] if times_path else 0
                if (
                    (max_length is None or len(path) <= max_length)
                    and (max_duration is None or duration <= max_duration)
                ):
                    cycle_count[0] += 1
                    yield (path[:] + [start], times_path[:] + [t_next])
                    closed = True
                    if max_cycles and cycle_count[0] >= max_cycles:
                        return

            # Continue depth-first search
            elif w not in path and (max_length is None or len(path) < max_length):
                path.append(w)
                times_path.append(t_next)
                for result in backtrack(w, t_next):
                    yield result
                    closed = True
                    if max_cycles and cycle_count[0] >= max_cycles:
                        return
                path.pop()
                times_path.pop()

        # Johnson block bookkeeping
        if closed:
            unblock(v)
        else:
            for w, _ in _out_neighbors(v, None, adjacency):
                B[w].add(v)

    yield from backtrack(start, None)



