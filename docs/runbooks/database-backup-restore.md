# Database backup and restore drill

## Scope and limitations

The bundled CLI creates a PostgreSQL custom-format archive plus a SHA-256/size manifest for local,
test, and isolated staging drills. It is deliberately disabled in production: production must use
the selected platform's encrypted managed-backup, point-in-time recovery, access-control, and
retention procedure. A successful database restore does not restore Cloudinary originals,
derivatives, provider backups, queues, or external accounting state, so it does not by itself prove
the product RPO/RTO or satisfy the R1 recovery gate.

PostgreSQL client tools compatible with the server major version must be installed. Credentials
come from `PROCUREX_DATABASE_URL`; passwords are passed through `PGPASSWORD`, never command-line
arguments, manifests, or normal output. Interactive password prompts are disabled so unattended
drills fail instead of hanging. Archive and manifest files are mode `0600`.

## Create and verify an archive

Activate the backend environment and point `PROCUREX_DATABASE_URL` at the authorized source:

```bash
python -m app.admin.database_backup backup --output-directory ./backups
```

The command prints only the archive and manifest paths. Move both through the approved encrypted
storage path. Do not commit them or attach them to ordinary tickets. Verification is performed
again immediately before every restore.

## Restore drill

Provision a new, empty, isolated PostgreSQL database with no customer connectivity. Set
`PROCUREX_ENVIRONMENT=test` or `staging` and point `PROCUREX_DATABASE_URL` at that target. The CLI
does not use `--clean` or `--create`, so it will not erase or replace an existing database.

```bash
python -m app.admin.database_backup restore \
  --archive ./backups/procurex-TIMESTAMP-ID.dump \
  --manifest ./backups/procurex-TIMESTAMP-ID.manifest.json \
  --confirm-empty-target
```

The confirmation asserts that the operator independently verified the target is disposable and
empty. The tool first checks archive name, size, and SHA-256, then asks `pg_restore` to list the
archive before restoring it in one transaction with ownership and privilege replay disabled.

## Verification and evidence

1. Run `alembic current` against the restored target and compare it with the source release.
2. Use read-only checks to reconcile tenant counts, critical workflow counts, ledger totals, audit
   events, document-version metadata, and latest immutable digests against pre-recorded source
   evidence.
3. Confirm tenant RLS and application-role restrictions remain enabled; do not validate only as a
   database owner or superuser.
4. Reconcile every Cloudinary asset reference separately and test authorized access to a permitted
   sample. Record missing provider assets without silently deleting metadata.
5. Record archive time, restore start/end, versions, data volume, verification queries/results,
   exceptions, achieved recovery point/time, operator, and reviewer.
6. Destroy the isolated restored environment through the approved process after evidence review.

Escalate checksum mismatch, partial restore, migration mismatch, missing audit history, broken RLS,
or provider-asset mismatch. Do not weaken verification or retry into a non-empty target.
