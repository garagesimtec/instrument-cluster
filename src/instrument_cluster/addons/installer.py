from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _find_systemctl() -> Optional[str]:
    # Prefer typical absolute paths, then $PATH
    for cand in ("/bin/systemctl", "/usr/bin/systemctl"):
        if Path(cand).exists():
            return cand
    found = shutil.which("systemctl")
    return found


SYSTEMCTL: Optional[str] = _find_systemctl()

DEST = Path("/opt/granturismo")
ENV_FILE = Path("/etc/default/instrument-cluster-proxy")
UNIT_NAME = "instrument-cluster-proxy.service"
DEFAULT_OUTPUT = "udp://127.0.0.1:5600"

DEFAULT_TARBALL_URL = (
    "https://github.com/chrshdl/granturismo/releases/download/v0.3.0/"
    "granturismo-selfcontained-0.3.0.tar.gz"
)


@dataclass
class InstallResult:
    ok: bool
    message: str = ""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _write(path: Path, content: str, mode: int = 0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)


def is_installed() -> bool:
    """Return True if the extracted bundle exists under /opt/granturismo."""
    return (DEST / "granturismo" / "proxy.py").exists() and (DEST / "vendor").exists()


def service_status() -> str:
    """
    Return 'active', 'inactive', 'failed', etc., for the preinstalled unit.
    On systems without systemctl (e.g. macOS), return 'unavailable'.
    """
    if SYSTEMCTL is None:
        return "unavailable"
    try:
        cp = _run([SYSTEMCTL, "is-active", UNIT_NAME])
        return cp.stdout.strip()
    except subprocess.CalledProcessError as e:
        # systemd returns non-zero for inactive/failed; capture text safely
        return (e.stdout or "inactive").strip()


def start_service() -> InstallResult:
    if SYSTEMCTL is None:
        return InstallResult(False, "systemctl not available on this OS")
    try:
        _run([SYSTEMCTL, "daemon-reload"])
        _run([SYSTEMCTL, "enable", "--now", UNIT_NAME])
        return InstallResult(True, f"Started {UNIT_NAME}")
    except subprocess.CalledProcessError as e:
        return InstallResult(False, e.stdout)


def restart_service() -> InstallResult:
    if SYSTEMCTL is None:
        return InstallResult(False, "systemctl not available on this OS")
    try:
        _run([SYSTEMCTL, "restart", UNIT_NAME])
        return InstallResult(True, f"Restarted {UNIT_NAME}")
    except subprocess.CalledProcessError as e:
        return InstallResult(False, e.stdout)


def stop_service() -> InstallResult:
    if SYSTEMCTL is None:
        return InstallResult(False, "systemctl not available on this OS")
    try:
        _run([SYSTEMCTL, "disable", "--now", UNIT_NAME])
        return InstallResult(True, f"Stopped {UNIT_NAME}")
    except subprocess.CalledProcessError as e:
        return InstallResult(False, e.stdout)


def install_from_url(
    url: str,
    ps_ip: str,
    sha256: Optional[str] = None,
    jsonl_output: Optional[str] = None,
) -> InstallResult:
    """
    Download & install the third-party granturismo bundle into /opt/granturismo,
    write /etc/default/simdash-proxy, and enable+start the preinstalled unit.
    If systemctl is not available (e.g., macOS), the install still completes
    and returns ok=True with a note that service control is unavailable.
    """
    if not ps_ip:
        return InstallResult(False, "PS5 IP missing")

    if not _tool_exists("curl") and not _tool_exists("wget"):
        return InstallResult(False, "Need curl or wget to download the tarball")

    DEST.mkdir(parents=True, exist_ok=True)

    # 1) Download to a temp file
    tmp = Path(tempfile.mkstemp(prefix="granturismo-", suffix=".tar.gz")[1])
    try:
        try:
            if _tool_exists("curl"):
                _run(["curl", "-L", "-o", str(tmp), url])
            else:
                _run(["wget", "-O", str(tmp), url])
        except subprocess.CalledProcessError as e:
            return InstallResult(False, e.stdout or "Download failed")

        # 2) Optional integrity check
        if sha256:
            h = hashlib.sha256()
            with tmp.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != sha256.lower():
                return InstallResult(False, "SHA256 mismatch; aborting")

        # 3) Extract to /opt/granturismo (idempotent over existing)
        try:
            with tarfile.open(tmp, "r:gz") as tf:
                tf.extractall(DEST)
        except Exception as e:
            return InstallResult(False, f"Extraction failed: {e}")

    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

    # 4) /etc/default/simdash-proxy with PS IP and output
    output = jsonl_output or DEFAULT_OUTPUT
    env_content = f"GT_PS_IP={ps_ip}\nGT_JSONL_OUTPUT={output}\n"
    try:
        _write(ENV_FILE, env_content, 0o644)
    except Exception as e:
        return InstallResult(False, f"Failed to write {ENV_FILE}: {e}")

    # 5) Enable + start the service (if available)
    if SYSTEMCTL is None:
        # On macOS/CI: installation is still successful; just can't manage service here.
        return InstallResult(
            True,
            "Installed bundle; service control unavailable on this OS (no systemctl).",
        )

    try:
        _run([SYSTEMCTL, "daemon-reload"])
        _run([SYSTEMCTL, "enable", "--now", UNIT_NAME])
    except subprocess.CalledProcessError as e:
        return InstallResult(False, e.stdout or "Failed to enable/start service")

    st = service_status()
    return InstallResult(True, f"Installed bundle, service: {st}")
