# Database Index Recommendations

This document outlines recommended database indexes for optimal query performance in QDash with multi-tenancy support.

## Overview

All collections use `project_id` as the leading key in their indexes to support multi-tenant data isolation. This ensures efficient queries within project boundaries while maintaining proper data separation.

## MongoDB Collections

### ProjectDocument

```python
db.project.create_index([("project_id", 1)], unique=True)
db.project.create_index([("owner_username", 1), ("name", 1)], unique=True)
```

### ProjectMembershipDocument

```python
db.project_membership.create_index([("project_id", 1), ("username", 1)], unique=True)
db.project_membership.create_index([("username", 1), ("status", 1)])
```

### ChipDocument

```python
db.chip.create_index([("project_id", 1), ("chip_id", 1), ("username", 1)], unique=True)
db.chip.create_index([("project_id", 1), ("username", 1), ("installed_at", -1)])
```

### QubitDocument

```python
db.qubit.create_index([("project_id", 1), ("chip_id", 1), ("qid", 1), ("username", 1)], unique=True)
db.qubit.create_index([("project_id", 1), ("chip_id", 1)])
```

### CouplingDocument

```python
db.coupling.create_index([("project_id", 1), ("chip_id", 1), ("qid", 1), ("username", 1)], unique=True)
db.coupling.create_index([("project_id", 1), ("chip_id", 1)])
```

### ExecutionHistoryDocument

```python
db.execution_history.create_index([("project_id", 1), ("execution_id", 1)], unique=True)
db.execution_history.create_index([("project_id", 1), ("chip_id", 1), ("start_at", -1)])
db.execution_history.create_index([("project_id", 1), ("chip_id", 1)])
db.execution_history.create_index([("project_id", 1), ("username", 1), ("start_at", -1)])
```

**Usage**: Used by `_extract_best_metrics()` for querying execution history within a project

**Query Pattern**:

```python
ExecutionHistoryDocument.find({
    "project_id": project_id,
    "chip_id": chip_id,
    "start_at": {"$gte": cutoff_time}
}).sort([("start_at", -1)]).limit(1000)
```

### TaskDocument

```python
db.task.create_index([("project_id", 1), ("name", 1), ("username", 1)], unique=True)
db.task.create_index([("project_id", 1), ("username", 1)])
```

### BackendDocument

```python
db.backend.create_index([("project_id", 1), ("name", 1), ("username", 1)], unique=True)
db.backend.create_index([("project_id", 1), ("username", 1)])
```

### TagDocument

```python
db.tag.create_index([("project_id", 1), ("name", 1), ("username", 1)], unique=True)
db.tag.create_index([("project_id", 1), ("username", 1)])
```

### FlowDocument

```python
db.flows.create_index([("project_id", 1), ("username", 1), ("name", 1)])
db.flows.create_index([("project_id", 1), ("username", 1), ("created_at", -1)])
db.flows.create_index([("project_id", 1), ("chip_id", 1)])
```

### ExecutionLockDocument

```python
db.execution_lock.create_index([("project_id", 1)], unique=True)
```

### ExecutionCounterDocument

```python
db.execution_counter.create_index([("project_id", 1), ("date", 1), ("username", 1), ("chip_id", 1)], unique=True)
```

### ChipHistoryDocument

```python
db.chip_history.create_index([("project_id", 1), ("chip_id", 1), ("username", 1), ("recorded_date", 1)], unique=True)
db.chip_history.create_index([("project_id", 1), ("chip_id", 1), ("recorded_date", -1)])
```

### QubitHistoryDocument

```python
db.qubit_history.create_index([("project_id", 1), ("chip_id", 1), ("qid", 1), ("username", 1), ("recorded_date", 1)], unique=True)
db.qubit_history.create_index([("project_id", 1), ("chip_id", 1), ("recorded_date", -1)])
```

### CouplingHistoryDocument

```python
db.coupling_history.create_index([("project_id", 1), ("chip_id", 1), ("qid", 1), ("username", 1), ("recorded_date", 1)], unique=True)
db.coupling_history.create_index([("project_id", 1), ("chip_id", 1), ("recorded_date", -1)])
```

### TaskResultHistoryDocument

Primary storage for task execution results. Linked to executions via `execution_id`.

```python
db.task_result_history.create_index([("project_id", 1), ("task_id", 1)], unique=True)
db.task_result_history.create_index([("project_id", 1), ("execution_id", 1)])  # Join with execution_history
db.task_result_history.create_index([("project_id", 1), ("chip_id", 1), ("start_at", -1)])
db.task_result_history.create_index([
    ("project_id", 1), ("chip_id", 1), ("name", 1), ("qid", 1), ("start_at", -1)
])  # Latest task result queries
```

**Usage**: Used by `ExecutionService._fetch_tasks_for_execution()` for retrieving tasks by execution

**Query Pattern**:

```python
TaskResultHistoryDocument.find({
    "project_id": project_id,
    "execution_id": execution_id,
}).sort([("start_at", ASCENDING)])
```

## Performance Impact

Without indexes:

- Collection scan: O(n) where n = total documents
- 1000+ documents: ~500ms+ query time

With compound index (project_id first):

- Index scan: O(log n + k) where k = matched documents
- 1000+ documents: ~10-50ms query time
- Multi-tenant isolation: Queries automatically scoped to project

## Implementation

Add to your MongoDB initialization script or run manually:

```javascript
// MongoDB shell
use qdash;

// Project indexes
db.project.createIndex({ project_id: 1 }, { unique: true, name: "project_id_unique" });
db.project.createIndex({ owner_username: 1, name: 1 }, { unique: true, name: "owner_name_unique" });

// Membership indexes
db.project_membership.createIndex({ project_id: 1, username: 1 }, { unique: true, name: "membership_unique" });
db.project_membership.createIndex({ username: 1, status: 1 }, { name: "user_status_idx" });

// Execution history indexes
db.execution_history.createIndex(
  { project_id: 1, chip_id: 1, start_at: -1 },
  { name: "metrics_best_query_idx" }
);

db.execution_history.createIndex(
  { project_id: 1, chip_id: 1 },
  { name: "metrics_chip_idx" }
);

db.execution_history.createIndex(
  { project_id: 1, username: 1, start_at: -1 },
  { name: "metrics_project_user_idx" }
);
```

## Verification

Check if indexes exist:

```javascript
db.execution_history.getIndexes();
```

Analyze query performance:

```javascript
db.execution_history
  .find({
    project_id: "proj_123",
    chip_id: "test_chip",
    start_at: { $gte: ISODate("2025-01-01T00:00:00Z") },
  })
  .sort({ start_at: -1 })
  .limit(1000)
  .explain("executionStats");
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
db.execution_history.aggregate([{ $indexStats: {} }]);
```

Remove unused indexes to reduce write overhead.
