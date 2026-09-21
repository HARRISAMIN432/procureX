import errno
import hashlib
import json
import resource
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pyseccomp  # type: ignore[import-untyped]


class DocumentSecurityError(RuntimeError):
    """Fail-closed error while retrieving or inspecting quarantined bytes."""


class DocumentIntegrityError(DocumentSecurityError):
    """Downloaded bytes do not match the immutable upload declaration."""


class ScannerExecutionError(DocumentSecurityError):
    """The malware scanner could not produce a trustworthy verdict."""


class ParserExecutionError(DocumentSecurityError):
    """The isolated parser could not produce a bounded structured result."""


@dataclass(frozen=True, slots=True)
class DownloadEvidence:
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ScanEvidence:
    clean: bool
    scanner: str
    scanner_version: str
    finding: str | None = None


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[no-untyped-def]
        self, request, file_pointer, code, message, headers, new_url
    ) -> None:
        raise HTTPError(new_url, code, "Document download redirects are forbidden", headers, None)


def copy_verified_stream(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    expected_size: int,
    expected_sha256: str,
    maximum_size: int,
    chunk_size: int = 64 * 1024,
) -> DownloadEvidence:
    """Copy a bounded stream while enforcing its declared size and digest."""
    if expected_size < 1 or expected_size > maximum_size:
        raise DocumentIntegrityError("Declared document size is outside the configured limit")

    digest = hashlib.sha256()
    byte_size = 0
    while chunk := source.read(chunk_size):
        byte_size += len(chunk)
        if byte_size > expected_size or byte_size > maximum_size:
            raise DocumentIntegrityError("Downloaded document exceeds its declared size")
        digest.update(chunk)
        destination.write(chunk)

    actual_sha256 = digest.hexdigest()
    if byte_size != expected_size:
        raise DocumentIntegrityError("Downloaded document size does not match its declaration")
    if actual_sha256 != expected_sha256:
        raise DocumentIntegrityError("Downloaded document digest does not match its declaration")
    return DownloadEvidence(byte_size=byte_size, sha256=actual_sha256)


def download_verified_asset(
    url: str,
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    maximum_size: int,
    timeout_seconds: float,
) -> DownloadEvidence:
    """Download a Cloudinary asset without redirects and verify it before use."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.cloudinary.com":
        raise DocumentSecurityError("Document download URL is not an approved Cloudinary endpoint")
    request = Request(url, headers={"Accept": "application/octet-stream"})  # noqa: S310
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) != expected_size:
                raise DocumentIntegrityError(
                    "Document response length does not match its declaration"
                )
            with destination.open("wb") as output:
                return copy_verified_stream(
                    response,
                    output,
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                    maximum_size=maximum_size,
                )
    except DocumentSecurityError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        destination.unlink(missing_ok=True)
        raise DocumentSecurityError("Unable to retrieve quarantined document bytes") from exc


def _bounded_detail(value: str, *, limit: int = 500) -> str:
    return " ".join(value.split())[:limit]


def scan_with_clamav(
    path: Path,
    *,
    command: Sequence[str],
    timeout_seconds: float,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ScanEvidence:
    """Run ClamAV with a timeout; only exit codes 0 and 1 are verdicts."""
    if not command or any(not part.strip() for part in command):
        raise ScannerExecutionError("Malware scanner command is not configured")
    try:
        version_result = runner(
            [*command, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=min(timeout_seconds, 10),
        )
        if version_result.returncode != 0:
            raise ScannerExecutionError("Malware scanner version check failed")
        scanner_version = _bounded_detail(version_result.stdout or version_result.stderr)
        if not scanner_version:
            raise ScannerExecutionError("Malware scanner returned no version")
        result = runner(
            [*command, "--no-summary", "--infected", "--stdout", str(path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScannerExecutionError("Malware scanner was unavailable or timed out") from exc

    detail = _bounded_detail(result.stdout or result.stderr)
    if result.returncode == 0:
        return ScanEvidence(clean=True, scanner="clamav", scanner_version=scanner_version)
    if result.returncode == 1:
        return ScanEvidence(
            clean=False,
            scanner="clamav",
            scanner_version=scanner_version,
            finding=detail or "malware_detected",
        )
    raise ScannerExecutionError("Malware scanner failed without a verdict")


def run_sandboxed_parser(
    path: Path,
    media_type: str,
    *,
    parser_command: Sequence[str],
    timeout_seconds: float,
    memory_bytes: int,
    output_bytes: int,
) -> dict[str, object]:
    """Execute the parser with no network and strict OS/process/output limits."""
    if not parser_command:
        raise ParserExecutionError("Document parser command is not configured")

    def apply_limits() -> None:
        cpu_seconds = max(1, min(int(timeout_seconds), 300))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_bytes, output_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        network_filter = pyseccomp.SyscallFilter(defaction=pyseccomp.ALLOW)
        for syscall in ("socket", "socketpair"):
            network_filter.add_rule(pyseccomp.ERRNO(errno.EPERM), syscall)
        network_filter.load()

    command = [*parser_command, str(path), media_type]
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(  # noqa: S603
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout_seconds,
                cwd=path.parent,
                env={
                    "HOME": str(path.parent),
                    "LANG": "C.UTF-8",
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                    "PATH": f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin",
                    "PYTHONUNBUFFERED": "1",
                },
                preexec_fn=apply_limits,
            )
            output.seek(0)
            raw = output.read(output_bytes + 1)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ParserExecutionError("Document parser was unavailable or timed out") from exc
    if len(raw) > output_bytes:
        raise ParserExecutionError("Document parser output exceeded its safety limit")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ParserExecutionError("Document parser returned invalid structured output") from exc
    if not isinstance(payload, dict):
        raise ParserExecutionError("Document parser returned an invalid result object")
    if result.returncode != 0 and "error_code" not in payload:
        raise ParserExecutionError("Document parser failed without a structured error")
    return {str(key): value for key, value in payload.items()}
