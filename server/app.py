"""Flask server for Lokus-Synapse."""
import os
import sys
import json
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Add server dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import init_db, clear_all, insert_file, get_file_by_path, upsert_concept, \
    link_file_concept, insert_edge, get_all_files, get_file_detail, get_graph_data, \
    get_concept_graph_data, search, get_stats, set_meta, get_meta
from scanner import scan_directory
from extractor import extract_concepts
from graph import build_graph

app = Flask(__name__, static_folder=None)
CORS(app)

# Global scan state
scan_state = {
    'running': False,
    'total': 0,
    'scanned': 0,
    'current': '',
    'phase': 'idle',
    'error': None
}

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')


@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'name': 'Lokus-Synapse'})


@app.route('/api/stats')
def stats():
    return jsonify(get_stats())


@app.route('/api/files')
def files():
    return jsonify(get_all_files())


@app.route('/api/files/<int:fid>')
def file_detail(fid):
    detail = get_file_detail(fid)
    if not detail:
        return jsonify({'error': 'File not found'}), 404
    return jsonify(detail)


@app.route('/api/graph')
def graph():
    mode = request.args.get('mode', 'files')
    if mode == 'concepts':
        return jsonify(get_concept_graph_data())
    return jsonify(get_graph_data())


@app.route('/api/search')
def search_api():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'files': [], 'concepts': []})
    return jsonify(search(q))


@app.route('/api/vault', methods=['POST'])
def set_vault():
    data = request.get_json()
    path = data.get('path', '').strip()
    if not path:
        return jsonify({'error': 'Path is required'}), 400
    set_meta('vault_path', os.path.abspath(path))
    return jsonify({'path': os.path.abspath(path)})


@app.route('/api/vault', methods=['GET'])
def get_vault():
    path = get_meta('vault_path')
    return jsonify({'path': path})


@app.route('/api/scan', methods=['POST'])
def start_scan():
    global scan_state
    if scan_state['running']:
        return jsonify({'error': 'Scan already in progress'}), 409

    data = request.get_json(silent=True) or {}
    vault_path = data.get('path') or get_meta('vault_path')

    if not vault_path or not os.path.isdir(vault_path):
        return jsonify({'error': f'Invalid vault path: {vault_path}'}), 400

    scan_state = {
        'running': True, 'total': 0, 'scanned': 0,
        'current': '', 'phase': 'scanning', 'error': None
    }

    def run_scan():
        global scan_state
        try:
            # Clear old data
            clear_all()

            # Scan files
            def progress(scanned, total):
                scan_state['scanned'] = scanned
                scan_state['total'] = total

            raw_files = scan_directory(vault_path, progress_cb=progress)

            if not raw_files:
                scan_state.update({'phase': 'done', 'running': False})
                return

            # Extract concepts and store
            scan_state['phase'] = 'extracting'
            file_concepts = {}

            for i, f in enumerate(raw_files):
                scan_state['current'] = f['filename']
                scan_state['scanned'] = i
                scan_state['total'] = len(raw_files)

                fid = insert_file(
                    f['path'], f['filename'], f['extension'],
                    f['directory'], f['size'], f['modified'], f['content']
                )
                concepts = extract_concepts(f['filename'], f['content'])
                concept_entries = []
                for name, weight in concepts:
                    cid = upsert_concept(name)
                    link_file_concept(fid, cid, weight)
                    concept_entries.append((name, weight))
                file_concepts[fid] = concept_entries

            # Build graph
            scan_state['phase'] = 'building'
            scan_state['current'] = 'Computing relationships...'
            edges = build_graph(file_concepts)

            for src, tgt, weight, shared in edges:
                insert_edge(src, tgt, round(weight, 4), shared)

            set_meta('vault_path', vault_path)
            scan_state.update({
                'phase': 'done', 'running': False,
                'scanned': len(raw_files), 'current': ''
            })

        except Exception as e:
            scan_state.update({
                'phase': 'error', 'running': False,
                'error': str(e), 'current': ''
            })

    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    return jsonify({'status': 'started'})


@app.route('/api/scan/status')
def scan_status():
    return jsonify(scan_state)


@app.route('/api/demo', methods=['POST'])
def load_demo():
    """Load demo data to showcase the tool without a real vault."""
    global scan_state
    if scan_state['running']:
        return jsonify({'error': 'Scan already in progress'}), 409

    scan_state = {'running': True, 'total': 1, 'scanned': 0,
                  'current': '', 'phase': 'extracting', 'error': None}

    def run_demo():
        global scan_state
        try:
            clear_all()
            demo_files = generate_demo_data()
            file_concepts = {}

            for i, (path, filename, ext, directory, content) in enumerate(demo_files):
                scan_state['current'] = filename
                scan_state['scanned'] = i
                scan_state['total'] = len(demo_files)
                fid = insert_file(path, filename, ext, directory,
                                  len(content), '2025-01-15T10:00:00', content)
                concepts = extract_concepts(filename, content)
                entries = []
                for name, weight in concepts:
                    cid = upsert_concept(name)
                    link_file_concept(fid, cid, weight)
                    entries.append((name, weight))
                file_concepts[fid] = entries

            scan_state['phase'] = 'building'
            scan_state['current'] = 'Computing relationships...'
            edges = build_graph(file_concepts)
            for src, tgt, weight, shared in edges:
                insert_edge(src, tgt, round(weight, 4), shared)

            scan_state.update({'phase': 'done', 'running': False,
                               'scanned': len(demo_files), 'current': ''})
        except Exception as e:
            scan_state.update({'phase': 'error', 'running': False, 'error': str(e)})

    thread = threading.Thread(target=run_demo, daemon=True)
    thread.start()
    return jsonify({'status': 'started'})


def generate_demo_data():
    """Generate realistic CS curriculum demo files."""
    vault = "/demo-vault"
    files = []

    # --- NOTES ---
    notes = [
        ("notes/sliding_window.md", "sliding_window.md", ".md", "notes",
         """# Sliding Window Technique
The **sliding window** is a technique for reducing the time complexity of problems
involving subarrays or substrings. Instead of recalculating for every position,
we slide a window across the data.

## Fixed Size Window
Maintain a window of size `k`. Slide it one step at a time, adding the new element
and removing the oldest. Used for `maximum sum subarray` of fixed size.

## Variable Size Window
Expand the window until a condition is violated, then shrink from the left.
Used for `longest substring without repeating characters` and `minimum window substring`.

## Two Pointers Connection
The sliding window is essentially a specialized **two pointers** technique where
both pointers move in the same direction. It's closely related to the `two pointer`
approach used in sorted array problems.

## Common Patterns
- `maximum subarray` sum with constraint
- `longest substring` with unique characters
- `minimum window` containing all characters
- `permutation in string` check
- `frequency count` based problems

## Time Complexity
O(n) instead of O(n²) brute force. The window visits each element at most twice.
"""),

        ("notes/binary_search.md", "binary_search.md", ".md", "notes",
         """# Binary Search
**Binary search** finds an element in a **sorted array** in O(log n) time
by repeatedly dividing the search interval in half.

## Algorithm
1. Set `left = 0`, `right = n - 1`
2. Compute `mid = left + (right - left) / 2`
3. If `arr[mid] == target`, return mid
4. If `arr[mid] < target`, search right half
5. If `arr[mid] > target`, search left half

## Variants
- `lower_bound`: first element >= target
- `upper_bound`: first element > target
- `binary search on answer`: when the answer is monotonic

## Applications
- Finding insertion point in sorted array
- `rotated sorted array` search
- `peak element` finding
- `square root` using binary search
- `minimum in rotated sorted array`

## Related Techniques
Binary search pairs well with `dynamic programming` for optimization problems
and with `two pointers` in sorted contexts.
"""),

        ("notes/dynamic_programming.md", "dynamic_programming.md", ".md", "notes",
         """# Dynamic Programming
**Dynamic programming** solves problems by breaking them into overlapping subproblems
and storing results to avoid recomputation.

## Key Properties
- **Optimal substructure**: optimal solution contains optimal sub-solutions
- **Overlapping subproblems**: same subproblems recur

## Approaches
### Top-Down (Memoization)
Recursive with caching. Start from the main problem, memoize subproblem results.

### Bottom-Up (Tabulation)
Iterative, fill table from base cases up. Usually more space-efficient.

## Classic Problems
- `fibonacci` sequence (classic DP intro)
- `knapsack` problem (0/1 and fractional)
- `longest common subsequence` (LCS)
- `longest increasing subsequence` (LIS)
- `edit distance` between strings
- `coin change` problem
- `matrix chain multiplication`

## State Design
The hardest part is defining the state. Common patterns:
- Single dimension: `dp[i]` for prefix problems
- Two dimensions: `dp[i][j]` for two-sequence problems
- Bitmask: `dp[mask]` for subset problems
"""),

        ("notes/graph_algorithms.md", "graph_algorithms.md", ".md", "notes",
         """# Graph Algorithms
Graph algorithms operate on **graphs** consisting of **nodes** (vertices) and **edges**.

## Representation
- `adjacency list`: array of lists, space O(V+E)
- `adjacency matrix`: 2D array, space O(V²)

## Traversal
### BFS (Breadth-First Search)
Uses a `queue`. Explores all neighbors before going deeper. Finds `shortest path`
in unweighted graphs. Time: O(V+E).

### DFS (Depth-First Search)
Uses a `stack` (or recursion). Goes as deep as possible before backtracking.
Used for `topological sort`, `cycle detection`, `connected components`.

## Shortest Path
- `dijkstra`: single source, non-negative weights, O((V+E) log V)
- `bellman ford`: handles negative weights, O(VE)
- `floyd warshall`: all pairs shortest path, O(V³)

## Minimum Spanning Tree
- `kruskal`: sort edges, use `union find`, O(E log E)
- `prims`: grow MST from a node, O((V+E) log V)

## Applications
- `social network` analysis
- `routing` and navigation
- `dependency resolution`
- `web crawling`
"""),

        ("notes/trees_bst.md", "trees_bst.md", ".md", "notes",
         """# Trees and Binary Search Trees
A **tree** is a hierarchical data structure with a root and child nodes.
A **binary search tree** (BST) maintains the property: left < root < right.

## BST Operations
- `search`: O(log n) average, O(n) worst
- `insert`: find position, insert as leaf
- `delete`: handle 0, 1, or 2 children cases
- `traversal`: inorder (sorted), preorder, postorder, level order

## Balanced BST Variants
- `AVL tree`: strict height balance, rotations
- `Red Black tree`: relaxed balance, fewer rotations
- Both guarantee O(log n) operations

## Tree Traversal Applications
- `inorder traversal` gives sorted order in BST
- `level order traversal` uses BFS with a queue
- `preorder` useful for serialization
- `postorder` useful for directory size calculation

## Related Structures
- `Heap`: complete binary tree for priority queue
- `Trie`: tree for string/prefix operations
- `Segment tree`: range queries
"""),

        ("notes/linked_lists.md", "linked_lists.md", ".md", "notes",
         """# Linked Lists
A **linked list** stores elements in nodes where each node points to the next.
Unlike arrays, insertion/deletion is O(1) but access is O(n).

## Types
- `singly linked list`: each node has next pointer
- `doubly linked list`: each node has next and prev pointers
- `circular linked list`: last node points to head

## Common Operations
- `reverse` a linked list (iterative and recursive)
- `detect cycle` using Floyd's algorithm (fast/slow pointers)
- `merge two sorted` linked lists
- `find middle` using fast/slow pointers
- `remove nth from end`

## Key Patterns
- **Dummy head**: simplifies edge cases for insertion/deletion at head
- **Fast/slow pointers**: cycle detection, middle finding
- The `two pointers` technique is heavily used in linked list problems

## Comparison with Arrays
- Linked list: O(1) insert/delete at known position, O(n) access
- Array: O(1) access, O(n) insert/delete
"""),

        ("notes/sorting.md", "sorting.md", ".md", "notes",
         """# Sorting Algorithms
Sorting arranges elements in a defined order. Understanding sorting is fundamental
to competitive programming.

## Comparison-Based Sorts
| Algorithm | Best | Average | Worst | Space | Stable |
|-----------|------|---------|-------|-------|--------|
| `merge sort` | O(n log n) | O(n log n) | O(n log n) | O(n) | Yes |
| `quick sort` | O(n log n) | O(n log n) | O(n²) | O(log n) | No |
| `heap sort` | O(n log n) | O(n log n) | O(n log n) | O(1) | No |

## Non-Comparison Sorts
- `counting sort`: O(n+k) when range k is small
- `radix sort`: O(d*(n+b)) for d digits
- `bucket sort`: average O(n+k)

## Key Concepts
- `merge sort` uses divide and conquer, similar to `dynamic programming`
- `quick sort` partitioning is related to `two pointers`
- `heap sort` uses the `heap` data structure
- Stability matters when sorting by multiple keys

## When to Use What
- General purpose: `merge sort` (stable) or `quick sort` (fast in practice)
- Nearly sorted: `insertion sort`
- Small range: `counting sort`
- External sorting: `merge sort` variant
"""),

        ("notes/two_pointers.md", "two_pointers.md", ".md", "notes",
         """# Two Pointers Technique
The **two pointers** technique uses two indices to traverse a data structure,
often reducing O(n²) to O(n).

## Types
### Same Direction
Both pointers move in the same direction. Examples:
- `sliding window` (specialized same-direction)
- `fast slow pointers` for cycle detection
- `remove duplicates` from sorted array

### Opposite Direction
One from start, one from end. Examples:
- `two sum` in sorted array
- `container with most water`
- `palindrome` checking
- `three sum` problem (with nested pointer)

## When to Use
- Sorted array problems
- Subarray/substring problems
- Pair finding in sorted data
- `linked list` problems (fast/slow)

## Connection to Other Techniques
- `sliding window` is a variant of same-direction two pointers
- `binary search` can be seen as a degenerate two-pointer
- `merge sort` merge step uses two pointers
"""),

        ("notes/hash_maps.md", "hash_maps.md", ".md", "notes",
         """# Hash Maps and Hashing
A **hash map** (dictionary) provides O(1) average-case lookup, insert, and delete
by mapping keys to array indices via a hash function.

## Implementation
- `hash function`: converts key to array index
- `collision resolution`: chaining (linked lists) or open addressing
- `load factor`: triggers resizing when elements/capacity exceeds threshold

## Common Patterns
- `frequency count`: count occurrences of elements
- `group by`: group items by a key
- `lookup table`: store precomputed results
- `two sum` using hash map instead of sorting

## Time Complexity
- Average: O(1) for all operations
- Worst: O(n) when all keys collide

## Applications
- `anagram` checking
- `duplicate detection`
- `caching` and memoization in `dynamic programming`
- `union find` sometimes uses hash maps
- `subarray sum` equals k problem
"""),

        ("notes/recursion.md", "recursion.md", ".md", "notes",
         """# Recursion and Backtracking
**Recursion** is when a function calls itself to solve smaller subproblems.
**Backtracking** is recursion with undoing choices.

## Recursion Essentials
- **Base case**: stops recursion
- **Recursive case**: breaks problem into smaller subproblems
- Call stack depth limits (usually ~1000 in Python)

## Classic Recursion Problems
- `fibonacci` (naive vs memoized)
- `factorial`
- `tower of hanoi`
- `permutations` and `combinations`
- `subset` generation

## Backtracking
Systematically try choices and undo them:
- `N-Queens` problem
- `sudoku` solver
- `maze` solving
- `subset sum` problem
- `word search` in grid

## Recursion to Iteration
- Use explicit `stack` instead of call stack
- `DFS` can be recursive or iterative
- `dynamic programming` converts recursive memoization to iterative tabulation
"""),
    ]

    for path, fn, ext, d, content in notes:
        files.append((f"{vault}/{path}", fn, ext, d, content))

    # --- CODE FILES ---
    code = [
        ("code/sliding_window.py", "sliding_window.py", ".py", "code",
         '''def max_subarray_sum(arr, k):
    """Fixed size sliding window - maximum sum of subarray of size k."""
    if len(arr) < k:
        return 0
    window_sum = sum(arr[:k])
    max_sum = window_sum
    for i in range(k, len(arr)):
        window_sum += arr[i] - arr[i - k]
        max_sum = max(max_sum, window_sum)
    return max_sum

def longest_substring_without_repeating(s):
    """Variable size sliding window - longest substring with unique chars."""
    char_index = {}
    left = 0
    max_len = 0
    for right, ch in enumerate(s):
        if ch in char_index and char_index[ch] >= left:
            left = char_index[ch] + 1
        char_index[ch] = right
        max_len = max(max_len, right - left + 1)
    return max_len

def min_window_substring(s, t):
    """Minimum window containing all characters of t."""
    from collections import Counter
    need = Counter(t)
    have = {}
    left = 0
    formed = 0
    required = len(need)
    min_len = float('inf')
    min_window = ""
    for right, ch in enumerate(s):
        have[ch] = have.get(ch, 0) + 1
        if ch in need and have[ch] == need[ch]:
            formed += 1
        while formed == required and left <= right:
            if right - left + 1 < min_len:
                min_len = right - left + 1
                min_window = s[left:right + 1]
            have[s[left]] -= 1
            if s[left] in need and have[s[left]] < need[s[left]]:
                formed -= 1
            left += 1
    return min_window
'''),

        ("code/binary_search.c", "binary_search.c", ".c", "code",
         '''#include <stdio.h>

int binary_search(int arr[], int n, int target) {
    int left = 0, right = n - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}

int lower_bound(int arr[], int n, int target) {
    int left = 0, right = n;
    while (left < right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] < target) left = mid + 1;
        else right = mid;
    }
    return left;
}

int search_rotated(int arr[], int n, int target) {
    int left = 0, right = n - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[left] <= arr[mid]) {
            if (arr[left] <= target && target < arr[mid]) right = mid - 1;
            else left = mid + 1;
        } else {
            if (arr[mid] < target && target <= arr[right]) left = mid + 1;
            else right = mid - 1;
        }
    }
    return -1;
}

int sqrt_binary(int x) {
    if (x < 2) return x;
    int left = 1, right = x / 2;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        long sq = (long)mid * mid;
        if (sq == x) return mid;
        if (sq < x) left = mid + 1;
        else right = mid - 1;
    }
    return right;
}
'''),

        ("code/dp_fibonacci.py", "dp_fibonacci.py", ".py", "code",
         '''def fib_memo(n, memo=None):
    """Top-down DP with memoization for Fibonacci."""
    if memo is None:
        memo = {}
    if n in memo:
        return memo[n]
    if n <= 1:
        return n
    memo[n] = fib_memo(n - 1, memo) + fib_memo(n - 2, memo)
    return memo[n]

def fib_tabular(n):
    """Bottom-up DP tabulation for Fibonacci."""
    if n <= 1:
        return n
    dp = [0] * (n + 1)
    dp[1] = 1
    for i in range(2, n + 1):
        dp[i] = dp[i - 1] + dp[i - 2]
    return dp[n]

def fib_optimized(n):
    """Space-optimized Fibonacci - only keep last two values."""
    if n <= 1:
        return n
    prev2, prev1 = 0, 1
    for _ in range(2, n + 1):
        curr = prev1 + prev2
        prev2, prev1 = prev1, curr
    return prev1

def climb_stairs(n):
    """Climbing stairs - same pattern as Fibonacci."""
    if n <= 2:
        return n
    prev2, prev1 = 1, 2
    for _ in range(3, n + 1):
        curr = prev1 + prev2
        prev2, prev1 = prev1, curr
    return prev1
'''),

        ("code/dp_knapsack.py", "dp_knapsack.py", ".py", "code",
         '''def knapsack_01(weights, values, capacity):
    """0/1 Knapsack using 2D DP tabulation."""
    n = len(weights)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for w in range(capacity + 1):
            if weights[i - 1] <= w:
                dp[i][w] = max(dp[i - 1][w],
                                values[i - 1] + dp[i - 1][w - weights[i - 1]])
            else:
                dp[i][w] = dp[i - 1][w]
    return dp[n][capacity]

def knapsack_01_space_optimized(weights, values, capacity):
    """0/1 Knapsack with 1D DP array."""
    n = len(weights)
    dp = [0] * (capacity + 1)
    for i in range(n):
        for w in range(capacity, weights[i] - 1, -1):
            dp[w] = max(dp[w], values[i] + dp[w - weights[i]])
    return dp[capacity]

def coin_change(coins, amount):
    """Minimum coins to make amount - unbounded knapsack variant."""
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    for coin in coins:
        for a in range(coin, amount + 1):
            dp[a] = min(dp[a], dp[a - coin] + 1)
    return dp[amount] if dp[amount] != float('inf') else -1

def longest_increasing_subsequence(nums):
    """LIS using patience sorting approach - O(n log n)."""
    import bisect
    tails = []
    for num in nums:
        idx = bisect.bisect_left(tails, num)
        if idx == len(tails):
            tails.append(num)
        else:
            tails[idx] = num
    return len(tails)
'''),

        ("code/graph_bfs.py", "graph_bfs.py", ".py", "code",
         '''from collections import deque

def bfs(graph, start):
    """Standard BFS traversal returning visited order."""
    visited = set()
    queue = deque([start])
    visited.add(start)
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return order

def shortest_path_bfs(graph, start, end):
    """Shortest path in unweighted graph using BFS."""
    visited = {start}
    queue = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        if node == end:
            return path
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None

def bfs_levels(graph, start):
    """BFS returning nodes grouped by level."""
    visited = {start}
    queue = deque([start])
    levels = []
    while queue:
        level_size = len(queue)
        level = []
        for _ in range(level_size):
            node = queue.popleft()
            level.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        levels.append(level)
    return levels

def connected_components(graph):
    """Find all connected components using BFS."""
    visited = set()
    components = []
    for node in graph:
        if node not in visited:
            component = bfs(graph, node)
            components.append(component)
            visited.update(component)
    return components
'''),

        ("code/graph_dfs.py", "graph_dfs.py", ".py", "code",
         '''def dfs_recursive(graph, node, visited=None):
    """Recursive DFS traversal."""
    if visited is None:
        visited = set()
    visited.add(node)
    order = [node]
    for neighbor in graph.get(node, []):
        if neighbor not in visited:
            order.extend(dfs_recursive(graph, neighbor, visited))
    return order

def dfs_iterative(graph, start):
    """Iterative DFS using explicit stack."""
    visited = set()
    stack = [start]
    order = []
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for neighbor in reversed(graph.get(node, [])):
            if neighbor not in visited:
                stack.append(neighbor)
    return order

def topological_sort(graph):
    """Topological sort using DFS - for DAGs."""
    visited = set()
    result = []
    def dfs(node):
        visited.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
        result.append(node)
    for node in graph:
        if node not in visited:
            dfs(node)
    return result[::-1]

def has_cycle_dfs(graph):
    """Cycle detection using DFS with recursion stack."""
    visited = set()
    rec_stack = set()
    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False
    for node in graph:
        if node not in visited:
            if dfs(node):
                return True
    return False
'''),

        ("code/bst_operations.c", "bst_operations.c", ".c", "code",
         '''#include <stdio.h>
#include <stdlib.h>

struct TreeNode {
    int val;
    struct TreeNode *left;
    struct TreeNode *right;
};

struct TreeNode* create_node(int val) {
    struct TreeNode* node = (struct TreeNode*)malloc(sizeof(struct TreeNode));
    node->val = val;
    node->left = node->right = NULL;
    return node;
}

struct TreeNode* insert_bst(struct TreeNode* root, int val) {
    if (root == NULL) return create_node(val);
    if (val < root->val) root->left = insert_bst(root->left, val);
    else if (val > root->val) root->right = insert_bst(root->right, val);
    return root;
}

struct TreeNode* search_bst(struct TreeNode* root, int val) {
    if (root == NULL || root->val == val) return root;
    if (val < root->val) return search_bst(root->left, val);
    return search_bst(root->right, val);
}

void inorder_traversal(struct TreeNode* root) {
    if (root == NULL) return;
    inorder_traversal(root->left);
    printf("%d ", root->val);
    inorder_traversal(root->right);
}

int min_value(struct TreeNode* root) {
    while (root->left != NULL) root = root->left;
    return root->val;
}

struct TreeNode* delete_bst(struct TreeNode* root, int val) {
    if (root == NULL) return root;
    if (val < root->val) root->left = delete_bst(root->left, val);
    else if (val > root->val) root->right = delete_bst(root->right, val);
    else {
        if (root->left == NULL) { struct TreeNode* t = root->right; free(root); return t; }
        if (root->right == NULL) { struct TreeNode* t = root->left; free(root); return t; }
        root->val = min_value(root->right);
        root->right = delete_bst(root->right, root->val);
    }
    return root;
}

int max_depth(struct TreeNode* root) {
    if (root == NULL) return 0;
    int left_depth = max_depth(root->left);
    int right_depth = max_depth(root->right);
    return (left_depth > right_depth ? left_depth : right_depth) + 1;
}
'''),

        ("code/linked_list.py", "linked_list.py", ".py", "code",
         '''class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def reverse_linked_list(head):
    """Iterative reversal of a singly linked list."""
    prev, curr = None, head
    while curr:
        next_node = curr.next
        curr.next = prev
        prev, curr = curr, next_node
    return prev

def has_cycle(head):
    """Floyd cycle detection - fast and slow pointers."""
    slow = fast = head
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
        if slow == fast:
            return True
    return False

def find_middle(head):
    """Find middle node using fast/slow pointers."""
    slow = fast = head
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
    return slow

def merge_two_sorted(l1, l2):
    """Merge two sorted linked lists."""
    dummy = ListNode()
    curr = dummy
    while l1 and l2:
        if l1.val <= l2.val:
            curr.next, l1 = l1, l1.next
        else:
            curr.next, l2 = l2, l2.next
        curr = curr.next
    curr.next = l1 or l2
    return dummy.next

def remove_nth_from_end(head, n):
    """Remove nth node from end using two pointers."""
    dummy = ListNode(0, head)
    fast = slow = dummy
    for _ in range(n + 1):
        fast = fast.next
    while fast:
        slow, fast = slow.next, fast.next
    slow.next = slow.next.next
    return dummy.next

def detect_cycle_start(head):
    """Find start node of cycle."""
    slow = fast = head
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
        if slow == fast:
            slow = head
            while slow != fast:
                slow, fast = slow.next, fast.next
            return slow
    return None
'''),

        ("code/sorting_merge.py", "sorting_merge.py", ".py", "code",
         '''def merge_sort(arr):
    """Merge sort - divide and conquer, stable, O(n log n)."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    """Merge two sorted arrays - uses two pointers technique."""
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result

def merge_sort_inplace(arr, left=0, right=None):
    """In-place merge sort to show the two pointers pattern."""
    if right is None:
        right = len(arr) - 1
    if left < right:
        mid = (left + right) // 2
        merge_sort_inplace(arr, left, mid)
        merge_sort_inplace(arr, mid + 1, right)
        merge_inplace(arr, left, mid, right)

def merge_inplace(arr, left, mid, right):
    temp = arr[left:right + 1]
    i, j, k = 0, mid - left + 1, left
    while i <= mid - left and j <= right - left:
        if temp[i] <= temp[j]:
            arr[k] = temp[i]
            i += 1
        else:
            arr[k] = temp[j]
            j += 1
        k += 1
    while i <= mid - left:
        arr[k] = temp[i]
        i += 1
        k += 1
'''),

        ("code/sorting_quick.py", "sorting_quick.py", ".py", "code",
         '''import random

def quick_sort(arr):
    """Quick sort with random pivot selection."""
    if len(arr) <= 1:
        return arr
    pivot = arr[random.randint(0, len(arr) - 1)]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quick_sort(left) + middle + quick_sort(right)

def quick_sort_inplace(arr, low=0, high=None):
    """In-place quick sort using two pointers partition."""
    if high is None:
        high = len(arr) - 1
    if low < high:
        pi = partition(arr, low, high)
        quick_sort_inplace(arr, low, pi - 1)
        quick_sort_inplace(arr, pi + 1, high)

def partition(arr, low, high):
    """Lomuto partition - two pointers from same end."""
    pivot = arr[high]
    i = low - 1
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1

def hoare_partition(arr, low, high):
    """Hoare partition - two pointers from opposite ends."""
    pivot = arr[(low + high) // 2]
    i, j = low - 1, high + 1
    while True:
        i += 1
        while arr[i] < pivot:
            i += 1
        j -= 1
        while arr[j] > pivot:
            j -= 1
        if i >= j:
            return j
        arr[i], arr[j] = arr[j], arr[i]

def kth_smallest(arr, k):
    """Quick select - find kth smallest using partition."""
    return quick_select(arr, 0, len(arr) - 1, k)

def quick_select(arr, low, high, k):
    if low == high:
        return arr[low]
    pi = partition(arr, low, high)
    if k == pi:
        return arr[k]
    elif k < pi:
        return quick_select(arr, low, pi - 1, k)
    else:
        return quick_select(arr, pi + 1, high, k)
'''),

        ("code/two_pointers.py", "two_pointers.py", ".py", "code",
         '''def two_sum_sorted(arr, target):
    """Two sum in sorted array using opposite direction pointers."""
    left, right = 0, len(arr) - 1
    while left < right:
        current = arr[left] + arr[right]
        if current == target:
            return [left, right]
        elif current < target:
            left += 1
        else:
            right -= 1
    return None

def three_sum(arr):
    """Three sum using nested two pointers - O(n²)."""
    arr.sort()
    result = []
    for i in range(len(arr) - 2):
        if i > 0 and arr[i] == arr[i - 1]:
            continue
        left, right = i + 1, len(arr) - 1
        while left < right:
            total = arr[i] + arr[left] + arr[right]
            if total == 0:
                result.append([arr[i], arr[left], arr[right]])
                while left < right and arr[left] == arr[left + 1]:
                    left += 1
                while left < right and arr[right] == arr[right - 1]:
                    right -= 1
                left += 1
                right -= 1
            elif total < 0:
                left += 1
            else:
                right -= 1
    return result

def container_with_most_water(height):
    """Max area using opposite direction two pointers."""
    left, right = 0, len(height) - 1
    max_area = 0
    while left < right:
        area = min(height[left], height[right]) * (right - left)
        max_area = max(max_area, area)
        if height[left] < height[right]:
            left += 1
        else:
            right -= 1
    return max_area

def is_palindrome(s):
    """Check palindrome using two pointers from ends."""
    left, right = 0, len(s) - 1
    while left < right:
        if s[left] != s[right]:
            return False
        left += 1
        right -= 1
    return True

def remove_duplicates_sorted(arr):
    """Remove duplicates in sorted array - same direction pointers."""
    if not arr:
        return 0
    write = 1
    for read in range(1, len(arr)):
        if arr[read] != arr[write - 1]:
            arr[write] = arr[read]
            write += 1
    return write
'''),

        ("code/hash_map_impl.py", "hash_map_impl.py", ".py", "code",
         '''class HashMap:
    """Simple hash map implementation with chaining."""
    def __init__(self, capacity=16):
        self.capacity = capacity
        self.size = 0
        self.buckets = [[] for _ in range(capacity)]

    def _hash(self, key):
        return hash(key) % self.capacity

    def put(self, key, value):
        idx = self._hash(key)
        bucket = self.buckets[idx]
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        bucket.append((key, value))
        self.size += 1
        if self.size > self.capacity * 0.75:
            self._resize()

    def get(self, key, default=None):
        idx = self._hash(key)
        for k, v in self.buckets[idx]:
            if k == key:
                return v
        return default

    def _resize(self):
        old_buckets = self.buckets
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.size = 0
        for bucket in old_buckets:
            for key, value in bucket:
                self.put(key, value)

def two_sum_hash(nums, target):
    """Two sum using hash map - O(n) time."""
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return None

def subarray_sum_equals_k(nums, k):
    """Count subarrays with sum k using prefix sum hash map."""
    from collections import defaultdict
    count = defaultdict(int)
    count[0] = 1
    prefix_sum = 0
    result = 0
    for num in nums:
        prefix_sum += num
        result += count.get(prefix_sum - k, 0)
        count[prefix_sum] += 1
    return result

def group_anagrams(strs):
    """Group anagrams using sorted string as hash map key."""
    groups = {}
    for s in strs:
        key = tuple(sorted(s))
        if key not in groups:
            groups[key] = []
        groups[key].append(s)
    return list(groups.values())
'''),

        ("code/union_find.py", "union_find.py", ".py", "code",
         '''class UnionFind:
    """Disjoint Set Union with path compression and union by rank."""
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.count = n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        self.count -= 1
        return True

    def connected(self, x, y):
        return self.find(x) == self.find(y)

def kruskal_mst(n, edges):
    """Kruskal minimum spanning tree using union find."""
    edges.sort(key=lambda e: e[2])
    uf = UnionFind(n)
    mst = []
    total_weight = 0
    for u, v, w in edges:
        if uf.union(u, v):
            mst.append((u, v, w))
            total_weight += w
            if len(mst) == n - 1:
                break
    return mst, total_weight

def count_connected_components(n, edges):
    """Count connected components in undirected graph."""
    uf = UnionFind(n)
    for u, v in edges:
        uf.union(u, v)
    return uf.count
'''),
    ]

    for path, fn, ext, d, content in code:
        files.append((f"{vault}/{path}", fn, ext, d, content))

    return files


if __name__ == '__main__':
    init_db()
    print("Lokus-Synapse server starting...")
    print("Open http://localhost:5000 in your browser")
    app.run(host='0.0.0.0', port=5000, debug=False)
