# Remote write

Forward only allowlisted, pre-aggregated metrics from the source Prometheus to the anomaly Prometheus pair.

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

Selected metrics must include anomaly labels before they arrive at the anomaly Prometheus pair:

```yaml
- record: service:http_request_rate5m
  expr: sum by (service, environment) (rate(http_requests_total[5m]))
  labels:
    anomaly_name: http_requests
    anomaly_type: requests
    anomaly_strategy: adaptive
```

Recommended labels are `service` and `environment`. Avoid forwarding raw series with `pod`, `instance`, `route`, `method`, `status_code`, or histogram `le` combinations unless they are intentionally bounded.

Do not remote write the entire metric set. Do not send `anomaly:*` series back into the anomaly Prometheus pair or the source Prometheus. If a future topology adds result write-back, add explicit loop protection first.
