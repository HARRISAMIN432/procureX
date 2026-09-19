# AI system

## Framework decision

LangChain provides model, embedding, prompt, structured-output, retrieval, and typed tool
interfaces. LangGraph orchestrates bounded multi-step flows, durable checkpoints, branching,
retries, and human interrupts. ProcureX-owned adapters prevent framework or provider types from
becoming domain contracts.

## Initial graphs

### `document_analysis_graph`

```text
authorize source → load parse/OCR result → extract typed fields
→ validate anchors and arithmetic → human review interrupt
→ finalize extraction version
```

The graph is not started by upload. It may consume a document version only after a successful
parser result has moved that immutable version to `parsed`. The signed-upload/quarantine and
immutable parser-result contracts are implemented. Schema-validated extraction persistence,
same-parse evidence anchors, and the
`document_analysis_graph` human-review interrupt/resume state contract are implemented. The graph
rejects a resume whose source digest changed. Parser/OCR/model execution nodes, deterministic
commercial arithmetic, and production PostgreSQL checkpoint invocation remain pending.

### `evaluation_graph`

```text
load immutable evaluation snapshot → retrieve authorized evidence
→ evaluate requirements → validate citations → draft summary
→ unresolved-finding interrupt → finalize analysis run
```

The implemented graph contract gates finalization on validated citations, interrupts when findings
remain unresolved, and rejects a resume when the immutable evaluation digest has changed. Evaluation
snapshots now carry tenant-validated citations and a deterministic summary. Authorized retrieval,
model-backed narrative generation, persisted analysis-run lifecycle handling, and production
PostgreSQL checkpoint invocation remain pending.

## Execution contract

- Graph state contains identifiers and derived typed results, not full files or secrets.
- Every run records tenant, graph/version, thread, source digests, actor, and correlation IDs.
- PostgreSQL-backed checkpoints are required outside tests and local prototypes.
- Celery starts/resumes runs and supplies queue-level capacity controls.
- Replayed nodes use stable application idempotency keys for any persisted effect.
- A graph cannot approve, issue a PO, send an award, or initiate payment.

## Evidence and safety

- Supplier content is untrusted data and cannot introduce instructions or tools.
- Retrieval is filtered by current tenant and source authorization before similarity ranking.
- Structured results are schema-validated; malformed output retries within a fixed bound.
- Critical prices, quantities, currency, tax, and delivery basis require human verification.
- Unsupported factual claims abstain or remain unresolved.
- Tokens, time, retries, calls, and tenant cost have hard caps.

## Evaluation

Model, prompt, parser, graph, and retrieval changes run against a frozen labeled set. Track field
accuracy, critical errors, citation correctness, unsupported claims, corrections, latency, cost,
and repeated-run agreement. Deterministic pipeline baselines remain available to determine whether
additional graph complexity provides measurable value.
