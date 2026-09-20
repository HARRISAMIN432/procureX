import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.admin.database_backup import (
    DatabaseBackupError,
    create_backup,
    postgres_target,
    restore_backup,
    verify_backup,
)
from app.core.config import AuthMode, Environment, Settings


def test_postgres_target_keeps_password_out_of_command_arguments() -> None:
    target = postgres_target(
        "postgresql+asyncpg://backup%40user:very%2Fsecret@db.example:5544/procurex"
        "?sslmode=verify-full&sslrootcert=%2Fcerts%2Froot.pem"
    )

    assert target.command_args() == [
        "--no-password",
        "--host",
        "db.example",
        "--port",
        "5544",
        "--username",
        "backup@user",
        "--dbname",
        "procurex",
    ]
    assert "very/secret" not in " ".join(target.command_args())
    assert target.environment()["PGPASSWORD"] == "very/secret"
    assert target.environment()["PGSSLMODE"] == "verify-full"
    assert target.environment()["PGSSLROOTCERT"] == "/certs/root.pem"


def test_backup_creates_private_verified_archive_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        commands.append(command)
        archive = Path(command[command.index("--file") + 1])
        archive.write_bytes(b"verified pg archive")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    artifact = create_backup(
        Settings(_env_file=None),
        tmp_path,
        created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    )

    assert commands[0][0] == "pg_dump"
    assert "procurex" in commands[0]
    assert "procurex:procurex" not in " ".join(commands[0])
    assert artifact.archive.read_bytes() == b"verified pg archive"
    assert artifact.archive.stat().st_mode & 0o777 == 0o600
    assert artifact.manifest.stat().st_mode & 0o777 == 0o600
    payload = json.loads(artifact.manifest.read_text(encoding="utf-8"))
    assert payload["archive"] == artifact.archive.name
    assert payload["created_at"] == "2026-09-20T12:00:00+00:00"
    assert payload["sha256"] == artifact.sha256
    assert payload["size_bytes"] == artifact.size_bytes
    assert verify_backup(artifact.archive, artifact.manifest) == artifact


def test_restore_verifies_before_running_non_destructive_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        if command[0] == "pg_dump":
            Path(command[command.index("--file") + 1]).write_bytes(b"archive")
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    settings = Settings(_env_file=None)
    artifact = create_backup(settings, tmp_path)
    commands.clear()

    restore_backup(
        settings,
        artifact.archive,
        artifact.manifest,
        confirm_empty_target=True,
    )

    assert commands[0][:2] == ["pg_restore", "--list"]
    assert commands[1][0] == "pg_restore"
    assert "--single-transaction" in commands[1]
    assert "--clean" not in commands[1]
    assert "--create" not in commands[1]


def test_restore_rejects_missing_confirmation_and_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        Path(command[command.index("--file") + 1]).write_bytes(b"archive")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    settings = Settings(_env_file=None)
    artifact = create_backup(settings, tmp_path)

    with pytest.raises(DatabaseBackupError, match="explicit confirmation"):
        restore_backup(
            settings,
            artifact.archive,
            artifact.manifest,
            confirm_empty_target=False,
        )
    artifact.archive.write_bytes(b"tampered")
    with pytest.raises(DatabaseBackupError, match="verification"):
        restore_backup(
            settings,
            artifact.archive,
            artifact.manifest,
            confirm_empty_target=True,
        )


def test_local_archive_tool_is_disabled_in_production(tmp_path: Path) -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.OIDC,
        oidc_issuer="https://identity.example.com",
        oidc_audience="procurex-api",
        cloudinary_cloud_name="procurex",
        cloudinary_api_key="key",
        cloudinary_api_secret="secret",
        gemini_api_key="model-key",
        allowed_hosts=["api.procurex.example"],
        cors_allowed_origins=["https://app.procurex.example"],
        _env_file=None,
    )
    with pytest.raises(DatabaseBackupError, match="disabled in production"):
        create_backup(settings, tmp_path)


def test_postgres_tool_failures_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.CalledProcessError(1, command, stderr=b"password=very-secret")

    monkeypatch.setattr(subprocess, "run", failed_run)
    with pytest.raises(DatabaseBackupError, match="pg_dump") as error:
        create_backup(Settings(_env_file=None), tmp_path)
    assert "very-secret" not in str(error.value)
    assert not any(path.suffix == ".tmp" for path in tmp_path.iterdir())
