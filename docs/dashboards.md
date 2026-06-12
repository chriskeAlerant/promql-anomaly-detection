# Dashboards

Import the JSON dashboards from `dashboards/` or let the local Docker Compose Grafana provisioning load them automatically.

Use the `Anomaly Calculator` datasource. It must point at Thanos Query:

```text
http://thanos-query:10902
```

`anomaly-overview.json` shows the source metric, `anomaly:level`, `anomaly:upper_band`, and `anomaly:lower_band`. Filter by `anomaly_strategy`, `anomaly_name`, `service`, and `environment`.

`anomaly-calculator-prometheus-health.json` shows rule evaluation cost, query engine load, TSDB cardinality, remote write ingest, resource usage, and per-replica health for `anomaly-prometheus-a` and `anomaly-prometheus-b`.

The main operational panel is:

```promql
prometheus_rule_group_last_duration_seconds / prometheus_rule_group_interval_seconds
```

Keep it below `0.5` during normal operation.
