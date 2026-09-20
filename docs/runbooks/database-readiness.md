# Database readiness failure

## Signal and impact

`GET /health/ready` returns `503` with database status `timeout` or `unavailable`. The endpoint is
bounded by `PROCUREX_READINESS_TIMEOUT_SECONDS` and never returns connection details. Liveness may
remain healthy because the API process can still answer even though tenant workflows must not
receive traffic.

Load balancers and orchestrators should remove an instance from service after repeated readiness
failures. They must use `/health/live` only for process restart decisions; a database outage should
not create an uncontrolled restart loop.

## Triage

1. Record the incident start time, affected environment, request ID, and alert source.
2. Check database service health, connection saturation, network/DNS errors, certificate expiry,
   and recent database or application deployments.
3. Check API pool utilization and error rates. Do not paste database URLs or credentials into the
   incident channel or ticket.
4. If the database is reachable from its own control plane but not the API, check security groups,
   routing, secret versions, and service identity changes.
5. Pause migrations, bulk jobs, and deployment rollout until the cause is understood.

## Recovery and verification

Restore the dependency or roll forward/back the responsible infrastructure change using the
environment's approved procedure. Do not bypass readiness or point production at another database
without a data-consistency decision.

Verify from the same network path as the service:

```bash
curl --fail-with-body --max-time 5 https://api.example.com/health/ready
```

Expected recovery response:

```json
{"status":"ok","checks":{"database":{"status":"ok"}}}
```

Confirm application error rate, connection saturation, and queue backlog return to baseline before
closing the incident. Record timeline, cause, data-integrity assessment, recovery action, and
follow-up owner.

## Drill

In an isolated test environment, block the API's database route or stop the test database. Confirm
readiness becomes `503` within the configured timeout, liveness stays `200`, traffic is drained,
and no connection string appears in the response or logs. Restore the database and confirm
readiness recovers without restarting the API. Record measured detection and recovery times; this
runbook alone is not evidence that an RTO has been met.
