# Kubernetes deployment

These manifests run the anomaly calculator as a dedicated HA Prometheus pair plus Thanos Query.

Create the namespace and ConfigMaps first:

```bash
kubectl create namespace anomaly-calculator
kubectl -n anomaly-calculator create configmap anomaly-recording-rules \
  --from-file=adaptive.yml=../../rules/adaptive.yml \
  --from-file=robust.yml=../../rules/robust.yml
kubectl -n anomaly-calculator apply -f configmaps.yaml
```

Then deploy the workloads and services:

```bash
kubectl -n anomaly-calculator apply -f prometheus-anomaly-a.yaml
kubectl -n anomaly-calculator apply -f prometheus-anomaly-b.yaml
kubectl -n anomaly-calculator apply -f thanos-query.yaml
kubectl -n anomaly-calculator apply -f services.yaml
```

The `anomaly-recording-rules` ConfigMap intentionally contains only `rules/adaptive.yml` and `rules/robust.yml`. Do not add `rules/alerts/anomaly-alerts-example.yml` unless you also add an Alertmanager path intentionally.

Point Grafana at `http://thanos-query.anomaly-calculator.svc.cluster.local:10902`.
