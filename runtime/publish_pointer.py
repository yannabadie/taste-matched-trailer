#!/usr/bin/env python3
"""One-file GitHub Pages publisher. No credential is read or serialized here."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

REPOSITORY = "https://github.com/yannabadie/taste-matched-trailer.git"
CONFIG_PATH = "director-config.json"
DEADLINE = dt.datetime.fromisoformat("2026-11-17T04:45:00+00:00")


def pointer_expiry(config):
    """Return a timezone-aware expiry within the runtime deadline, or None."""
    value = config.get("expires_at") if isinstance(config, dict) else None
    if not isinstance(value, str):
        return None
    try:
        expiry = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry.utcoffset() is None:
            return None
        expiry = expiry.astimezone(dt.timezone.utc)
        return expiry if expiry <= DEADLINE else None
    except (ValueError, OverflowError):
        return None


def pointer_needs_renewal(config, instant):
    expiry = pointer_expiry(config)
    # A deadline-capped pointer cannot be extended, even in its final six hours.
    return expiry is None or (expiry < DEADLINE and expiry <= instant + dt.timedelta(hours=6))


def pointer_unexpired(config, instant):
    expiry = pointer_expiry(config)
    return expiry is not None and instant < expiry


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, document):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(document, out, indent=2, ensure_ascii=False)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def git(checkout, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    # The installed GitHub CLI consults its protected credential store. No token
    # enters this file, a command argument, the child environment or its output.
    command = ["/usr/bin/git", "-c", "credential.helper=", "-c",
               "credential.helper=" + str(Path.home() / ".local/bin/gh") + " auth git-credential"]
    if checkout:
        command += ["-C", str(checkout)]
    result = subprocess.run(command + list(args), env=env, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("GIT_OPERATION_FAILED:" + args[0].upper())
    return result.stdout


def publish(private_directory, api_base, runtime_status, acquire_lock):
    """CAS against the last observed/published bytes; ordinary push only."""
    from urllib.parse import urlparse
    url = urlparse(api_base)
    if url.scheme != "https" or not url.hostname or not url.hostname.endswith(".trycloudflare.com") or url.path not in ("", "/") or url.query or url.fragment or url.username or url.password:
        raise RuntimeError("PUBLIC_ENDPOINT_REFUSED")
    if runtime_status not in ("ready", "offline", "degraded"):
        raise RuntimeError("PUBLIC_STATUS_REFUSED")
    private = Path(private_directory)
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    release = acquire_lock(private / "publisher.lock", "publisher")
    try:
        checkout = private / "pointer-checkout"
        if not checkout.exists():
            git(None, "clone", "--single-branch", "--branch", "main", REPOSITORY, str(checkout))
        if git(checkout, "remote", "get-url", "origin").decode().strip() != REPOSITORY:
            raise RuntimeError("PUBLISHER_REMOTE_CHANGED")
        if git(checkout, "status", "--porcelain").strip():
            raise RuntimeError("PUBLISHER_WORKTREE_NOT_CLEAN")
        git(checkout, "fetch", "origin", "main")
        remote_bytes = git(checkout, "show", "origin/main:" + CONFIG_PATH)
        receipt_path = private / "pointer-state.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {"expected_sha256": digest(remote_bytes)}
        if digest(remote_bytes) != receipt["expected_sha256"]:
            # An unknown push outcome may already have published our exact candidate.
            if digest(remote_bytes) != receipt.get("pending_sha256"):
                raise RuntimeError("PUBLIC_POINTER_COMPARE_AND_SWAP_CONFLICT")
            receipt["expected_sha256"] = digest(remote_bytes)
            receipt.pop("pending_sha256", None)
            atomic_json(receipt_path, receipt)
        if receipt.get("pending_sha256"):
            # Complete our one known unpublished commit before preparing another.
            if git(checkout, "rev-list", "--count", "origin/main..HEAD").decode().strip() != "1" or git(checkout, "diff", "--name-only", "origin/main...HEAD").decode().splitlines() != [CONFIG_PATH]:
                raise RuntimeError("PUBLISHER_PENDING_COMMIT_UNCERTAIN")
            pending_bytes = git(checkout, "show", "HEAD:" + CONFIG_PATH)
            if digest(pending_bytes) != receipt["pending_sha256"]:
                raise RuntimeError("PUBLISHER_PENDING_CONTENT_CHANGED")
            git(checkout, "rebase", "origin/main")
            git(checkout, "push", "origin", "HEAD:main")
            remote_bytes = pending_bytes
            receipt = {"expected_sha256": digest(pending_bytes), "last_revision": json.loads(pending_bytes).get("revision"),
                       "commit": git(checkout, "rev-parse", "HEAD").decode().strip()}
            atomic_json(receipt_path, receipt)
        current = json.loads(remote_bytes)
        instant = dt.datetime.now(dt.timezone.utc)
        if instant >= DEADLINE:
            runtime_status = "offline"
        expiry = min(DEADLINE, instant + dt.timedelta(hours=24))
        if current.get("api_base_url") == api_base and current.get("runtime_status") == runtime_status and current.get("release") == "2.6.3" and not pointer_needs_renewal(current, instant):
            return {"changed": False, "config": current, "config_sha256": digest(remote_bytes)}
        # Refuse unrelated local commits; only our one pending config commit may rebase.
        ahead = git(checkout, "rev-list", "--count", "origin/main..HEAD").decode().strip()
        if ahead != "0":
            changed = git(checkout, "diff", "--name-only", "origin/main...HEAD").decode().splitlines()
            if changed != [CONFIG_PATH] or ahead != "1":
                raise RuntimeError("PUBLISHER_UNEXPECTED_LOCAL_COMMITS")
            git(checkout, "rebase", "origin/main")
        else:
            git(checkout, "merge", "--ff-only", "origin/main")
        document = {"api_base_url": api_base, "supported_modes": ["live"], "release": "2.6.3",
                    "revision": "runtime-" + uuid.uuid4().hex, "runtime_status": runtime_status,
                    "updated_at": instant.isoformat().replace("+00:00", "Z"),
                    "expires_at": expiry.isoformat().replace("+00:00", "Z")}
        target = checkout / CONFIG_PATH
        target.write_text(json.dumps(document, indent=2) + "\n")
        candidate_sha = digest(target.read_bytes())
        git(checkout, "add", "--", CONFIG_PATH)
        if git(checkout, "diff", "--cached", "--name-only").decode().splitlines() != [CONFIG_PATH]:
            raise RuntimeError("PUBLISHER_STAGED_PATH_REFUSED")
        # Reuse the author already present on this authorized repository if the
        # account has no global Git identity. Never change global configuration.
        try:
            git(checkout, "var", "GIT_AUTHOR_IDENT")
        except RuntimeError:
            author = git(checkout, "log", "-1", "--format=%an%n%ae", "origin/main").decode().strip().splitlines()
            if len(author) != 2 or any("\n" in item or not item for item in author):
                raise RuntimeError("PUBLISHER_GIT_IDENTITY_UNAVAILABLE")
            git(checkout, "config", "--local", "user.name", author[0])
            git(checkout, "config", "--local", "user.email", author[1])
        git(checkout, "commit", "-m", "Update declared jury runtime endpoint")
        receipt["pending_sha256"] = candidate_sha
        atomic_json(receipt_path, receipt)
        try:
            git(checkout, "push", "origin", "HEAD:main")
        except RuntimeError:
            git(checkout, "fetch", "origin", "main")
            observed = git(checkout, "show", "origin/main:" + CONFIG_PATH)
            if digest(observed) != candidate_sha:
                if digest(observed) != receipt["expected_sha256"]:
                    raise RuntimeError("PUBLIC_POINTER_COMPARE_AND_SWAP_CONFLICT")
                # Rebase only our unpublished one-file commit. No reset/force push.
                git(checkout, "rebase", "origin/main")
                git(checkout, "push", "origin", "HEAD:main")
        receipt = {"expected_sha256": candidate_sha, "last_revision": document["revision"],
                   "commit": git(checkout, "rev-parse", "HEAD").decode().strip()}
        atomic_json(receipt_path, receipt)
        return {"changed": True, "config": document, "config_sha256": candidate_sha, "commit": receipt["commit"]}
    finally:
        release()
