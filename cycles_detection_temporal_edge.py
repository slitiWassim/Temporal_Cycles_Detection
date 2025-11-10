from collections import defaultdict
import numpy as np 
from itertools import chain
from raphtory import algorithms as rp
from bisect import bisect_right


def temporal_cycles(rolling_g, max_length=None, max_cycles=None, max_duration=None):
    
    """
    Enumerate all temporal cycles in a temporal graph with duration < max_duration.
    
    """
    
    components = [list(value.name) for _, value in rp.strongly_connected_components(rolling_g).groups() if len(value) > 1]
    
    ## only keep nodes that could be in a cycle
    nodes = list(chain.from_iterable(components))
    rolling_g = rolling_g.subgraph(nodes)
    
    cycle_count = [0]
    adjacency = defaultdict(dict)

    # ---- Build adjacency: significantly improves performance by avoiding repeated per-edge timestamp scans. ----
    for node in rolling_g.nodes:
        for edge in node.out_edges:
            times = sorted(edge.history().tolist())
            if times:
                adjacency[node.name][edge.dst.name] = times

    
    def _out_neighbors(node_id, prev_time):
        for nbr, times in adjacency[node_id].items():
            if prev_time is None:
                for t in times:
                    yield nbr, t
            else:
                idx = bisect_right(times, prev_time)
                for t in times[idx:]:
                    yield nbr, t


    # ---- Johnson-like cycle search ----
    def johnson_temporal_cycle_search(start):
        path, times_path = [start], []
        blocked = set()
        B = defaultdict(set)

        def unblock(u):
            if u in blocked:
                blocked.remove(u)
                for v in list(B[u]):
                    B[u].remove(v)
                    unblock(v)

        def backtrack(v, last_time):
            closed = False
            blocked.add(v)

            for w, t_next in _out_neighbors(v, last_time):
                # Duration pruning
                if times_path and max_duration and t_next - times_path[0] > max_duration:
                    continue

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

            if closed:
                unblock(v)
            else:
                for w, _ in _out_neighbors(v, None):
                    B[w].add(v)

        yield from backtrack(start, None)


    for comp in components:
        for start in comp:
            for cycle in johnson_temporal_cycle_search(start):
                yield cycle
                if max_cycles and cycle_count[0] >= max_cycles:
                    return