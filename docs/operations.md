# Operations

Monitor whether rule evaluation fits within the configured interval:

```promql
prometheus_rule_group_last_duration_seconds
/
prometheus_rule_group_interval_seconds
```

Use `0.5` as a warning threshold and `1` as a critical threshold. At `1`, rule evaluation no longer fits into the scheduled cycle.

Watch TSDB cardinality and ingest:

```promql
prometheus_tsdb_head_series
rate(prometheus_tsdb_head_samples_appended_total[5m])
```

Watch resource usage:

```promql
rate(process_cpu_seconds_total[5m])
process_resident_memory_bytes
go_memstats_heap_alloc_bytes
```

If rule evaluation becomes too slow:

1. Reduce the number of input series sent by remote write.
2. Further aggregate source metrics.
3. Increase long-term rule group intervals where appropriate.
4. Split adaptive and robust strategies onto separate Prometheus pairs if needed.
5. Increase CPU and memory for the anomaly Prometheus pair.

Retention should not be too short. The default examples use `15d` because the recording rules use 1 day and 1 week offsets. Shorter retention can produce missing or incomplete bands.
