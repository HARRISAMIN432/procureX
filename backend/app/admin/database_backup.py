import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from app.core.config import Environment, Settings, get_settings


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PostgresTarget:
    host: str
    port: int
    database: str
    username: str
    password: str
    libpq_environment: tuple[tuple[str, str], ...] = ()

    def command_args(self) -> list[str]:
        return [
            "--no-password",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--username",
            self.username,
            "--dbname",
            self.database,
        ]

    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PGPASSWORD"] = self.password
        environment.update(self.libpq_environment)
        return environment


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    archive: Path
    manifest: Path
    sha256: str
    size_bytes: int


def postgres_target(database_url: str) -> PostgresTarget:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg", "postgres"}:
        raise DatabaseBackupError("Database backup requires a PostgreSQL URL")
    database = unquote(parsed.path.lstrip("/"))
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if not parsed.hostname or not database or not username:
        raise DatabaseBackupError("Database URL must include host, database, and username")
    query = parse_qs(parsed.query, keep_blank_values=False)
    libpq_environment: list[tuple[str, str]] = []
    option_names = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
    }
    if "ssl" in query and "sslmode" not in query:
        query["sslmode"] = query["ssl"]
    for option, environment_name in option_names.items():
        values = query.get(option)
        if values:
            libpq_environment.append((environment_name, values[-1]))
    return PostgresTarget(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=database,
        username=username,
        password=password,
        libpq_environment=tuple(libpq_environment),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_postgres_tool(command: list[str], target: PostgresTarget) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=target.environment(),
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise DatabaseBackupError(f"Required PostgreSQL tool is unavailable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise DatabaseBackupError(f"PostgreSQL tool failed: {command[0]}") from exc


def _require_nonproduction(settings: Settings) -> None:
    if settings.environment is Environment.PRODUCTION:
        raise DatabaseBackupError(
            "This local archive tool is disabled in production; "
            "use the approved managed backup procedure"
        )


def create_backup(
    settings: Settings,
    output_directory: Path,
    *,
    created_at: datetime | None = None,
) -> BackupArtifact:
    _require_nonproduction(settings)
    target = postgres_target(settings.database_url)
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    effective_created_at = (created_at or datetime.now(UTC)).astimezone(UTC)
    timestamp = effective_created_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"procurex-{timestamp}-{uuid.uuid4().hex[:8]}"
    archive = output_directory / f"{stem}.dump"
    manifest = output_directory / f"{stem}.manifest.json"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{stem}-", suffix=".dump.tmp", dir=output_directory
    )
    os.close(descriptor)
    temporary_archive = Path(temporary_name)
    try:
        run_postgres_tool(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(temporary_archive),
                *target.command_args(),
            ],
            target,
        )
        size_bytes = temporary_archive.stat().st_size
        if size_bytes <= 0:
            raise DatabaseBackupError("PostgreSQL backup archive is empty")
        checksum = sha256_file(temporary_archive)
        os.chmod(temporary_archive, 0o600)
        temporary_archive.replace(archive)
        manifest_payload = {
            "format": "postgresql-custom",
            "archive": archive.name,
            "created_at": effective_created_at.isoformat(),
            "sha256": checksum,
            "size_bytes": size_bytes,
        }
        temporary_manifest = manifest.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(temporary_manifest, 0o600)
        temporary_manifest.replace(manifest)
        return BackupArtifact(archive, manifest, checksum, size_bytes)
    except BaseException:
        temporary_archive.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        manifest.with_suffix(".json.tmp").unlink(missing_ok=True)
        raise


def verify_backup(archive: Path, manifest: Path) -> BackupArtifact:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseBackupError("Backup manifest cannot be read") from exc
    if payload.get("format") != "postgresql-custom" or payload.get("archive") != archive.name:
        raise DatabaseBackupError("Backup manifest does not describe this archive")
    try:
        expected_size = int(payload["size_bytes"])
        expected_checksum = str(payload["sha256"])
        actual_size = archive.stat().st_size
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise DatabaseBackupError("Backup archive or manifest is incomplete") from exc
    actual_checksum = sha256_file(archive)
    if actual_size != expected_size or actual_checksum != expected_checksum:
        raise DatabaseBackupError("Backup archive failed size or SHA-256 verification")
    return BackupArtifact(archive, manifest, actual_checksum, actual_size)


def restore_backup(
    settings: Settings,
    archive: Path,
    manifest: Path,
    *,
    confirm_empty_target: bool,
) -> None:
    _require_nonproduction(settings)
    if not confirm_empty_target:
        raise DatabaseBackupError(
            "Restore requires explicit confirmation of an empty target database"
        )
    verified = verify_backup(archive, manifest)
    target = postgres_target(settings.database_url)
    run_postgres_tool(["pg_restore", "--list", str(verified.archive)], target)
    run_postgres_tool(
        [
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            *target.command_args(),
            str(verified.archive),
        ],
        target,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or restore a non-production ProcureX DB archive"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--output-directory", type=Path, required=True)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--archive", type=Path, required=True)
    restore_parser.add_argument("--manifest", type=Path, required=True)
    restore_parser.add_argument("--confirm-empty-target", action="store_true")
    arguments = parser.parse_args()
    settings = get_settings()
    try:
        if arguments.command == "backup":
            artifact = create_backup(settings, arguments.output_directory)
            print(
                json.dumps({"archive": str(artifact.archive), "manifest": str(artifact.manifest)})
            )
        else:
            restore_backup(
                settings,
                arguments.archive,
                arguments.manifest,
                confirm_empty_target=arguments.confirm_empty_target,
            )
            print(json.dumps({"status": "restored"}))
    except DatabaseBackupError as exc:
        parser.exit(1, f"database backup error: {exc}\n")


if __name__ == "__main__":
    main()
