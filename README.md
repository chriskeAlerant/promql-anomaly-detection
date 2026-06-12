# PromQL Anomaly Calculator

This fork adapts Grafana's PromQL anomaly detection framework to a dedicated Prometheus HA topology.

The anomaly bands are still calculated by Prometheus recording rules. The difference is operational: the source Prometheus does not spend CPU and TSDB capacity on anomaly calculations. It remote writes only selected, pre-aggregated input metrics to two dedicated anomaly Prometheus replicas. Both replicas run the same recording rules, and Grafana queries the results through Thanos Query with replica deduplication.

Alerting is not enabled by default. Example alerting rules are kept in `rules/alerts/anomaly-alerts-example.yml` for reference only.

## Architecture

```text
Source Prometheus
  └── remote_write selected metrics
        ├── Anomaly Prometheus A
        └── Anomaly Prometheus B
              │
              └── Thanos Querier with replica deduplication
                    └── Grafana
```

Components:

- Source Prometheus: owns normal scraping, source recording rules, and metric selection.
- Remote write allowlist: forwards only selected anomaly inputs.
- Anomaly Prometheus A/B: receive remote write samples, store local TSDB data, and run `rules/adaptive.yml` and `rules/robust.yml`.
- Recording rules: produce `anomaly:level`, `anomaly:upper_band`, and `anomaly:lower_band`.
- Thanos Query: reads both replicas through sidecars and deduplicates by `replica`.
- Grafana datasource: points to Thanos Query, not directly to either Prometheus replica.

The anomaly Prometheus replicas use matching external labels except for `replica`:

```yaml
global:
  external_labels:
    cluster: anomaly-calculator
    replica: anomaly-prometheus-a
```

Thanos Query is started with:

```text
--query.replica-label=replica
```

## Remote Write

Forward only allowlisted metrics to both anomaly Prometheus replicas:

```yaml
remote_write:
  - url: http://anomaly-prometheus-a:9090/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "service:http_request_rate5m|service:http_error_rate5m|service:http_latency_p95"
        action: keep
      - source_labels: [__name__]
        regex: "anomaly:.*"
        action: drop

  - url: http://anomaly-prometheus-b:9090/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "service:http_request_rate5m|service:http_error_rate5m|service:http_latency_p95"
        action: keep
      - source_labels: [__name__]
        regex: "anomaly:.*"
        action: drop
```

Do not remote write the full metric set. Do not send `anomaly:*` results back to the source Prometheus or back into the anomaly Prometheus pair without explicit loop protection.

## Metric Selection

Recommended inputs are pre-aggregated service-level or environment-level series:

- request rate
- error rate
- latency p95/p99
- CPU usage
- memory usage
- queue length
- business SLIs

Recommended granularity:

```text
service + environment
```

Avoid high-cardinality raw dimensions:

```text
pod + instance + route + method + status_code + le
```

Selected metrics must carry `anomaly_name`; `anomaly_type` and `anomaly_strategy` are recommended:

```yaml
- record: service:http_request_rate5m
  expr: sum by (service, environment) (rate(http_requests_total[5m]))
  labels:
    anomaly_name: http_requests
    anomaly_type: requests
    anomaly_strategy: adaptive
```

See `examples/metric-selection.yml`.

## Local Deployment

Run the local HA topology:

```bash
cd deploy/docker-compose
docker compose up
```

Endpoints:

```text
Grafana: http://localhost:3000
Thanos Query: http://localhost:10902
Source Prometheus: http://localhost:9090/prometheus/
Anomaly Prometheus A: http://localhost:9091
Anomaly Prometheus B: http://localhost:9092
```

The compose stack starts:

- source Prometheus with example metric selection and remote write
- anomaly Prometheus A and B with remote write receiver enabled
- Thanos sidecar for each anomaly Prometheus
- Thanos Query with `--query.replica-label=replica`
- Grafana with the source Prometheus datasource, Thanos datasource, anomaly dashboards, and demo dashboards provisioned

The anomaly Prometheus command includes:

```text
--web.enable-remote-write-receiver
--storage.tsdb.retention.time=15d
```

The 15 day retention supports recording rules that use 1 day and 1 week offsets.

To run the original OpenTelemetry demo application stack against the new Prometheus topology:

```bash
cd demo
make start
```

This starts the demo application services from `demo/docker-compose.yml` together with the shared stack in `deploy/docker-compose/docker-compose.yml`. The source Prometheus scrapes the collector at `otelcol:8888`, keeps the OTLP write receiver for the original demo telemetry path, and remote writes the selected demo/anomaly input metrics to both anomaly Prometheus replicas.

Demo endpoints:

```text
Demo UI: http://localhost:8080
Grafana through demo proxy: http://localhost:8080/grafana/
Source Prometheus through demo proxy: http://localhost:8080/prometheus/
Thanos Query: http://localhost:10902
```

## Kubernetes Deployment

Minimal manifests live in `deploy/kubernetes/`:

- `prometheus-anomaly-a.yaml`
- `prometheus-anomaly-b.yaml`
- `thanos-query.yaml`
- `services.yaml`
- `configmaps.yaml`

Create the recording rule ConfigMap from the repo rule files:

```bash
kubectl create namespace anomaly-calculator
kubectl -n anomaly-calculator create configmap anomaly-recording-rules \
  --from-file=adaptive.yml=rules/adaptive.yml \
  --from-file=robust.yml=rules/robust.yml
kubectl -n anomaly-calculator apply -f deploy/kubernetes/configmaps.yaml
kubectl -n anomaly-calculator apply -f deploy/kubernetes/prometheus-anomaly-a.yaml
kubectl -n anomaly-calculator apply -f deploy/kubernetes/prometheus-anomaly-b.yaml
kubectl -n anomaly-calculator apply -f deploy/kubernetes/thanos-query.yaml
kubectl -n anomaly-calculator apply -f deploy/kubernetes/services.yaml
```

Point Grafana at:

```text
http://thanos-query.anomaly-calculator.svc.cluster.local:10902
```

## Grafana

Datasource provisioning example:

```yaml
apiVersion: 1

datasources:
  - name: Anomaly Calculator
    type: prometheus
    access: proxy
    url: http://thanos-query:10902
    isDefault: false
```

Dashboards:

- `dashboards/anomaly-overview.json`
- `dashboards/anomaly-calculator-prometheus-health.json`

Import them into Grafana and select the `Anomaly Calculator` datasource. The local Docker Compose deployment provisions them automatically.

The health dashboard highlights:

```promql
prometheus_rule_group_last_duration_seconds / prometheus_rule_group_interval_seconds
```

Keep this below `0.5` during normal operation. At `1`, rule evaluation no longer fits into its interval.

## Operations Checklist

```text
[ ] A source Prometheus csak allowlistelt metrikákat küld.
[ ] Mindkét anomaly Prometheus fogad remote write mintákat.
[ ] Mindkét anomaly Prometheus azonos rule fájlokat tölt be.
[ ] A két Prometheus external labelje csak replica labelben tér el.
[ ] Thanos Querier deduplikáció be van kapcsolva.
[ ] Grafana datasource a Thanos Query endpointjára mutat.
[ ] Az anomaly health dashboardon a rule duration / interval arány 0.5 alatt van.
[ ] A TSDB head series növekedése kontrollált.
[ ] Az anomaly:upper_band és anomaly:lower_band idősorok megjelennek.
```

## Validation

Recommended checks:

```bash
promtool check rules rules/adaptive.yml
promtool check rules rules/robust.yml
promtool check config deploy/docker-compose/prometheus-anomaly-a.yml
promtool check config deploy/docker-compose/prometheus-anomaly-b.yml
python3 -m json.tool dashboards/anomaly-overview.json
python3 -m json.tool dashboards/anomaly-calculator-prometheus-health.json
```

You can also validate all YAML and JSON files with:

```bash
python3 scripts/validate-configs.py
```

## Documentation

- `docs/architecture.md`
- `docs/remote-write.md`
- `docs/operations.md`
- `docs/dashboards.md`
