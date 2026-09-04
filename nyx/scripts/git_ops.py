import os
import json
import hmac
import hashlib
import subprocess
from pathlib import Path
from typing import Any

ROLE_IDENTITIES = {
    "planner": {
        "name": "Nyx Planner",
        "email": "agent-planner@nyx.local",
        "prefix": "plan"
    },
    "executor": {
        "name": "Nyx Executor",
        "email": "agent-executor@nyx.local",
        "prefix": "exec"
    },
    "reviewer": {
        "name": "Nyx Reviewer",
        "email": "agent-reviewer@nyx.local",
        "prefix": "verify"
    }
}

DEFAULT_SECRET = "nyx-tamper-evident-key-v1"

def canonical_json_bytes(data: Any) -> bytes:
    """Serializes data into canonical sorted JSON bytes for deterministic cryptographic hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sign_context_pack(context_pack_data: dict[str, Any], secret: str = DEFAULT_SECRET) -> str:
    """Signs a ContextPack to create a tamper-evident cryptographic signature."""
    # Exclude signature field itself if present
    clean_data = {k: v for k, v in context_pack_data.items() if k != "signature"}
    payload = canonical_json_bytes(clean_data)
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return sig

def verify_context_pack(context_pack_data: dict[str, Any], signature: str, secret: str = DEFAULT_SECRET) -> bool:
    """Verifies that a ContextPack has not been modified after being created by Planner."""
    expected = sign_context_pack(context_pack_data, secret)
    return hmac.compare_digest(expected, signature)

def role_git_commit(
    role: str,
    message: str,
    repo_dir: Path | str | None = None,
    stage_all: bool = True
) -> dict[str, Any]:
    """
    Executes a git commit tagged with specific role identity (Planner / Executor / Reviewer)
    and prefix.
    """
    role_key = role.lower()
    if role_key not in ROLE_IDENTITIES:
        raise ValueError(f"Unknown role '{role}'. Must be one of: {list(ROLE_IDENTITIES.keys())}")

    identity = ROLE_IDENTITIES[role_key]
    cwd = str(repo_dir) if repo_dir else str(Path(__file__).resolve().parent.parent.parent)

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = identity["name"]
    env["GIT_AUTHOR_EMAIL"] = identity["email"]
    env["GIT_COMMITTER_NAME"] = identity["name"]
    env["GIT_COMMITTER_EMAIL"] = identity["email"]

    if stage_all:
        subprocess.run(["git", "add", "."], cwd=cwd, check=True, capture_output=True, env=env)

    commit_msg = f"{identity['prefix']}: {message}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )

    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "role": identity["name"]
    }
