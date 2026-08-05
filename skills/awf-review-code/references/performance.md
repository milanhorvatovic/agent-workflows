# Performance catalog

Anti-patterns to check systematically when the change touches hot paths, data access, caching, concurrency, or large data volumes. Findings from this catalog carry category `performance`; grade severity by expected impact under production load, not by how untidy the pattern looks.

## Algorithmic complexity

- Complexity inappropriate for the expected input size; O(n²) or worse in hot paths — nested loops, repeated linear scans, recursion without memoization.
- Hidden quadratic behavior: string concatenation in loops, array resizing in loops, nested filter/map/find chains.
- Algorithms that degrade unacceptably as data grows, even if fine at current scale — say at what scale they break.

## Database queries

- N+1 patterns: a query per loop iteration instead of a batch; ORM lazy-loading triggered inside loops.
- Filtering or sorting on columns without index support; full scans on large tables.
- Unbounded result sets: missing LIMIT or pagination, `SELECT *` on wide tables when a subset is needed.
- Joins on non-indexed columns, unnecessary joins, accidental Cartesian products.
- Round-trips that could be one query; re-fetching data an earlier query already returned.

## Memory

- Whole files, datasets, or result sets loaded into memory where streaming or pagination suffices.
- Leaks: listeners never removed, collections that only grow, closures capturing more than they need.
- Caches without eviction, TTL, or size bounds.
- Unnecessary copying: deep clones where shallow suffices, large buffers duplicated, lazy sequences materialized early.

## I/O

- The same file read or the same call made repeatedly where one read and reuse would do.
- Synchronous/blocking I/O on performance-sensitive or async paths.

## Caching

- Expensive repeated computation or I/O with no cache where one would clearly pay.
- Incorrect invalidation: stale-data risk, inconsistent states, races in cache updates.
- Keys that miss a relevant parameter (collisions) or granularity that defeats the purpose.

## Concurrency

- Blocking calls (file I/O, CPU-heavy work, sleeps) inside async contexts, stalling the event loop or thread pool.
- Missing awaits or dropped results on concurrent operations; unprotected shared state; lock contention.
- Behavior under production load: shared resources becoming contention points, thundering herds, cache stampedes, connection exhaustion; missing backpressure or rate limiting toward external dependencies.

## Resource cleanup

- Connections not returned to pools; file handles, streams, and HTTP connections not closed or drained; temp files left behind; timers never cleared.
