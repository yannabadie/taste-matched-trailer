#!/usr/bin/env python3
"""Dedicated user-session lifecycle. Health GET only; never invokes a model or Qloo."""
import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

from publish_pointer import atomic_json, publish, DEADLINE, pointer_expiry, pointer_needs_renewal, pointer_unexpired

BASE = Path(__file__).resolve().parents[1]
APP = BASE / "taste-matched-trailer"
PRIVATE = Path.home() / "Library/Application Support/Agentique/qloo-hackathon-private"
OLD = PRIVATE / "public-20261020"
RUNTIME = PRIVATE / "jury-runtime-20261020"
META = OLD / "processes.json"
STATE = OLD / "gateway-state/jobs.json"
LEASE = RUNTIME / "admission.json"
CONTROL = RUNTIME / "control.json"
LABEL = "com.yannabadie.qloo-jury"
PLIST = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
NODE = Path.home() / ".local/bin/node"
PYTHON = Path(sys.executable).resolve()
HOSTS = {"backend": "http://127.0.0.1:49324", "gateway": "http://127.0.0.1:49325"}
PAGE_CONFIG = "https://yannabadie.github.io/taste-matched-trailer/director-config.json"
PAGE_ORIGIN = "https://yannabadie.github.io"
LOG_LIMIT = 256 * 1024
STOP = threading.Event()
LOG_LOCK = threading.Lock()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise RuntimeError("PRIVATE_DIRECTORY_OWNERSHIP_REFUSED")


def alive(pid):
    if not isinstance(pid, int) or pid < 2:
        raise RuntimeError("LOCK_PID_INVALID")
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    # PermissionError is intentionally not interpreted as a dead owner.


def recover_dead_lock(lock, kind):
    """Archive once under an exclusive recovery mutex; never unlink an active lock."""
    lock = Path(lock)
    recovery = lock.with_name(lock.name + ".runtime-recovery")
    fd = os.open(recovery, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "kind": kind}).encode())
        if not lock.exists():
            return None
        info = lock.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise RuntimeError("LOCK_OWNERSHIP_UNCERTAIN")
        raw = lock.read_bytes()
        owner = json.loads(raw)
        if alive(owner.get("pid")):
            raise RuntimeError("LOCK_OWNER_ALIVE")
        again = lock.lstat()
        if (again.st_ino, again.st_dev) != (info.st_ino, info.st_dev) or lock.read_bytes() != raw:
            raise RuntimeError("LOCK_CHANGED_DURING_RECOVERY")
        archive = lock.with_name(lock.name + ".stale-" + str(time.time_ns()) + "-" + uuid.uuid4().hex)
        lock.rename(archive)
        return {"kind": kind, "archived_name": archive.name, "sha256": hashlib.sha256(raw).hexdigest(), "dead_pid": owner["pid"]}
    finally:
        os.close(fd)
        recovery.unlink()


def acquire_lock(lock, kind):
    lock = Path(lock)
    owner = uuid.uuid4().hex
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        recover_dead_lock(lock, kind)
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"pid": os.getpid(), "owner": owner, "kind": kind}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    def release():
        try:
            if json.loads(lock.read_text()).get("owner") == owner:
                lock.unlink()
        except (FileNotFoundError, ValueError):
            pass
    return release


def log(event, **values):
    """Only structured operational fields; never serialize an exception/env/body."""
    record = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "event": event, **values}
    encoded = json.dumps(record, ensure_ascii=False) + "\n"
    with LOG_LOCK:
        target = RUNTIME / "lifecycle.jsonl"
        if target.exists() and target.stat().st_size + len(encoded.encode()) > LOG_LIMIT:
            older = target.with_suffix(".jsonl.1")
            os.replace(target, older)
        fd = os.open(target, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(encoded)


def summary():
    data = json.loads(STATE.read_text())
    return {"reserved": data["reserved"], "physical_used": sum(f.get("physical_used", 0) for f in data["families"].values()),
            "models_used": sum(f.get("models_used", 0) for f in data["families"].values()),
            "statuses": dict(collections.Counter(j["status"] for j in data["jobs"].values())),
            "halted": data.get("halted"), "state_sha256": sha(STATE), "policy_hash": data["policy_hash"]}


def no_active_jobs():
    current = summary()
    if any(current["statuses"].get(k, 0) for k in ("running", "queued")):
        raise RuntimeError("ACTIVE_OR_QUEUED_JOB_REFUSED")
    return current


def identity(pid):
    if not alive(pid):
        return None
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart=", "-o", "command="], capture_output=True, text=True, timeout=5)
    line = result.stdout.strip()
    if result.returncode or len(line) < 25:
        return None
    return {"pid": pid, "start": line[:24], "command_sha256": hashlib.sha256(line[24:].encode()).hexdigest(), "command": line[24:].strip()}


def matches(record):
    current = identity(record["pid"])
    return current and current["start"] == record["start"] and current["command_sha256"] == record["command_sha256"]


def safe_record(record):
    return {key: record[key] for key in ("pid", "start", "command_sha256")}


def terminate(record):
    if not matches(record):
        if alive(record["pid"]):
            raise RuntimeError("PROCESS_IDENTITY_CHANGED")
        return
    os.kill(record["pid"], signal.SIGTERM)
    for _ in range(100):
        if not matches(record):
            return
        time.sleep(0.1)
    # No SIGKILL: an unexpectedly busy backend may still be cleaning a worker.
    raise RuntimeError("PROCESS_DID_NOT_STOP_CLEANLY")


def backend_health():
    try:
        with urllib.request.urlopen(HOSTS["backend"] + "/api/health", timeout=3) as response:
            health = json.load(response)
        return health.get("status") == "ok" and health.get("qloo_key_present_on_server") is True and health.get("llm_route_configured") == "guarded_qwen_18080"
    except Exception:
        return False


def get_json(url, timeout=5):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Origin": PAGE_ORIGIN}), timeout=timeout) as response:
        return json.load(response)


def write_lease(accepting, valid_until=None):
    instant = dt.datetime.now(dt.timezone.utc)
    expires_at = instant + dt.timedelta(seconds=45)
    if valid_until is not None:
        expires_at = min(expires_at, valid_until)
        accepting = bool(accepting) and instant < valid_until
    atomic_json(LEASE, {"schema_version": 1, "accepting": bool(accepting),
                       "expires_at": expires_at.isoformat()})


def source_pins():
    manifest = json.loads((BASE / "runtime/SOURCE-PINS.json").read_text())
    for relative, expected in manifest["sha256"].items():
        if sha(BASE / relative) != expected:
            raise RuntimeError("RUNTIME_SOURCE_PIN_MISMATCH")
    return manifest


def basic_env():
    return {key: os.environ[key] for key in ("HOME", "PATH", "LANG", "TMPDIR") if key in os.environ} | {"PYTHONUNBUFFERED": "1"}


def backend_env():
    env = basic_env()
    pins = source_pins()["sha256"]
    spec = importlib.util.spec_from_file_location("qloo_private_keychain", PRIVATE / "keychain_qloo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Protected Keychain -> backend environment only. Never stdout/disk/arguments.
    env.update(QLOO_API_KEY=module.read_key(), QLOO_BASE_URL="https://hackathon.api.qloo.com",
               QLOO_TRUSTED_BASE_URL="https://hackathon.api.qloo.com", QLOO_HOME=str(OLD / "harness"),
               DIRECTOR_ENABLE_LIVE_LLM="1", DIRECTOR_LLM_PROVIDER="guarded_qwen_18080",
               DIRECTOR_QWEN_BRIDGE_ENTRY=str(APP / "bridge/director_entry.py"),
               DIRECTOR_QWEN_EXPECTED_DIRECTOR_SHA256=pins["taste-matched-trailer/cultural_launch_director.py"],
               DIRECTOR_QWEN_EXPECTED_RUNNER_SHA256=pins["taste-matched-trailer/guarded_qwen_runner.py"],
               DIRECTOR_QWEN_ACTIVE_SECONDS="120")
    return env


class Supervisor:
    def __init__(self):
        self.roles = {}
        self.children = {}
        self.url = None
        self.published_revision = None
        self.pointer = None
        self.pointer_checked = 0
        self.failures = collections.defaultdict(list)
        self.next_start = collections.defaultdict(float)
        self.gateway_ready = False

    def save(self):
        data = {"release": "2.6.3", "supervisor_pid": os.getpid(), "managed_by": LABEL,
                "components": self.roles, "backend_origin": HOSTS["backend"], "gateway_origin": HOSTS["gateway"],
                "tunnel_url": self.url, "application_only": True, "autostart_after_user_login": True,
                "available_before_login_or_filevault_unlock": False, "api_calls_on_start": 0, "model_calls_on_start": 0}
        atomic_json(META, data)

    def consume_log(self, role, stream):
        # Drain all output but persist only whitelisted events. This avoids keys,
        # paths, prompts, HTTP payloads and unbounded third-party logs on disk.
        for line in iter(stream.readline, b""):
            if role == "tunnel":
                found = re.search(rb"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if found:
                    self.url = found[0].decode()
                    self.published_revision = None
                    log("tunnel_endpoint_observed", endpoint=self.url)
            elif b"public_gateway_ready" in line:
                log("gateway_listener_ready")
        stream.close()

    def start(self, role):
        source_pins()
        if role == "backend":
            lock = APP / "var/runs/application-active.lock"
            if lock.exists():
                proof = recover_dead_lock(lock, "backend_application")
                if proof:
                    log("stale_application_lock_archived", **proof)
            command = [str(NODE), str(APP / "qloo_mcp_backend.mjs"), "--serve", "--port", "49324"]
            env = backend_env()
        elif role == "gateway":
            write_lease(False)
            command = [str(NODE), str(APP / "public_gateway.mjs"), "--serve"]
            env = basic_env() | {"DIRECTOR_PUBLIC_ALLOWED_ORIGIN": PAGE_ORIGIN, "DIRECTOR_PUBLIC_BACKEND_ORIGIN": HOSTS["backend"],
                "DIRECTOR_PUBLIC_STATE_DIR": str(OLD / "gateway-state"), "DIRECTOR_PUBLIC_TRUST_PROXY": "127.0.0.1",
                "DIRECTOR_PUBLIC_PORT": "49325", "DIRECTOR_PUBLIC_ADMISSION_FILE": str(LEASE)}
        elif role == "tunnel":
            cloud = json.loads((BASE / "publication/CLOUDFLARED.json").read_text())
            if sha(cloud["path"]) != cloud["binary_sha256"]:
                raise RuntimeError("CLOUDFLARED_PIN_MISMATCH")
            self.url = None
            self.published_revision = None
            command = [cloud["path"], "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", HOSTS["gateway"]]
            env = basic_env()
        else:
            command = ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())]
            env = basic_env()
        child = subprocess.Popen(command, cwd=APP, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        env.pop("QLOO_API_KEY", None)
        self.children[role] = child
        time.sleep(0.15)
        record = identity(child.pid)
        if not record:
            raise RuntimeError("COMPONENT_EXITED_DURING_START")
        self.roles[role] = safe_record(record)
        threading.Thread(target=self.consume_log, args=(role, child.stdout), daemon=True).start()
        self.save()
        log("component_started", role=role, pid=child.pid)

    def adopt(self):
        if not META.exists():
            return
        metadata = json.loads(META.read_text())
        if metadata.get("managed_by") != LABEL:
            raise RuntimeError("LEGACY_PROCESSES_REQUIRE_CONTROLLED_TAKEOVER")
        for role, record in metadata.get("components", {}).items():
            if matches(record):
                self.roles[role] = record
                log("component_adopted", role=role, pid=record["pid"])
            elif alive(record["pid"]):
                raise RuntimeError("PROCESS_IDENTITY_CHANGED")
        if "tunnel" in self.roles:
            self.url = metadata.get("tunnel_url")

    def loop(self):
        self.adopt()
        while not STOP.is_set() and dt.datetime.now(dt.timezone.utc) < DEADLINE:
            healthy = True
            for role in ("backend", "gateway", "tunnel", "idle_sleep_guard"):
                record = self.roles.get(role)
                if record and matches(record):
                    continue
                if record:
                    self.roles.pop(role, None)
                    self.children.pop(role, None)
                    write_lease(False)
                    log("component_not_running", role=role)
                healthy = False
                if time.monotonic() < self.next_start[role]:
                    continue
                if role == "tunnel" and "gateway" not in self.roles:
                    continue
                try:
                    self.start(role)
                except Exception as error:
                    code = str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else type(error).__name__
                    log("component_start_refused", role=role, code=code)
                    self.failures[role] = [t for t in self.failures[role] if t > time.monotonic() - 300] + [time.monotonic()]
                    self.next_start[role] = time.monotonic() + min(300, 10 * 2 ** min(5, len(self.failures[role]) - 1))
            try:
                source_pins()
                pins_ok = True
            except RuntimeError:
                pins_ok = False
            ready = healthy and pins_ok and backend_health() and self.url is not None and not summary()["halted"]
            control = json.loads(CONTROL.read_text())
            declared = "ready" if ready and control.get("allow_live") else "offline"
            if self.url and (self.pointer is None or self.pointer["api_base_url"] != self.url or self.pointer["runtime_status"] != declared or pointer_needs_renewal(self.pointer, dt.datetime.now(dt.timezone.utc))):
                if time.monotonic() >= self.next_start["publisher"]:
                    try:
                        result = publish(RUNTIME, self.url, declared, acquire_lock)
                        self.pointer = result["config"]
                        log("pointer_published", revision=self.pointer["revision"], status=declared, changed=result["changed"])
                    except Exception as error:
                        code = str(error) if re.fullmatch(r"[A-Z_:]+", str(error)) else type(error).__name__
                        log("pointer_publish_refused", code=code)
                        self.next_start["publisher"] = time.monotonic() + 120
            if self.pointer and time.monotonic() - self.pointer_checked > 15:
                self.pointer_checked = time.monotonic()
                try:
                    visible = get_json(PAGE_CONFIG + "?revision=" + self.pointer["revision"])
                    self.published_revision = visible.get("revision") if visible.get("api_base_url") == self.url and pointer_unexpired(visible, dt.datetime.now(dt.timezone.utc)) else None
                except Exception:
                    self.published_revision = None
            allow = ready and control.get("allow_live") is True and self.pointer and self.published_revision == self.pointer.get("revision") and pointer_unexpired(self.pointer, dt.datetime.now(dt.timezone.utc))
            write_lease(allow, pointer_expiry(self.pointer))
            self.save()
            STOP.wait(5)
        write_lease(False)
        if self.url:
            try:
                publish(RUNTIME, self.url, "offline", acquire_lock)
            except Exception:
                log("offline_pointer_not_confirmed")
        # Graceful user service stop, never kill a worker/inference underneath it.
        try:
            no_active_jobs()
        except RuntimeError:
            log("shutdown_waiting_for_active_job")
            for _ in range(65):
                time.sleep(5)
                try:
                    no_active_jobs()
                    break
                except RuntimeError:
                    continue
            else:
                log("shutdown_components_left_for_manual_reconciliation")
                return
        for role in ("tunnel", "gateway", "backend", "idle_sleep_guard"):
            if self.roles.get(role):
                try:
                    terminate(self.roles[role])
                    self.roles.pop(role)
                except RuntimeError:
                    log("component_stop_not_confirmed", role=role)
        self.save()


def takeover():
    no_active_jobs()
    private_directory(RUNTIME)
    archive = RUNTIME / ("takeover-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    archive.mkdir(mode=0o700)
    metadata = json.loads(META.read_text())
    if metadata.get("managed_by") == LABEL:
        raise RuntimeError("ALREADY_MANAGED")
    records = {}
    expected = {"backend_pid": str(APP / "qloo_mcp_backend.mjs"), "gateway_pid": str(APP / "public_gateway.mjs"), "tunnel_pid": "--url " + HOSTS["gateway"], "idle_sleep_guard_pid": "caffeinate"}
    for field, marker in expected.items():
        record = identity(metadata[field])
        if record and marker not in record["command"]:
            if field in ("backend_pid", "gateway_pid"):
                cwd = subprocess.run(["/usr/sbin/lsof", "-a", "-p", str(record["pid"]), "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=5)
                directory = next((line[1:] for line in cwd.stdout.splitlines() if line.startswith("n")), None)
                relative = Path(marker).name
                if directory != str(APP) or relative not in record["command"].split():
                    raise RuntimeError("LEGACY_PROCESS_IDENTITY_REFUSED")
            else:
                raise RuntimeError("LEGACY_PROCESS_IDENTITY_REFUSED")
        if record:
            records[field] = safe_record(record)
    import shutil
    # Exact copies stay private. They are evidence backups, never quota rollback.
    shutil.copytree(OLD / "gateway-state", archive / "gateway-state")
    shutil.copy2(META, archive / "processes.json")
    atomic_json(archive / "summary.json", summary())
    no_active_jobs()
    for field in ("tunnel_pid", "gateway_pid", "backend_pid", "idle_sleep_guard_pid"):
        if records.get(field):
            terminate(records[field])
    atomic_json(META, {"managed_by": LABEL, "components": {}, "tunnel_url": metadata.get("tunnel_url")})
    return {"backup": str(archive), "before": json.loads((archive / "summary.json").read_text()), "after": summary()}


def install():
    private_directory(RUNTIME)
    private_directory(PLIST.parent) if not PLIST.parent.exists() else None
    if not CONTROL.exists():
        atomic_json(CONTROL, {"allow_live": False, "note": "Enable explicitly after GPU coordination; never starts an inference by itself."})
    write_lease(False)
    configuration = {"Label": LABEL, "ProgramArguments": [str(PYTHON), str(Path(__file__).resolve()), "run"],
        "WorkingDirectory": str(BASE / "runtime"), "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30, "ExitTimeOut": 330, "ProcessType": "Background", "AbandonProcessGroup": True,
        "EnvironmentVariables": {"HOME": str(Path.home()), "PATH": str(Path.home() / ".local/bin") + ":/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"},
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}
    with PLIST.open("wb") as stream:
        plistlib.dump(configuration, stream)
    os.chmod(PLIST, 0o600)
    return {"plist": str(PLIST), "label": LABEL, "allow_live": json.loads(CONTROL.read_text())["allow_live"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "takeover", "install", "run", "status", "enable-live", "pause-live"))
    args = parser.parse_args()
    private_directory(RUNTIME)
    if args.action == "preflight":
        pins = source_pins()
        print(json.dumps({"source_pins": "pass", "source_count": len(pins["sha256"]), "pool": summary(), "backend_health_no_inference": backend_health(), "deadline_utc": DEADLINE.isoformat(), "qloo_calls": 0, "model_calls": 0}, indent=2))
    elif args.action == "takeover":
        source_pins()
        release = acquire_lock(RUNTIME / "supervisor.lock", "takeover")
        try:
            print(json.dumps(takeover(), indent=2))
        finally:
            release()
    elif args.action == "install":
        source_pins()
        print(json.dumps(install(), indent=2))
    elif args.action in ("enable-live", "pause-live"):
        atomic_json(CONTROL, {"allow_live": args.action == "enable-live", "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        if args.action == "pause-live":
            write_lease(False)
        print(json.dumps({"allow_live": args.action == "enable-live", "qloo_calls": 0, "model_calls": 0}))
    elif args.action == "status":
        metadata = json.loads(META.read_text())
        print(json.dumps({"managed_by": metadata.get("managed_by"), "components": {role: {"pid": record["pid"], "identity_matches": bool(matches(record))} for role, record in metadata.get("components", {}).items()}, "tunnel_url": metadata.get("tunnel_url"), "pool": summary(), "admission": json.loads(LEASE.read_text()) if LEASE.exists() else None}, indent=2))
    else:
        release = acquire_lock(RUNTIME / "supervisor.lock", "supervisor")
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        write_lease(False)
        try:
            source_pins()
            Supervisor().loop()
        except Exception as error:
            log("supervisor_stopped", code=str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else type(error).__name__)
            raise SystemExit(1)
        finally:
            write_lease(False)
            release()


if __name__ == "__main__":
    main()
