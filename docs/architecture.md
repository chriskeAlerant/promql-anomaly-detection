# Architecture

This fork packages the PromQL anomaly detection framework as a dedicated calculator tier.

```text
Source Prometheus
  └── remote_write selected, pre-aggregated metrics
        ├── Anomaly Prometheus A
        │     ├── remote write receiver
        │     ├── recording rules
        │     └── Thanos Sidecar
        └── Anomaly Prometheus B
              ├── remote write receiver
              ├── recording rules
              └── Thanos Sidecar
                    │
                    └── Thanos Query --query.replica-label=replica
                          └── Grafana datasource
```

The source Prometheus owns normal monitoring and metric selection. It remote writes only the metrics selected for anomaly calculations.

The anomaly Prometheus pair stores those selected inputs locally and evaluates the recording rules from `rules/adaptive.yml` and `rules/robust.yml`. Both replicas run the same rule files.

Each anomaly Prometheus has the same `cluster` external label and a different `replica` external label:

```yaml
global:
  external_labels:
    cluster: anomaly-calculator
    replica: anomaly-prometheus-a
```

Thanos Query reads both replicas through sidecars and deduplicates by the `replica` label. Grafana should use Thanos Query, not either Prometheus replica directly.

Alerting is intentionally not part of the default deployment. Example alerting rules live in `rules/alerts/anomaly-alerts-example.yml`.
