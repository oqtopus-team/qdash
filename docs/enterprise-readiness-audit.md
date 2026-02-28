# QDash Enterprise Readiness Audit Report

**Date**: 2026-02-28
**Scope**: Security, Testing & Quality, Observability & Operations, Architecture & Data Layer

---

## Executive Summary

QDash has a solid foundation with well-structured code, good dependency injection patterns, comprehensive structured logging, and strong multi-tenancy support. However, several critical gaps must be addressed to reach enterprise-level readiness. The most impactful areas are **security hardening**, **observability**, **API maturity**, and **operational resilience**.

Below is a prioritized breakdown organized by severity.

---

## 1. Security

### 1.1 CRITICAL Issues

| Issue | Location | Description |
|-------|----------|-------------|
| Overly permissive CORS | `src/qdash/api/main.py:71-79` | `origins=["*"]` with `allow_credentials=True` allows any website to make authenticated requests. Must restrict to specific frontend origins. |
| Weak bcrypt rounds | `src/qdash/api/lib/auth.py:16-23` | `bcrypt__rounds=10` is below recommended minimum of 12. Should be 12-15 for production. |
| GitHub token in URLs | `src/qdash/api/services/file_service.py:335,434` | Tokens embedded in repository URLs risk exposure in logs and error messages. Use SSH keys or credential helpers instead. |
| Default credentials | `.env.example:19-20,28-29` | Default admin password `passw0rd` and MongoDB password `example` with no enforcement to change them. |
| No password strength validation | `src/qdash/api/db/session.py:110-169` | Admin user auto-created from env vars without password complexity checks. |

### 1.2 HIGH Issues

| Issue | Location | Description |
|-------|----------|-------------|
| No security headers | `src/qdash/api/main.py` | Missing HSTS, X-Content-Type-Options, X-Frame-Options, CSP headers. |
| No rate limiting | `src/qdash/api/main.py` | No rate limiting on any endpoint including authentication. Brute-force attacks possible. |
| Docker privileged mode | `compose.yaml:133` | API container runs with `privileged: true`. Should be removed or replaced with specific capabilities. |
| Plaintext tokens in DB | `src/qdash/api/lib/auth.py:86-103` | Access tokens stored unhashed in MongoDB. Should be hashed. |
| Unauthenticated routes | `src/qdash/api/main.py:92-95` | `execution` and `file` routers included without global auth dependency. |
| No token expiration | `src/qdash/api/services/auth_service.py:101` | Bearer tokens have no TTL or rotation mechanism. Compromised tokens remain valid indefinitely. |

### 1.3 MEDIUM Issues

| Issue | Location | Description |
|-------|----------|-------------|
| Error messages leak internals | Multiple routers | `detail=f"File not found: {path}"` exposes filesystem paths. Use generic error messages. |
| No security event logging | — | Failed login attempts, authorization failures not logged for audit. |

### 1.4 Positive Findings

- Pydantic models provide solid input validation
- Path traversal protection implemented with URL decoding
- `yaml.safe_load()` used consistently (no unsafe deserialization)
- Proper `secrets.token_urlsafe(32)` for token generation
- Bunnet ODM provides injection protection
- Request ID middleware for audit trail

---

## 2. Testing & Code Quality

### 2.1 Current State

| Category | Status | Details |
|----------|--------|---------|
| Python unit tests | 41 test files | Comprehensive coverage of API routers, services, database models |
| Frontend tests | 8 test files | URL state hooks, utilities |
| Test framework | pytest + Vitest | In-memory MongoDB via mongomock |
| Type checking | Strict | mypy (Python) + TypeScript strict mode |
| Linting | Comprehensive | Ruff with 40+ rules incl. security (bandit), ESLint for UI |
| CI/CD | Multi-stage | GitHub Actions: lint → typecheck → test (Python 3.10/3.11/3.12 matrix) |
| Coverage tracking | Codecov | Uploaded on CI for Python 3.10 |

### 2.2 Gaps

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| No pre-commit hooks | Code quality issues reach CI | Add `.pre-commit-config.yaml` with ruff, mypy, prettier |
| Low frontend test count | 8 vs 41 Python tests | Expand component and hook testing |
| No E2E tests | User-facing flows untested | Add Playwright or Cypress |
| No Python dead code detection | Unused code accumulates | Add vulture or similar tool |
| No static analysis platform | Limited code quality metrics | Consider SonarQube or CodeClimate |
| ESLint max warnings = 15 | Technical debt accepted | Reduce to 0 over time |

### 2.3 Coverage Targets (from pyproject.toml)

| Component | Target |
|-----------|--------|
| API Routers | 80% |
| Database Models | 90% |
| Workflow Helpers | 75% |
| Utility Functions | 90% |

---

## 3. Observability & Operations

### 3.1 Logging (Excellent)

- Structured JSON logging across all services via `pythonjsonlogger`
- YAML-based configuration with env var substitution
- Rotating file handlers (10MB, 5 backups)
- Request ID correlation via `X-Request-ID` header and ContextVar
- No `print()` statements in core code
- Suppressed noisy libraries (uvicorn, pymongo at WARNING)

### 3.2 Critical Gaps

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| No APM | Cannot track latency, throughput, error rates | Add Prometheus client + Grafana |
| No error tracking | Errors only in log files, no aggregation | Add Sentry SDK |
| No distributed tracing | Cannot trace requests across API → Workflow → DB | Add OpenTelemetry |
| No API health endpoint | No way to check API health | Add `GET /health` with DB connectivity check |
| No MongoDB healthcheck | Silent database failures in Docker | Add healthcheck to compose.yaml |
| No readiness/liveness probes | Premature traffic, dead services not restarted | Add Kubernetes-ready probes |
| No backup strategy | Data loss risk | Document and automate MongoDB backups |

### 3.3 Deployment Quality

**Strengths:**
- Multi-stage Docker builds (minimal runtime images)
- FastAPI lifespan management with proper startup/shutdown
- Docker Compose with dependency ordering
- YAML-based config management

**Weaknesses:**
- `privileged: true` on API container
- gunicorn with `--reload` flag (dev setting in production)
- No load balancer defined
- Single MongoDB instance (no replica set)
- No Kubernetes manifests

### 3.4 Graceful Shutdown

- FastAPI lifespan properly closes DB connections
- No explicit SIGTERM handlers for workflow workers
- Subprocess-based worker management lacks signal forwarding

---

## 4. Architecture & API Design

### 4.1 API Maturity Gaps

| Gap | Location | Description |
|-----|----------|-------------|
| No API versioning | `src/qdash/api/main.py` | All endpoints at single version. Need `/api/v1/` prefix for breaking changes. |
| Inconsistent error responses | Various routers | Mix of `{"detail": "..."}` and custom formats. No error codes or request ID in responses. |
| Incomplete pagination | 8/23 routers | Many list endpoints return full collections without skip/limit. |
| No sorting/filtering params | Most list endpoints | Only specific fields support filtering. No standard query operators. |
| Blocking I/O in async | `src/qdash/api/lib/auth.py:69` | Synchronous `.run()` MongoDB calls in async context blocks event loop. |

### 4.2 Data Layer

**Strengths:**
- Well-designed MongoDB indexes (unique, compound)
- Bunnet ODM with clean Document models
- Repository pattern with protocol-based abstractions
- Comprehensive migration system (dry-run by default)

**Weaknesses:**
- No query projections (fetches all document fields)
- No connection pool size configuration
- No query timeout settings
- No read preference for replicas
- Global DB state could cause threading issues

### 4.3 Caching

| Current | Missing |
|---------|---------|
| `@lru_cache` on service singletons | Redis/Memcached for distributed caching |
| Task name caching from filesystem | HTTP caching headers (Cache-Control, ETag) |
| Config caching | Query result caching |
| | Cache invalidation strategy |

### 4.4 Frontend Architecture

**Strengths:**
- React Context + TanStack Query for state management
- Auto-generated TypeScript API client from OpenAPI
- SSE support for real-time updates
- Strong multi-tenancy (project-scoped data)

**Weaknesses:**
- No error boundaries (only ErrorCard component)
- Limited accessibility (sparse `aria-labels`)
- No WCAG compliance audit
- No keyboard navigation documentation

### 4.5 Multi-tenancy (Excellent)

- Full project-level data isolation
- 138+ references to `project_id` across routers
- Role-based access (viewer, editor, owner)
- `ProjectContext` dependency enforces scoping

---

## 5. Prioritized Roadmap

### Phase 1: Security Critical (Week 1-2)

1. **Fix CORS** — Restrict to specific frontend origin(s)
2. **Increase bcrypt rounds** — Set to 12+ for production
3. **Add security headers middleware** — HSTS, CSP, X-Frame-Options, X-Content-Type-Options
4. **Add rate limiting** — `slowapi` on auth endpoints at minimum
5. **Remove `privileged: true`** from Docker compose
6. **Hash access tokens** in database
7. **Add token expiration** — TTL and rotation mechanism
8. **Sanitize error messages** — Remove file paths and internal details

### Phase 2: Observability (Week 2-4)

1. **Add `GET /health` endpoint** — Check MongoDB + PostgreSQL connectivity
2. **Add MongoDB healthcheck** to compose.yaml
3. **Integrate Prometheus metrics** — Request count, latency histograms, error rates
4. **Add Sentry SDK** — Error tracking and alerting
5. **Add readiness/liveness probes** for all services
6. **Security event logging** — Failed logins, auth failures, suspicious activity

### Phase 3: API Maturity (Week 4-6)

1. **API versioning** — Add `/api/v1/` prefix
2. **Standardize error responses** — Error codes, request ID, timestamp in all error responses
3. **Pagination on all list endpoints** — `skip`, `limit`, `sort_by`, `order`
4. **Fix async blocking I/O** — Use `asyncio.to_thread()` for MongoDB calls in async endpoints
5. **Add query projections** — Fetch only needed fields from MongoDB

### Phase 4: Testing & Quality (Week 6-8)

1. **Add pre-commit hooks** — ruff, mypy, prettier
2. **Expand frontend tests** — Component tests, hook tests
3. **Add E2E test framework** — Playwright for critical user flows
4. **Reduce ESLint max warnings to 0**
5. **Add Python dead code detection** (vulture)

### Phase 5: Production Hardening (Week 8-12)

1. **Implement distributed caching** — Redis for frequently accessed data
2. **Add OpenTelemetry** — Distributed tracing across services
3. **MongoDB replica set** — High availability configuration
4. **Load balancer** — Nginx/HAProxy for horizontal scaling
5. **Kubernetes manifests** — With health probes and resource limits
6. **Database backup automation** — Scheduled MongoDB dumps with point-in-time recovery
7. **Remove gunicorn `--reload`** from production config
8. **Accessibility audit** — WCAG 2.1 compliance

---

## 6. Summary Scorecard

| Area | Current | Enterprise Target | Gap |
|------|---------|-------------------|-----|
| Authentication & Authorization | 6/10 | 9/10 | Token expiration, hashing, rate limiting |
| Input Validation | 8/10 | 9/10 | Field-level validators, error sanitization |
| CORS & Headers | 2/10 | 9/10 | Wildcard origins, missing security headers |
| Logging | 9/10 | 10/10 | Add security event logging |
| Monitoring (APM) | 1/10 | 8/10 | No metrics, no dashboards |
| Error Tracking | 2/10 | 8/10 | No Sentry, no error aggregation |
| Distributed Tracing | 0/10 | 7/10 | No OpenTelemetry |
| Health Checks | 3/10 | 9/10 | Missing API and DB health endpoints |
| Testing | 7/10 | 9/10 | Need E2E, more frontend tests |
| API Design | 6/10 | 9/10 | Versioning, pagination, error consistency |
| Caching | 3/10 | 7/10 | No distributed cache |
| Multi-tenancy | 9/10 | 9/10 | Well-implemented |
| Deployment & Ops | 5/10 | 8/10 | Docker hardening, K8s, backups |
| Accessibility | 3/10 | 7/10 | WCAG audit needed |
| **Overall** | **4.6/10** | **8.4/10** | — |
