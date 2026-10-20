"""Candidate entrypoint: inert preflight or one explicitly activated supervised run.

No inference is performed by --preflight. The live branch is prepared for the
owner's later authorized test. It has not been executed by this preparation.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from native_bootstrap import (ExactCPUCounter, NativeQwenBootstrap, BridgeStop,
                              CPU_PYTHON, HERMES, MODEL, selected_python, sha)

HERE = Path(__file__).resolve().parent
DEFAULT_PROJECT = HERE.parent

def source_manifest(project):
    return {name: sha(project/name) for name in ['cultural_launch_director.py', 'guarded_qwen_runner.py']}

def preflight(project, probe_messages=None):
    """Read source and run only the CPU tokenizer; no native session/client built."""
    tree = ast.parse((project/'cultural_launch_director.py').read_text())
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    builder = functions['build_authorized_llm_runner']
    injection_names = [a.arg for a in builder.args.kwonlyargs]
    if not {'native_client', 'count_input_tokens'} <= set(injection_names):
        raise ValueError('Current Director builder injection contract differs')
    messages = json.loads(Path(probe_messages).read_text()) if probe_messages else [
        {'role': 'system', 'content': 'CPU counting probe only.'}, {'role': 'user', 'content': 'Public preflight.'}]
    counter = ExactCPUCounter()
    tokens = counter(messages)
    return {'status': 'OFFLINE_PREFLIGHT_ONLY', 'at': datetime.now(timezone.utc).isoformat(),
            'project': str(project), 'source_sha256': source_manifest(project),
            'native_python': str(selected_python()), 'cpu_python': str(CPU_PYTHON),
            'native_helper': str(HERMES/'agent/auxiliary_client.py'),
            'builder_injection_contract': injection_names,
            'cpu_probe_input_tokens': tokens, 'cpu_probe_accounting': counter.cache,
            'native_session_created': False, 'native_client_created': False,
            'model_calls': 0, 'qloo_calls': 0, 'new_sdks': 0,
            'next_step': 'Owner reviews hashes, then may explicitly activate a later run on the stable received product.'}

def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=DEFAULT_PROJECT)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--probe-messages', type=Path)
    parser.add_argument('--run-json', action='store_true')
    parser.add_argument('--execute-authorized', action='store_true')
    parser.add_argument('--expected-director-sha256')
    parser.add_argument('--expected-runner-sha256')
    parser.add_argument('--active-seconds', type=float, default=120)
    parser.add_argument('--receipt-root', type=Path, default=HERE/'runs')
    parser.add_argument('--_worker-dir', type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()

def verify_sources(args):
    manifest = source_manifest(args.project)
    expected = {'cultural_launch_director.py': args.expected_director_sha256,
                'guarded_qwen_runner.py': args.expected_runner_sha256}
    if manifest != expected:
        raise ValueError('Stable received source hashes are required and must match')
    return manifest

def worker(args, data):
    directory = args._worker_dir
    if not (directory/'controller-claim.json').is_file():
        raise ValueError('Supervised controller claim required')
    claim = json.loads((directory/'controller-claim.json').read_text())
    if claim['bridge_entry_sha256'] != sha(__file__) or claim['bootstrap_sha256'] != sha(HERE/'native_bootstrap.py') or claim['counter_sha256'] != sha(HERE/'cpu_counter.py'):
        raise ValueError('Bridge source epoch changed after supervision began')
    fd = os.open(directory/'worker-claim.json', os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    os.close(fd)
    verify_sources(args)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.project))
    spec = importlib.util.spec_from_file_location('qloo_received_director', args.project/'cultural_launch_director.py')
    director = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(director)
    request=director.normalize_run_request(json.loads(data))
    prepared=director.preflight_run_request(request)
    if prepared['phase']!='ready' or request['llm_call_limit']==0:
        director.build_authorized_llm_runner=lambda *a,**k: None
        old_stdin=sys.stdin
        try:
            sys.stdin=io.StringIO(data.decode())
            result=director._cli_main(['--run-json'])
            (directory/'native-receipt.json').write_text(json.dumps({'run_id':request['explicit_run_id'],
                'native_session_created':False,'native_session_released':True,'release_not_required':True,
                'network_calls':[],'runner_receipts':[],'cloud_calls':0,'qloo_api_calls_in_this_worker':0,
                'reason':'pre_model_gate_or_zero_model_budget'})+'\n')
            return result
        finally:
            sys.stdin=old_stdin
    original = director.build_authorized_llm_runner
    original_stdin = sys.stdin
    os.environ['DIRECTOR_ENABLE_LIVE_LLM'] = '1'
    os.environ['DIRECTOR_LLM_PROVIDER'] = 'guarded_qwen_18080'
    try:
        with NativeQwenBootstrap(directory, execute_authorized=True, active_seconds=args.active_seconds) as bridge:
            bridge.application_run_id = json.loads(data)["explicit_run_id"]
            injected = bridge.inject_builder(original)
            def qualification_builder(env=None, **kwargs):
                native_runner = injected(env, **kwargs)
                seen = set()
                def main_roles_only(role, payload):
                    if role not in {'role_1_brief_analyst', 'role_2_creative_redactor', 'role_3_verifier'} or role in seen:
                        raise BridgeStop('Qualification stops before repair or duplicate role; no extra inference authorized')
                    seen.add(role)
                    return native_runner(role, payload)
                return main_roles_only
            director.build_authorized_llm_runner = qualification_builder
            setup_ms=max(0,int((time.monotonic()-bridge.window_started_at)*1000))
            request['active_time_already_used_ms']+=setup_ms
            if request['active_time_already_used_ms']>=request['active_time_limit_ms']:
                raise BridgeStop('Active budget exhausted during native admission; no inference')
            bridge.native_setup_time_ms=setup_ms
            sys.stdin = io.StringIO(json.dumps(request,ensure_ascii=False))
            return director._cli_main(['--run-json'])
    finally:
        director.build_authorized_llm_runner = original
        sys.stdin = original_stdin

def supervise(args, data):
    manifest = verify_sources(args)
    payload=json.loads(data)
    elapsed=payload.get('active_time_already_used_ms',0); limit=payload.get('active_time_limit_ms',120000)
    if isinstance(elapsed,bool) or not isinstance(elapsed,int) or not isinstance(limit,int) or not 0<=elapsed<limit<=120000:
        raise ValueError('Explicit active time ledger invalid or exhausted')
    args.active_seconds=min(args.active_seconds,(limit-elapsed)/1000)
    application_run_id = str(json.loads(data).get("explicit_run_id") or "")
    import re
    if not re.fullmatch(r"run-[a-z0-9_-]{4,64}", application_run_id, flags=re.I):
        raise ValueError("Preallocated application run id required")
    directory = args.receipt_root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, mode=0o700)
    (directory/'controller-claim.json').write_text(json.dumps({'pid': os.getpid(), 'run_id': application_run_id, 'source_sha256': manifest,
        'bridge_entry_sha256': sha(__file__), 'bootstrap_sha256': sha(HERE/'native_bootstrap.py'),
        'counter_sha256': sha(HERE/'cpu_counter.py'), 'hard_wall_seconds': 150, 'automatic_retries': 0,'active_time_already_used_ms':elapsed,'native_remaining_seconds':args.active_seconds})+'\n')
    environment = {k: os.environ[k] for k in ['HOME', 'PATH', 'LANG', 'TMPDIR'] if k in os.environ}
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    command = [str(selected_python()), '-B', str(Path(__file__).resolve()), '--project', str(args.project),
               '--run-json', '--execute-authorized', '--expected-director-sha256', args.expected_director_sha256,
               '--expected-runner-sha256', args.expected_runner_sha256, '--active-seconds', str(args.active_seconds),
               '--_worker-dir', str(directory)]
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=directory, env=environment)
    try:
        stdout, stderr = process.communicate(input=data, timeout=150)
        result = {'worker_pid': process.pid, 'exit_code': process.returncode, 'hard_wall_timeout': False,
                  'wall_seconds': round(time.monotonic()-started, 3), 'automatic_retries': 0}
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        result = {'worker_pid': process.pid, 'hard_wall_timeout': True, 'outcome': 'unknown_no_retry',
                  'wall_seconds': round(time.monotonic()-started, 3), 'automatic_retries': 0}
    result['run_id'] = application_run_id
    (directory/'controller-receipt.json').write_text(json.dumps(result, indent=2)+'\n')
    if result['hard_wall_timeout'] or process.returncode:
        # Error text is the worker's safe static category, never a raw SDK exception.
        sys.stderr.write(json.dumps({'error': 'NATIVE_DIRECTOR_WORKER_FAILED', 'receipt_dir': str(directory),
                                     'exit_code': process.returncode, 'hard_wall_timeout': result['hard_wall_timeout']})+'\n')
        return 1
    if len(stdout) > 2*1024*1024:
        raise ValueError('Output bundle exceeds 2 MiB')
    json.loads(stdout)
    sys.stdout.buffer.write(stdout)
    return 0

def main():
    args = parse()
    if not 0 < args.active_seconds <= 120:
        raise ValueError('Active seconds must be in (0,120]')
    if args.preflight:
        if args.execute_authorized or args.run_json or args._worker_dir:
            raise ValueError('Preflight cannot activate a run')
        print(json.dumps(preflight(args.project, args.probe_messages), ensure_ascii=False, indent=2))
        return 0
    if not args.run_json or not args.execute_authorized:
        raise ValueError('Use --preflight, or explicitly activated --run-json after owner review')
    data = sys.stdin.buffer.read(1024*1024+1)
    if len(data) > 1024*1024 or not isinstance(json.loads(data), dict):
        raise ValueError('Input request must be an object within 1 MiB')
    if args._worker_dir:
        return worker(args, data)
    return supervise(args, data)

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, BridgeStop) as exc:
        sys.stderr.write(json.dumps({'error': type(exc).__name__, 'detail': 'Bridge stopped without fallback or automatic retry'})+'\n')
        raise SystemExit(1)
