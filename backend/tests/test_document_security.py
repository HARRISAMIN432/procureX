import hashlib
import io
import subprocess
from pathlib import Path

import pytest

from app.workers.document_security import (
    DocumentIntegrityError,
    ScannerExecutionError,
    copy_verified_stream,
    scan_with_clamav,
)


def test_copy_verified_stream_accepts_exact_declared_bytes() -> None:
    content = b"safe procurement document"
    destination = io.BytesIO()

    evidence = copy_verified_stream(
        io.BytesIO(content),
        destination,
        expected_size=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
        maximum_size=1024,
        chunk_size=5,
    )

    assert destination.getvalue() == content
    assert evidence.byte_size == len(content)


@pytest.mark.parametrize(
    ("expected_size", "expected_digest", "message"),
    [
        (3, hashlib.sha256(b"content").hexdigest(), "exceeds"),
        (7, "0" * 64, "digest"),
        (8, hashlib.sha256(b"content").hexdigest(), "size"),
    ],
)
def test_copy_verified_stream_rejects_integrity_mismatch(
    expected_size: int, expected_digest: str, message: str
) -> None:
    with pytest.raises(DocumentIntegrityError, match=message):
        copy_verified_stream(
            io.BytesIO(b"content"),
            io.BytesIO(),
            expected_size=expected_size,
            expected_sha256=expected_digest,
            maximum_size=1024,
        )


def test_clamav_clean_and_infected_are_explicit_verdicts(tmp_path: Path) -> None:
    calls = 0

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess([], 0, "ClamAV 1.4.3\n", "")
        return subprocess.CompletedProcess([], 1, f"{tmp_path}/file: Eicar FOUND\n", "")

    evidence = scan_with_clamav(
        tmp_path / "file", command=["clamscan"], timeout_seconds=30, runner=runner
    )

    assert evidence.clean is False
    assert evidence.scanner_version == "ClamAV 1.4.3"
    assert evidence.finding is not None and "Eicar FOUND" in evidence.finding


def test_clamav_operational_failure_is_not_treated_as_clean(tmp_path: Path) -> None:
    calls = 0

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess([], 0 if calls == 1 else 2, "ClamAV 1.4.3", "")

    with pytest.raises(ScannerExecutionError, match="without a verdict"):
        scan_with_clamav(tmp_path / "file", command=["clamscan"], timeout_seconds=30, runner=runner)
