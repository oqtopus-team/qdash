# Database Index Recommendations

This document outlines recommended database indexes for optimal query performance in QDash.

## MongoDB - ExecutionHistoryDocument

### Required Indexes for Metrics API

The metrics API with best/latest selection mode requires efficient queries on the `ExecutionHistory` collection.

#### 1. Compound Index: chip_id + username + start_at

```python
db.execution_history.create_index([
    ("chip_id", 1),
    ("username", 1),
    ("start_at", -1)  # Descending for recent-first sorting
])
```

**Usage**: Used by `_extract_best_metrics()` for querying execution history

**Query Pattern**:
```python
ExecutionHistoryDocument.find({
    "chip_id": chip_id,
    "username": username,
    "start_at": {"$gte": cutoff_time}
}).sort([("start_at", -1)]).limit(1000)
```

**Benefits**:
- Efficient filtering by chip and user
- Fast sorting by timestamp (descending)
- Supports time range queries with `$gte`

#### 2. Index: chip_id + username

```python
db.execution_history.create_index([
    ("chip_id", 1),
    ("username", 1)
])
```

**Usage**: Fallback for queries without time filter

**Query Pattern**:
```python
ExecutionHistoryDocument.find({
    "chip_id": chip_id,
    "username": username
}).sort([("start_at", -1)]).limit(1000)
```

### Performance Impact

Without indexes:
- Collection scan: O(n) where n = total executions
- 1000+ executions: ~500ms+ query time

With compound index:
- Index scan: O(log n + k) where k = matched documents
- 1000+ executions: ~10-50ms query time

### Implementation

Add to your MongoDB initialization script or run manually:

```javascript
// MongoDB shell
use qdash;

db.execution_history.createIndex(
  { chip_id: 1, username: 1, start_at: -1 },
  { name: "metrics_best_query_idx" }
);

db.execution_history.createIndex(
  { chip_id: 1, username: 1 },
  { name: "metrics_chip_user_idx" }
);
```

### Verification

Check if indexes exist:

```javascript
db.execution_history.getIndexes();
```

Analyze query performance:

```javascript
db.execution_history.find({
  chip_id: "test_chip",
  username: "admin",
  start_at: { $gte: ISODate("2025-01-01T00:00:00Z") }
}).sort({ start_at: -1 }).limit(1000).explain("executionStats");
```

Look for:
- `executionStats.executionTimeMillis` < 50ms
- `winningPlan.inputStage.stage` == "IXSCAN"
- `executionStats.totalDocsExamined` ≈ `executionStats.nReturned`

## PostgreSQL - Prefect Metadata (Future)

_To be documented when Prefect integration requires optimization_

## Monitoring

### Query Performance Alerts

Set up monitoring for:
- Query execution time > 100ms
- Collection scans (COLLSCAN) on large collections
- Index usage ratio < 95%

### Tools

- MongoDB Atlas: Built-in Performance Advisor
- Grafana: Custom dashboards with MongoDB exporter
- Application logs: Track slow queries via FastAPI middleware

## Maintenance

### Index Rebuilding

Schedule periodic index rebuilds during low-traffic periods:

```javascript
db.execution_history.reIndex();
```

Frequency: Monthly or when index fragmentation > 30%

### Index Statistics

Monitor index usage:

```javascript
db.execution_history.aggregate([
  { $indexStats: {} }
]);
```

Remove unused indexes to reduce write overhead.
