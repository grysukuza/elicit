# Performance, Latency & Throughput Checklist

Goals:
1. Minimize end-to-end latency (p50/p95/p99).
2. Maximize throughput without degradation.
3. Keep tail latency bounded under load.
4. Degrade gracefully under spikes.
5. Make bottlenecks observable and fixable.

Reference baselines:
- Google SRE (latency SLOs, error budgets)
- Tail latency: “The Tail at Scale” (Dean & Barroso)
- Use Little’s Law: L = λ * W (queue length = arrival rate * latency)

---

## 1. Define SLOs & Budgets (do this first)

- [ ] Define endpoints and targets:
  - [ ] p50 latency target (e.g., < 100 ms)
  - [ ] p95 latency target (e.g., < 300 ms)
  - [ ] p99 latency target (e.g., < 800 ms)
- [ ] Define throughput targets (RPS – requests per second).
- [ ] Define error budget (e.g., 99.9% success).
- [ ] Set alert thresholds tied to SLOs.

---

## 2. Instrumentation & Measurement

- [ ] Add request timing middleware (start/stop timers).
- [ ] Capture p50/p95/p99 latency.
- [ ] Add per-endpoint metrics.
- [ ] Track DB query time separately.
- [ ] Track external API latency.
- [ ] Add distributed tracing (trace IDs).
- [ ] Log queue wait time vs execution time.
- [ ] Separate cold-start vs warm performance.

---

## 3. Architecture (critical path reduction)

- [ ] Identify critical path per request.
- [ ] Remove unnecessary sequential steps.
- [ ] Parallelize independent operations.
- [ ] Move non-critical work to background jobs.
- [ ] Use async I/O where appropriate.
- [ ] Avoid blocking calls on main thread.
- [ ] Break monolith endpoints into smaller services if needed.

---

## 4. Caching (highest ROI lever)

- [ ] Add in-memory cache (e.g., Redis) for hot data.
- [ ] Cache DB query results.
- [ ] Cache computed responses (HTML/JSON).
- [ ] Use cache keys with versioning.
- [ ] Set TTLs (time-to-live).
- [ ] Implement cache invalidation strategy.
- [ ] Use CDN for static assets.
- [ ] Enable browser caching headers.

Key idea:
- 1 cache hit replaces DB + compute → often 10–100x faster.

---

## 5. Database Optimization

- [ ] Add indexes on frequently queried columns.
- [ ] Avoid full table scans.
- [ ] Use EXPLAIN to analyze queries.
- [ ] Limit returned rows (pagination).
- [ ] Select only needed columns.
- [ ] Avoid N+1 query patterns.
- [ ] Use connection pooling.
- [ ] Separate read vs write DB (if scale demands).
- [ ] Use batching for writes.

Sensitivity:
- Missing index can increase latency 10–100x.

---

## 6. API & Backend Efficiency

- [ ] Use efficient serialization (JSON minimal fields).
- [ ] Compress responses (gzip/brotli).
- [ ] Avoid large payloads.
- [ ] Implement pagination and filtering.
- [ ] Use streaming for large responses.
- [ ] Precompute expensive values.
- [ ] Use idempotency for retries.
- [ ] Avoid synchronous external calls in hot path.

---

## 7. Frontend Performance

- [ ] Minimize bundle size (tree-shaking).
- [ ] Lazy load components.
- [ ] Use CDN for assets.
- [ ] Optimize images (compression, WebP/AVIF).
- [ ] Reduce render-blocking scripts.
- [ ] Use HTTP/2 or HTTP/3.
- [ ] Preload critical resources.
- [ ] Use client-side caching.

---

## 8. Concurrency & Throughput

- [ ] Use async frameworks (FastAPI, Node async).
- [ ] Tune worker count (CPU cores vs I/O bound).
- [ ] Use connection pooling for DB and HTTP.
- [ ] Avoid thread blocking.
- [ ] Use queues for background work.
- [ ] Apply backpressure when overloaded.

Little’s Law:
- If λ (arrival rate) increases without reducing W (latency), queue grows → collapse.

---

## 9. Background Jobs & Queues

- [ ] Move emails, analytics, billing to background jobs.
- [ ] Use job queue (Redis, RabbitMQ, etc.).
- [ ] Retry failed jobs safely.
- [ ] Make jobs idempotent.
- [ ] Monitor queue depth.
- [ ] Scale workers independently.

---

## 10. External Dependencies

- [ ] Set timeouts for all external calls.
- [ ] Use retries with exponential backoff.
- [ ] Add circuit breakers.
- [ ] Cache external responses where possible.
- [ ] Fallback gracefully if dependency fails.
- [ ] Track latency per dependency.

---

## 11. Load Management

- [ ] Rate limit abusive or heavy clients.
- [ ] Apply quotas per user/API key.
- [ ] Use load shedding under stress.
- [ ] Prioritize critical endpoints.
- [ ] Queue overflow protection.
- [ ] Graceful degradation (return partial results).

---

## 12. Scaling Strategy

- [ ] Vertical scaling (increase CPU/RAM).
- [ ] Horizontal scaling (multiple instances).
- [ ] Stateless app design (required for horizontal scale).
- [ ] Use load balancer.
- [ ] Auto-scaling triggers (CPU, latency, queue depth).
- [ ] Separate services for heavy workloads.

---

## 13. Tail Latency Reduction (p99 focus)

- [ ] Eliminate long-tail slow queries.
- [ ] Add timeouts to every operation.
- [ ] Use hedged requests (duplicate slow calls).
- [ ] Reduce variance in execution paths.
- [ ] Warm caches on startup.
- [ ] Avoid cold starts where possible.

Key insight:
- Users feel p95–p99, not average latency.

---

## 14. Memory & Resource Management

- [ ] Monitor memory usage.
- [ ] Avoid memory leaks.
- [ ] Use streaming instead of loading large objects.
- [ ] Tune garbage collection (if applicable).
- [ ] Limit concurrency to prevent thrashing.

---

## 15. Deployment Optimization

- [ ] Use production server (not dev server).
- [ ] Enable keep-alive connections.
- [ ] Use HTTP compression.
- [ ] Reduce cold start time.
- [ ] Preload app on startup.
- [ ] Use health checks.

---

## 16. Observability & Alerts

- [ ] Dashboard for latency percentiles.
- [ ] Dashboard for throughput (RPS).
- [ ] Alert on p95/p99 breaches.
- [ ] Alert on error rate spikes.
- [ ] Alert on queue depth growth.
- [ ] Correlate errors with latency spikes.

---

## 17. Testing & Benchmarking

- [ ] Load testing (k6, Locust).
- [ ] Stress testing (beyond capacity).
- [ ] Soak testing (long duration).
- [ ] Benchmark critical endpoints.
- [ ] Compare before/after optimizations.

Example tools:
```bash id="load_testing_tools"
k6 run script.js
locust
ab -n 1000 -c 50 http://localhost:8000/