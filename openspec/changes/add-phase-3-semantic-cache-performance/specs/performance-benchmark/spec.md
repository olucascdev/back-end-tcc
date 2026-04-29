## ADDED Requirements

### Requirement: Performance baseline measurement
The system SHALL establish a performance baseline for the chat endpoint before cache activation. The baseline MUST include p50, p95, and p99 latency metrics and throughput (requests per second) measured under controlled load.

#### Scenario: Baseline executed without cache
- **WHEN** the baseline benchmark script is run with semantic cache disabled
- **THEN** the script records p50, p95, p99 latency and throughput and writes results to `docs/phase-3-baseline.md`

### Requirement: Cache performance benchmark
The system SHALL provide a benchmark script that compares chat endpoint performance with and without semantic cache under multiple scenarios of query repetition. The benchmark MUST validate that cache reduces p95 latency by at least 40% for repeated queries.

#### Scenario: Benchmark with 50% repeated queries
- **WHEN** the benchmark is run with a workload of 50% unique and 50% repeated queries
- **THEN** the results show p95 latency reduction of at least 40% compared to baseline and hit ratio is recorded

#### Scenario: Benchmark with 80% repeated queries
- **WHEN** the benchmark is run with a workload of 20% unique and 80% repeated queries
- **THEN** the results show maximum cache benefit with hit ratio approaching 80% and p95 latency significantly below baseline

#### Scenario: Benchmark results documented
- **WHEN** all benchmark scenarios complete
- **THEN** results are written to `docs/phase-3-benchmark-results.md` with comparative latency tables, hit ratios, and cost-benefit analysis

### Requirement: Performance gate enforcement
The system SHALL enforce a performance gate that requires cache to reduce p95 latency by at least 40% for repeated queries before the feature is considered production-ready.

#### Scenario: Gate validation passes
- **WHEN** benchmark results show p95 with cache is less than 60% of p95 without cache for repeated queries
- **THEN** the performance gate passes and the feature is eligible for production rollout

#### Scenario: Gate validation fails
- **WHEN** benchmark results do not meet the 40% p95 reduction threshold
- **THEN** the feature is blocked from production rollout and root cause analysis is required
