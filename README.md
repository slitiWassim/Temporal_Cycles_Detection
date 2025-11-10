


## How the algorithm works 

<a href="static/images/temporal_cycles.png" target="_blank">
    <image style="border: 2px solid rgb(201, 196, 196);" src="static/images/temporal_cycles.png" width="100%">
</a>

Illustrative example of temporal cycle extraction from a temporal graph. 
- ($\textbf{a}$)  is an example of a temporal cycle $(a \rightarrow b \rightarrow c \rightarrow d \rightarrow a)$. 
- ($\textbf{b}$) Temporal graph with edges annotated by their corresponding timestamps. 
- ($\textbf{c}$) A valid temporal cycle $(a \rightarrow b \rightarrow c \rightarrow d \rightarrow a)$ instance within the temporal graph, with duration $\delta = 9$ and length $L = 4$. 
- ($\textbf{d}$) A structurally valid directed cycle that fails to satisfy temporal ordering, and therefore does not qualify as a temporal cycle.




### 1) Strongly Connected Components decomposition

Following the [NetworkX implementation of Johnson’s algorithm](https://github.com/networkx/networkx/blob/main/networkx/algorithms/cycles.py) ,  the search is restricted to Strongly Connected Components .

Strongly Connected Components (SCCs) are identified using **Raphtory** built-in method.  

### 2) Johnson cycle search

Running the algorithm by examining cycles from every temporal edge individually would cause an exponential increase in complexity due to the vast number of temporal edges in temporal graphs. To improve efficiency, we instead focus on identifying **potentially temporal cycles**. This is achieved by locating structural cycles where consecutive edges $e_t$​ and $e_{t+1}$​ satisfy the temporal consistency condition  $min⁡(e_t.times)<max⁡(e_{t+1}.times)$.

This filtering step significantly reduces the search space while preserving cycles that are likely to be temporally valid.

Within each strongly connected component (SCC), a **modified Johnson backtracking algorithm** is then employed to enumerate structural cycles. Each candidate cycle undergoes **early pruning** through an interval compatibility check ,to ensure temporal feasibility between consecutive edges.

### 3) **Cycle validation**

Each candidate (structural) cycle is passed through `validate_cycle()`, which performs a fine grained temporal validation  by checking for a strictly **increasing sequence of timestamps** across edges.   Only cycles satisfying full temporal consistency are accepted.

Instead of computing the full **Cartesian product** of all timestamp combinations (which can explode combinatorially), it performs **incremental DFS pruning**:

- At each step, it picks the next timestamp that is strictly larger than the last chosen one.    
- It stops early when no valid next timestamp exists.

