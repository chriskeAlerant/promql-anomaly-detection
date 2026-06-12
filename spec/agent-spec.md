# Specification: Dedicated Prometheus-Based Anomaly Calculator Fork

## 1. Goal

Create a fork of `grafana/promql-anomaly-detection` that keeps the original PromQL-based anomaly detection behavior, but moves the calculations away from the primary monitoring Prometheus into a dedicated HA Prometheus pair.

The dedicated Prometheus instances receive the preselected source metrics required for anomaly calculations through remote write. Both Prometheus replicas evaluate the same recording rules. A Thanos Querier sits in front of them and deduplicates the results produced by the two Prometheus replicas.

An alerting layer is not required in this version. Alerting rules may remain as examples or archived references, but they must not be enabled in the default deployment.

## 2. Source Repository

Source repository:

```text
https://github.com/grafana/promql-anomaly-detection
```

The original repository is based on Prometheus recording rules. The framework produces anomaly bands through base recording rules, and alerting rules can report when an observed time series falls outside the calculated band. The goal of this fork is to keep the original recording rule logic while packaging it for dedicated calculation infrastructure.

## 3. Target Architecture

Target state:

```text
Primary Prometheus / source Prometheus
  +-- remote_write, only for allowlisted metrics
        +-- Anomaly Prometheus A
        |     +-- remote write receiver enabled
        |     +-- anomaly recording rules
        |     +-- local TSDB
        |
        +-- Anomaly Prometheus B
              +-- remote write receiver enabled
              +-- anomaly recording rules
              +-- local TSDB

Anomaly Prometheus A/B
  +-- Thanos Sidecar or Prometheus-compatible StoreAPI integration
        +-- Thanos Querier
              +-- Grafana datasource
```

Grafana should query the Thanos Querier by default, not the anomaly Prometheus instances directly. The Thanos Querier deduplicates identical time series produced by the two Prometheus replicas.

Thanos deduplication requires a stable replica label. The two anomaly Prometheus instances must have a shared cluster or role label and a distinct replica label in their external labels. Example:

```yaml
global:
  external_labels:
    cluster: anomaly-calculator
    replica: anomaly-prometheus-a
```

and:

```yaml
global:
  external_labels:
    cluster: anomaly-calculator
    replica: anomaly-prometheus-b
```

The Thanos Querier should start with a deduplication setting such as:

```text
--query.replica-label=replica
```

## 4. Important Design Decisions

### 4.1. The Dedicated Prometheus Pair Is Both Storage and Compute

In this version, the anomaly Prometheus pair:

* receives source metrics as a remote write receiver,
* stores the time series required for calculations locally,
* runs the anomaly recording rules,
* stores the generated `anomaly:*` time series,
* serves results to Grafana through Thanos Query.

### 4.2. No Write-Back to the Primary Prometheus

This implementation does not need to write `anomaly:*` results back to the original/source Prometheus.

Rationale:

* isolation stays cleaner,
* primary TSDB cardinality growth is avoided,
* remote write loop risk is avoided,
* ownership remains clear: anomaly results belong to the anomaly calculator layer.

### 4.3. No Alerting Layer

The original repository's alerting rules do not need to be actively used. This fork focuses on:

* recording rules,
* dedicated Prometheus HA topology,
* Thanos deduplicated queries,
* Grafana visualization,
* Prometheus load monitoring dashboard.

No Alertmanager configuration is required.

## 5. Repository Restructuring Tasks

### 5.1. Directory Structure

The fork should separate the original rules, deployment configuration, Grafana dashboards, and documentation.

Suggested structure:

```text
.
+-- README.md
+-- docs/
|   +-- architecture.md
|   +-- remote-write.md
|   +-- operations.md
|   +-- dashboards.md
+-- rules/
|   +-- adaptive.yml
|   +-- robust.yml
|   +-- examples/
|   +-- extra/
+-- deploy/
|   +-- docker-compose/
|       +-- docker-compose.yml
|       +-- prometheus-anomaly-a.yml
|       +-- prometheus-anomaly-b.yml
|       +-- thanos-query.yml
|       +-- grafana-dashboard-provider.yml
|       +-- source-prometheus-example.yml
+-- dashboards/
|   +-- anomaly-overview.json
|   +-- anomaly-calculator-prometheus-health.json
+-- examples/
    +-- remote-write-source-prometheus.yml
    +-- metric-selection.yml
    +-- grafana-datasource-thanos.yml
```

Exact file names may vary, but the repository must be clearly usable so that someone can start the dedicated anomaly calculator topology locally with Docker Compose by following the README.

### 5.2. Rule File Handling

The original recording rule logic in `rules/adaptive.yml` and `rules/robust.yml` must be preserved.

The goal is not to change the anomaly algorithm, but to run the rules on dedicated Prometheus instances.

Requirements:

1. The recording rules must continue to produce the output time series required by the original behavior, for example:

```text
anomaly:level
anomaly:upper_band
anomaly:lower_band
```

2. The rules must run only on metrics that the source Prometheus sends through remote write.

3. Alerting rules must not be loaded into the default Prometheus configuration.

4. The documentation must explain how to include a new metric in anomaly calculations.

5. The documentation must explain that high-cardinality label sets should be avoided. Prefer pre-aggregated SLI metrics, for example:

```text
service:http_request_rate5m{service, environment}
service:http_error_rate5m{service, environment}
service:http_latency_p95{service, environment}
```

Raw high-cardinality time series are not recommended, for example combinations of pod, route, status_code, instance, and le bucket labels.

### 5.3. Prometheus Configuration

Create two anomaly Prometheus configurations:

```text
prometheus-anomaly-a.yml
prometheus-anomaly-b.yml
```

Both configurations must:

* enable remote write receiver behavior through the required startup flag,
* load the anomaly recording rule files,
* not load alerting rule files by default,
* include different `replica` external labels,
* include a shared `cluster` or `role` external label,
* use a retention setting that supports rules using a 1 week offset.

The current Docker Compose implementation loads these demo/example recording rule files in addition to the base `rules/adaptive.yml` and `rules/robust.yml` files:

```text
rules/examples/node_exporter.yml
rules/examples/otel_demo.yml
rules/extra/demo.yml
```

These are part of the default compose configuration for the local demo and example metric selection. Alerting rule files must still not be loaded by default.

Recommended minimum retention:

```text
15d
```

Rationale: adaptive/robust rules may use long-term and seasonal calculations with 1 day and 1 week offsets, so overly short retention can produce incorrect or incomplete bands.

Example:

```yaml
global:
  scrape_interval: 30s
  evaluation_interval: 1m
  external_labels:
    cluster: anomaly-calculator
    replica: anomaly-prometheus-a

rule_files:
  - /etc/prometheus/rules/adaptive.yml
  - /etc/prometheus/rules/robust.yml
```

The Prometheus startup command must include:

```text
--web.enable-remote-write-receiver
--storage.tsdb.retention.time=15d
```

### 5.4. Source Prometheus Remote Write Example

Create an example configuration showing how the source Prometheus sends metrics to the anomaly Prometheus pair.

The remote write configuration must include two target URLs:

```yaml
remote_write:
  - url: http://anomaly-prometheus-a:9090/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "service:http_request_rate5m|service:http_error_rate5m|service:http_latency_p95"
        action: keep

  - url: http://anomaly-prometheus-b:9090/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "service:http_request_rate5m|service:http_error_rate5m|service:http_latency_p95"
        action: keep
```

The documentation must explicitly call out that:

* only allowlisted metrics should be forwarded,
* copying the full metric set through remote write should be avoided,
* sending `anomaly:*` metrics back into the anomaly Prometheus instances should be avoided,
* if any write-back topology is added later, loop protection is required.

### 5.5. Thanos Querier Integration

Create a minimal Thanos Query configuration.

The Thanos Querier must:

* connect to both anomaly Prometheus instances through Thanos Sidecar or StoreAPI,
* use replica-label-based deduplication,
* provide a single query endpoint for Grafana.

Example startup parameters:

```text
thanos query \
  --http-address=0.0.0.0:10902 \
  --query.replica-label=replica \
  --endpoint=anomaly-prometheus-a-sidecar:10901 \
  --endpoint=anomaly-prometheus-b-sidecar:10901
```

The specification requires the Grafana datasource to point to the Thanos Querier HTTP endpoint, not directly to Prometheus A/B.

### 5.6. Grafana Datasource Example

Create an example Grafana datasource provisioning file:

```yaml
apiVersion: 1

datasources:
  - name: Anomaly Calculator
    type: prometheus
    access: proxy
    url: http://thanos-query:10902
    isDefault: false
```

## 6. Dashboard Requirements

Two dashboards must be created or adapted.

### 6.1. Anomaly Overview Dashboard

This dashboard should show the anomaly bands and the measured values.

Required panels:

1. `anomaly:level`
2. `anomaly:upper_band`
3. `anomaly:lower_band`
4. original source metric, if queryable from the same anomaly datasource
5. filtering by strategy, for example adaptive/robust
6. variables for `anomaly_name`, `service`, `environment`, or other relevant labels

The goal of this dashboard is to make it visible whether the anomaly bands follow the input time series correctly.

### 6.2. Anomaly Calculator Prometheus Health Dashboard

Create a separate Grafana dashboard that shows the load and health of the anomaly Prometheus pair.

This is a required deliverable.

Required panels:

#### Rule Evaluation

```promql
prometheus_rule_group_last_duration_seconds
```

```promql
prometheus_rule_group_interval_seconds
```

```promql
prometheus_rule_group_last_duration_seconds
/
prometheus_rule_group_interval_seconds
```

```promql
increase(prometheus_rule_evaluation_failures_total[5m])
```

Goal: make it visible whether rule groups fit within the evaluation interval.

#### Query Engine Load

```promql
rate(prometheus_engine_query_duration_seconds_count[5m])
```

```promql
histogram_quantile(
  0.95,
  rate(prometheus_engine_query_duration_seconds_bucket[5m])
)
```

#### TSDB Cardinality and Ingest

```promql
prometheus_tsdb_head_series
```

```promql
rate(prometheus_tsdb_head_samples_appended_total[5m])
```

#### Remote Write Receiver / Ingest State

If available in the Prometheus version in use:

```promql
rate(prometheus_http_requests_total{handler="/api/v1/write"}[5m])
```

```promql
rate(prometheus_http_response_size_bytes_sum{handler="/api/v1/write"}[5m])
```

or version-specific receiver metrics if they are available.

#### Resource Usage

```promql
rate(process_cpu_seconds_total[5m])
```

```promql
process_resident_memory_bytes
```

```promql
go_memstats_heap_alloc_bytes
```

#### HA Replica State

Panels are also required that show these replicas separately:

* anomaly-prometheus-a,
* anomaly-prometheus-b.

Goal: make it easy to see if one replica is running with different load or errors.

#### Suggested Visualization Thresholds

The dashboard should visually highlight:

```text
prometheus_rule_group_last_duration_seconds / prometheus_rule_group_interval_seconds > 0.5
```

This is a warning state.

```text
prometheus_rule_group_last_duration_seconds / prometheus_rule_group_interval_seconds >= 1
```

This is a critical state because rule evaluation no longer fits into the scheduled cycle.

No alerting needs to be implemented now; only dashboard-level visibility is required.

## 7. README Requirements

The root `README.md` must fully describe the fork's purpose and usage.

Required README sections:

### 7.1. Project Goal

Describe that this fork adapts the Grafana PromQL anomaly detection framework to a dedicated Prometheus HA topology.

Clarify that:

* anomaly bands are still calculated by PromQL recording rules,
* calculation is moved to a dedicated Prometheus pair,
* Grafana queries the results through Thanos Query,
* no alerting layer is enabled by default.

### 7.2. Architecture

Include an ASCII architecture diagram:

```text
Source Prometheus
  +-- remote_write selected metrics
        +-- Anomaly Prometheus A
        +-- Anomaly Prometheus B
              |
              +-- Thanos Querier with replica deduplication
                    +-- Grafana
```

Explain each component:

* source Prometheus,
* remote write allowlist,
* anomaly Prometheus A/B,
* recording rules,
* Thanos Querier,
* Grafana datasource.

### 7.3. Remote Write Configuration

Include a complete `remote_write` example with two target Prometheus instances.

Include a `write_relabel_configs` allowlist example.

Include warnings:

* do not forward the full metric set,
* do not forward raw high-cardinality metrics,
* do not send `anomaly:*` metrics between source and anomaly Prometheus instances without loop protection.

### 7.4. Metric Selection Recommendation

The README should describe recommended metrics:

* request rate,
* error rate,
* latency p95/p99,
* CPU usage,
* memory usage,
* queue length,
* business SLIs.

Recommended granularity:

```text
service + environment
```

Granularity to avoid:

```text
pod + instance + route + method + status_code + le
```

### 7.5. Local Deployment

Include a `docker-compose` example:

* source Prometheus,
* anomaly Prometheus A,
* anomaly Prometheus B,
* Thanos Sidecar A/B if needed,
* Thanos Querier,
* Grafana.

After `docker-compose up`, these endpoints should be available:

```text
Grafana: http://localhost:3000
Thanos Query: http://localhost:10902
Anomaly Prometheus A: http://localhost:9091
Anomaly Prometheus B: http://localhost:9092
```

Ports may be changed, but they must be documented.

### 7.6. Grafana Dashboards

The README must describe:

* how to import the anomaly overview dashboard,
* how to import the anomaly calculator Prometheus health dashboard,
* which datasource to select,
* which basic metrics to monitor.

### 7.7. Operations Checklist

Include this checklist:

```text
[ ] The source Prometheus sends only allowlisted metrics.
[ ] Both anomaly Prometheus replicas receive remote write samples.
[ ] Both anomaly Prometheus replicas load the same rule files.
[ ] The two Prometheus external labels differ only by the replica label.
[ ] Thanos Querier deduplication is enabled.
[ ] The Grafana datasource points to the Thanos Query endpoint.
[ ] The rule duration / interval ratio stays below 0.5 on the anomaly health dashboard.
[ ] TSDB head series growth is controlled.
[ ] The anomaly:upper_band and anomaly:lower_band time series are visible.
```

## 8. Operations Documentation

Create `docs/operations.md`.

It must include:

### 8.1. Capacity Monitoring

The documentation must describe that the following should be monitored regularly:

```promql
prometheus_rule_group_last_duration_seconds
/
prometheus_rule_group_interval_seconds
```

```promql
prometheus_tsdb_head_series
```

```promql
rate(prometheus_tsdb_head_samples_appended_total[5m])
```

```promql
rate(process_cpu_seconds_total[5m])
```

```promql
process_resident_memory_bytes
```

### 8.2. Scaling Recommendation

If rule evaluation becomes too slow:

1. reduce the number of input series sent through remote write,
2. further aggregate source metrics,
3. increase long-term rule group evaluation intervals where appropriate,
4. split adaptive and robust strategies onto separate Prometheus pairs if needed,
5. increase CPU and memory for the anomaly Prometheus pair.

### 8.3. Retention

Document that anomaly Prometheus retention must not be too short.

Recommended default:

```text
15d
```

Rationale: enough historical data is required for long-term calculations using a 1 week offset.

## 9. Testing and Validation Requirements

The Codex agent should create or update checks that validate:

1. YAML files are syntactically valid.
2. Prometheus rule files can be validated with `promtool check rules`.
3. Prometheus configurations can be validated with `promtool check config`.
4. The docker-compose configuration can be started.
5. The Thanos Querier datasource is reachable as a working HTTP endpoint.
6. The Grafana datasource provisioning file is valid YAML.
7. Dashboard JSON files are valid JSON documents.
8. Alerting rule files are not loaded in the default anomaly Prometheus configuration.

The current validation script checks the repository deployment YAML files, examples, rule files, and dashboard JSON files.

Suggested CI steps:

```bash
promtool check rules rules/adaptive.yml
promtool check rules rules/robust.yml
promtool check config deploy/docker-compose/prometheus-anomaly-a.yml
promtool check config deploy/docker-compose/prometheus-anomaly-b.yml
python -m json.tool dashboards/anomaly-overview.json
python -m json.tool dashboards/anomaly-calculator-prometheus-health.json
```

## 10. Acceptance Criteria

The task is complete when:

1. The fork preserves the original anomaly recording rule behavior.
2. The dedicated anomaly Prometheus A/B configuration is complete.
3. Both anomaly Prometheus instances can be configured as remote write receivers.
4. The default configuration does not load alerting rules.
5. The Thanos Querier configuration with replica deduplication is complete.
6. At least one Grafana datasource example pointing to the Thanos Query endpoint is complete.
7. The anomaly overview dashboard is complete.
8. The anomaly calculator Prometheus health dashboard is complete.
9. The root README is complete with architecture, remote write example, and operations guidance.
10. At least one local docker-compose-based runtime example is complete.
11. YAML and JSON files can be validated.
12. Prometheus rule and config files can be validated with `promtool`.
13. The documentation clearly explains that only allowlisted, preferably pre-aggregated metrics should be forwarded.
14. The documentation clearly explains that results do not need to be written back to the source Prometheus.
15. The documentation clearly explains that Grafana should query the Thanos Querier.

## 11. Non-Goals

The following are not part of this implementation:

* Alertmanager integration.
* Enabling alerting rules in production by default.
* Rewriting the anomaly algorithm.
* Introducing an external ML component.
* Writing anomaly results back to the primary/source Prometheus.
* Copying the full metric set through remote write.
* Long-term object-storage-based Thanos retention, unless required as a separate deployment option.

## 12. Implementation Notes for the Codex Agent

Changes must be made in a way that does not break the original repository's PromQL-based anomaly detection logic.

Where possible, add example configurations instead of destructively rewriting the original rules.

Documentation should be practical and include copyable configuration examples.

The README should be sufficient on its own for a new user to understand:

1. why there is a dedicated Prometheus pair,
2. how source metrics enter the system,
3. where anomaly calculation happens,
4. how HA deduplication works,
5. how Grafana should query the results,
6. how to verify that the anomaly calculator Prometheus pair is not overloaded.
