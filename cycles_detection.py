from collections import defaultdict
import numpy as np 
from itertools import chain
from raphtory import algorithms as rp
from raphtory import Graph


# ---- Main function ----
def temporal_cycles(
    rolling_g,
    max_length=None,
    max_cycles=None,
    max_duration=None,
    max_combo=None
):
    """
    Enumerate **temporal cycles** in a Raphtory temporal directed graph.

    This algorithm identifies all elementary cycles where the sequence of edge timestamps
    is **strictly increasing** — ensuring that the traversal follows the arrow of time.
    It combines a structural depth-first cycle search (based on Johnson's algorithm [1]_)
    with efficient temporal validation using stored edge timestamp histories.


    Parameters
    ----------
    rolling_g : Raphtory Graph
        A Raphtory temporal knowledge graph. 

    max_length : int, optional
        Maximum number of distinct nodes allowed in a cycle.
        Limits cycle depth to control computational growth.
        Default is ``None`` (no structural limit).

    max_cycles : int, optional
        Stop after this many **valid** cycles have been found.
        Prevents memory overload in dense graphs. Default is ``None``.

    max_duration : int, optional
        Maximum duration (in milliseconds) between the earliest and latest
        timestamps within a cycle. Cycles exceeding this temporal span are skipped.
        Default is ``None`` (no duration filter).

    max_combo : int, optional
        Stop validating a cycle once this many temporal cycle timestamp
        combinations have been found. Default is ``None`` (no limit).

    Yields
    ------
    (cycle_nodes, cycle_timestamps) : 
        - **cycle_nodes** : list of node names forming a cycle (start node repeated at end).
        - **cycle_timestamps** : list of timestamps (strictly increasing) associated with the edges.

        Each yielded pair corresponds to a time-respecting cycle

    Notes
    -----
    The algorithm proceeds in several conceptual stages:


    1. **SCC decomposition:**  
       Identify strongly connected components (SCCs) using Raphtory's built-in method.
       Following the implementation of NetworkX for detecting cycles in directed graphs,
       Johnson's algorithm is enhanced with well-known preprocessing techniques by restricting
       the search to strongly connected components. https://github.com/networkx/networkx/blob/main/networkx/algorithms/cycles.py

    2. **Johnson-style search:**  
       Perform a modified Johnson's backtracking algorithm within each SCC to
       enumerate structural cycles, pruned by temporal interval compatibility.
      
    3. **Cycle validation:**  
       Each structural cycle is checked via ``validate_cycle()`` to ensure that
       an increasing sequence of timestamps exists along the edges.

    4. **Yielding results:**  
       Only temporally valid cycles are yielded. Duration, length, and count
       constraints are enforced throughout.


    References
    ----------
    .. [1] Johnson, D. B. (1975). *Finding all the elementary circuits of a directed graph.*
           SIAM Journal on Computing, 4(1), 77-84. https://doi.org/10.1137/0204007

    Examples
    --------
    >>> cycles = time_respecting_cycles(rolling_g, max_length=4, max_cycles=500)
    >>> for nodes, times in cycles:
    ...     print(nodes, times)
    ('A', 'B', 'C', 'A') [102, 134, 180]
    """

    # ---- Strongly connected components ----
    components = [list(value.name) for _, value in rp.strongly_connected_components(rolling_g).groups() if len(value) > 1]
    
    ## only keep nodes that could be in a cycle
    nodes = list(chain.from_iterable(components))
    rolling_g = rolling_g.subgraph(nodes)

    cycle_count = [0]

    # ---- Main cycle search ----
    for comp in components:
        for start in comp:
            for raw_cycle_nodes,_ in johnson_cycle_search(start,
                                                          rolling_g,
                                                          cycle_count,
                                                          max_length,
                                                          max_cycles,
                                                          max_duration
                                                           ):
                
                edge_cycle = list(zip(raw_cycle_nodes[:-1], raw_cycle_nodes[1:]))
                valid_cycles = validate_cycle(rolling_g,edge_cycle,max_duration,max_combo)
                if valid_cycles:
                    cycle_count[0] += len(valid_cycles)
                    for vc in valid_cycles:
                        yield vc
                    if max_cycles and cycle_count[0] >= max_cycles:
                        return



# ---- Johnson cycle search ----
#   A modified Johnson-style cycle enumeration procedure extended to temporal graphs.
#   Each candidate path is evaluated under timestamp interval constraints, ensuring that
#   only structurally valid and temporally feasible cycles (strictly increasing in time)
#   are enumerated.
def johnson_cycle_search(
    start,
    rolling_g,
    cycle_count,
    max_length,
    max_cycles,
    max_duration
):
    path = [start]
    times_path = []
    blocked = set()
    B = defaultdict(set)

    def unblock(u):
        if u in blocked:
            blocked.remove(u)
            for v in list(B[u]):
                B[u].remove(v)
                unblock(v)

    def backtrack(v, prev_interval):
        closed = False
        blocked.add(v)

        for w, next_interval in out_neighbors(v, prev_interval, rolling_g):
            if max_duration and times_path:
                duration = next_interval[0] - times_path[0][1]
                if duration > max_duration:
                    continue

            if w == start:
                duration = next_interval[0] - times_path[0][1] if times_path else 0
                if ((max_length is None or len(path) <= max_length)
                    and (max_duration is None or duration <= max_duration)):
                    yield (path[:] + [start], times_path[:] + [next_interval])
                    closed = True
                    if max_cycles and cycle_count[0] >= max_cycles:
                        return

            elif w not in path and (max_length is None or len(path) < max_length):
                path.append(w)
                times_path.append(next_interval)
                for result in backtrack(w, next_interval):
                    yield result
                    closed = True
                    if max_cycles and cycle_count[0] >= max_cycles:
                        return
                path.pop()
                times_path.pop()

        if closed:
            unblock(v)
        else:
            for edge in rolling_g.node(v).out_edges:
                B[edge.dst.name].add(v)

    yield from backtrack(start, None)


# ---- Generates feasible outgoing edges. ----
def out_neighbors(node_id, prev_interval, rolling_g):
    node = rolling_g.node(node_id)
    for edge in node.out_edges:

        # Earliest/Latest Time from temporal edges
        next_interval = (int(edge.earliest_time), int(edge.latest_time))

        # first edge -> always allowed
        if prev_interval is None:
            yield edge.dst.name, next_interval
            continue

        # enforce strictly increasing feasible interval : Max(next_edge_times) > Min(prev_edge_times)
        if next_interval[1] > prev_interval[0]:
            yield edge.dst.name, next_interval



# ---- validate_cycle : Checks whether an edge cycle satisfies temporal constraints. ----
def validate_cycle(rolling_g, edge_cycle, max_duration=None, max_combo=None):
    """
    Validate whether a structural cycle (list of edges) admits one or more
    strictly time-increasing realizations, optionally stopping once max_combo
    realizations have been found.

    Returns:
        A list of unique (node_cycle_tuple, timestamp_list)
    """
    time_lists = []
    for src, dst in edge_cycle:
        edge = rolling_g.edge(src=src, dst=dst)
        if edge is None:
            return []
        times = edge.history().tolist()
        if not times:
            return []
        time_lists.append(sorted(int(t) for t in times))

    node_path = [edge_cycle[0][0]] + [dst for _, dst in edge_cycle]
    seen = set()
    results = []

    def dfs(i, prev_t, combo):
        # Early stop if reached max results
        if max_combo is not None and len(results) >= max_combo:
            return

        if i == len(time_lists):
            if max_duration is not None and (combo[-1] - combo[0]) > max_duration:
                return
            nodes_tuple = tuple(node_path)
            times_tuple = tuple(combo)
            key = (nodes_tuple, times_tuple)
            if key not in seen:
                seen.add(key)
                results.append((nodes_tuple, list(combo)))

            return

        for t in time_lists[i]:
            # Early stop inside loop too
            if max_combo is not None and len(results) >= max_combo:
                return

            if t > prev_t:
                combo.append(t)
                dfs(i + 1, t, combo)
                combo.pop()

    dfs(0, float("-inf"), [])
    return results






