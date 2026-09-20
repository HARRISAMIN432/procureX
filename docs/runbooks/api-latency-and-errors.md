# API latency and error triage

## Signals

Every completed HTTP request emits a structured `http_request_complete` log record with request
ID, method, route template, status, duration in milliseconds, and the exception class for an
unhandled failure. Query strings, authorization values, bodies, exception messages, and stack
traces are not included. Responses expose the same request ID and a
`Server-Timing: app;dur=...` value.

Requests at or above `PROCUREX_SLOW_REQUEST_THRESHOLD_MS`, and all `5xx` responses, log at warning
level. This is a diagnostic threshold, not proof that the roadmap latency targets are met.

## Triage

1. Group warnings by route, status, deployment version, organization only where authorized, and
   time window. Do not add supplier content or document text to telemetry.
2. Correlate the response request ID with application, database, queue, and edge telemetry.
3. For latency, separate database wait, connection-pool wait, provider calls, serialization, and
   application computation. Confirm whether the issue is isolated to one tenant or workload size.
4. For `5xx`, use the logged exception class and request ID. Reproduce with sanitized fixtures;
   never enable debug responses in staging or production.
5. If user impact is ongoing, stop a bad rollout or drain the affected instance using the approved
   deployment procedure. Do not bypass authorization, idempotency, or consistency checks to reduce
   latency.

## Verification

After mitigation, compare the same route and representative workload before and after the change.
Report sample size, percentiles, error rate, environment, database size, concurrency, and excluded
provider time. Confirm slow warnings and `5xx` rates return to baseline. A single fast request or
the `Server-Timing` header alone is not release evidence.

## Failure drill

In an isolated environment, exercise a route that raises a controlled exception and a route that
exceeds the warning threshold. Confirm the client receives a generic correlated `500`, the secret
test marker appears nowhere in the response or logs, security headers remain present, and exactly
one completion record contains the expected status and safe exception class.
