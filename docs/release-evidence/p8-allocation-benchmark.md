# P8 allocation benchmark evidence

Date: 2026-09-20

Command:

```bash
python -m app.admin.performance_benchmark \
  --items 100 --suppliers 50 --repetitions 5 --maximum-p95-ms 30000
```

Environment: Python 3.12.13, Linux 7.0.0-31-generic x86_64, glibc 2.43. The fixture contains
100 item demands and 50 eligible suppliers per item (5,000 offers), deterministic integer costs,
fixed supplier costs, independent feasibility validation, one solver worker, and a 30-second solver
limit.

Measured wall-clock durations: 1764.111, 1701.470, 1772.331, 1370.553, and 1436.524 ms. Median:
1701.470 ms. Nearest-rank p95/max: 1772.331 ms. All five runs returned a feasible/optimal result
that passed every independent constraint check.

This passes the roadmap's 30-second optimization budget for this synthetic fixture on this machine.
It does not establish API latency, multi-user capacity, database performance, or production p95.
Re-run the command on the release artifact and target-like hardware; retain raw output with the
release evidence.
