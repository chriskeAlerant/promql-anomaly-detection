#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

YAML_FILES = [
    "deploy/docker-compose/docker-compose.yml",
    "deploy/docker-compose/prometheus-anomaly-a.yml",
    "deploy/docker-compose/prometheus-anomaly-b.yml",
    "deploy/docker-compose/source-prometheus-example.yml",
    "deploy/docker-compose/thanos-query.yml",
    "deploy/docker-compose/grafana-dashboard-provider.yml",
    "deploy/kubernetes/configmaps.yaml",
    "deploy/kubernetes/prometheus-anomaly-a.yaml",
    "deploy/kubernetes/prometheus-anomaly-b.yaml",
    "deploy/kubernetes/thanos-query.yaml",
    "deploy/kubernetes/services.yaml",
    "examples/remote-write-source-prometheus.yml",
    "examples/metric-selection.yml",
    "examples/grafana-datasource-thanos.yml",
    "rules/adaptive.yml",
    "rules/robust.yml",
    "rules/alerts/anomaly-alerts-example.yml",
]

JSON_FILES = [
    "dashboards/anomaly-overview.json",
    "dashboards/anomaly-calculator-prometheus-health.json",
]

PROMTOOL_RULES = [
    "rules/adaptive.yml",
    "rules/robust.yml",
    "rules/examples/node_exporter.yml",
    "rules/examples/otel_demo.yml",
    "rules/extra/demo.yml",
    "rules/alerts/anomaly-alerts-example.yml",
    "examples/metric-selection.yml",
]

PROMTOOL_CONFIGS = [
    "deploy/docker-compose/prometheus-anomaly-a.yml",
    "deploy/docker-compose/prometheus-anomaly-b.yml",
    "deploy/docker-compose/source-prometheus-example.yml",
]


def check_yaml(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        list(yaml.safe_load_all(handle))


def check_json(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def staged_prometheus_config(relative: str, temp_dir: Path) -> Path:
    source = ROOT / relative
    with source.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    staged = dict(config)
    staged["rule_files"] = [
        rule_file.replace("/etc/prometheus/rules/", f"{ROOT}/rules/")
        .replace("/etc/prometheus/metric-selection.yml", f"{ROOT}/examples/metric-selection.yml")
        for rule_file in config.get("rule_files", [])
    ]

    target = temp_dir / Path(relative).name
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(staged, handle, sort_keys=False)
    return target


def main() -> int:
    for relative in YAML_FILES:
        check_yaml(ROOT / relative)
        print(f"yaml ok: {relative}")

    for relative in JSON_FILES:
        check_json(ROOT / relative)
        print(f"json ok: {relative}")

    promtool = shutil.which("promtool")
    if not promtool:
        print("promtool not found; skipped Prometheus rule/config validation", file=sys.stderr)
        return 0

    for relative in PROMTOOL_RULES:
        run([promtool, "check", "rules", relative])

    with tempfile.TemporaryDirectory(prefix="promql-anomaly-validation-") as directory:
        temp_dir = Path(directory)
        for relative in PROMTOOL_CONFIGS:
            staged_config = staged_prometheus_config(relative, temp_dir)
            run([promtool, "check", "config", str(staged_config)])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
