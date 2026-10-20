"""Candidate native Hermes context for a single dedicated Director CLI worker.

Import is inert. Entering the context requires explicit execution activation.
No old driver is imported, no model server is started, no credential is exposed.
The existing guard remains the sole admission path for model execution.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
HERMES = (Path.home() / '.hermes/hermes-agent')
PROFILE = (Path.home() / '.hermes/profiles/studio')
FACTS = (Path.home() / '.hermes/installs/a9cbfd907c713e05/facts.json')
CPU_PYTHON = (Path.home() / 'Documents/code/StudioVideoLocal/.venv/bin/python')
MODEL = (Path.home() / 'Movies/StudioVideoLocal/models/qwen38-27b-orcarouter-mlx/8-bit')
URL = 'http://127.0.0.1:18080/v1'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def selected_python():
    environment = Path(json.loads(FACTS.read_text())['packages']['venv']['environment'])
    python = environment/'bin/python'
    if not python.is_file():
        raise RuntimeError('Existing native Python unavailable; no installation attempted')
    return python

class BridgeStop(BaseException):
    """Never converted into an SDK retry or product fallback."""

class ExactCPUCounter:
    def __init__(self, deadline=lambda: None):
        self.deadline = deadline
        self.cache = {}
    def __call__(self, messages):
        raw = canonical(messages)
        if len(raw) > 24000:
            raise ValueError('Messages exceed candidate byte bound')
        key = hashlib.sha256(raw).hexdigest()
        if key not in self.cache:
            deadline = self.deadline()
            remaining = 20 if deadline is None else min(20, deadline-time.monotonic())
            if remaining <= 0:
                raise BridgeStop('Active deadline exhausted before CPU count')
            environment = {k: os.environ[k] for k in ['HOME', 'PATH', 'LANG', 'TMPDIR'] if k in os.environ}
            environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', USE_TORCH='0', USE_TF='0',
                               TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([str(CPU_PYTHON), '-B', '-I', str(HERE/'cpu_counter.py')],
                                    input=raw, capture_output=True, env=environment, timeout=remaining)
            if result.returncode:
                raise BridgeStop('CPU counter failed; no approximate fallback')
            data = json.loads(result.stdout)
            if data['canonical_messages_sha256'] != key or not 0 < data['tokens'] <= 6000:
                raise BridgeStop('CPU accounting mismatch or input token bound')
            self.cache[key] = data
        return self.cache[key]['tokens']

class NativeQwenBootstrap:
    def __init__(self, receipt_dir, *, execute_authorized=False, active_seconds=120):
        if not 0 < active_seconds <= 120:
            raise ValueError('Active budget must be within (0,120] seconds')
        self.directory = Path(receipt_dir)
        self.execute_authorized = execute_authorized
        self.active_seconds = active_seconds
        self.deadline_at = None
        self.window_started_at = time.monotonic()
        self.armed = self.admitted = self.closed = False
        self.cli = self.client = None
        self.network = []
        self.runners = []
        self.logical_role = None
        self.counter = ExactCPUCounter(lambda: self.deadline_at)
        self.configs = [PROFILE/'config.yaml', (Path.home() / '.hermes/config.yaml')]
        self.config_before = {}
        self.native_sources = {str(HERMES/name): sha(HERMES/name) for name in
                               ['cli.py', 'hermes_bootstrap.py', 'agent/auxiliary_client.py']}
        self.old_handlers = {}
        self.old_environment = {}
        self.old_path = list(sys.path)
        self.real_send = None
    def _audit(self, event, args):
        if event == 'socket.connect':
            address = args[1]
            if not self.armed or self.closed or not isinstance(address, tuple) or address[:2] != ('127.0.0.1', 18080):
                raise BridgeStop('Unexpected socket route')
    def _deadline(self, signum, frame):
        raise BridgeStop('Worker or active wall deadline; no retry')
    def __enter__(self):
        if not self.execute_authorized or threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Explicit activation in a dedicated main-thread CLI worker required')
        self.config_before = {str(p): sha(p) for p in self.configs}
        sys.dont_write_bytecode = True
        sys.addaudithook(self._audit)
        values = dict(HERMES_HOME=str(PROFILE), HERMES_SUPERVISED_CHILD='1', HERMES_DISABLE_LAZY_INSTALLS='1',
                      HERMES_INTERACTIVE='0', HERMES_QUIET='1', HERMES_IGNORE_RULES='1', HERMES_DEFER_AGENT_STARTUP='0')
        for key, value in values.items():
            self.old_environment[key] = os.environ.get(key)
            os.environ[key] = value
        sys.path.insert(0, str(HERMES))
        try:
            import httpx
            self.httpx = httpx
            self.real_send = httpx.Client.send
            def bounded_send(http_client, request, *args, **kwargs):
                return self._send(http_client, request, *args, **kwargs)
            httpx.Client.send = bounded_send
            for signum in [signal.SIGTERM, signal.SIGALRM]:
                self.old_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, self._deadline)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                import hermes_bootstrap
                from hermes_cli.mcp_startup import set_mcp_server_filter
                set_mcp_server_filter('__qloo_bridge_no_mcp__')
                from cli import HermesCLI
                self.cli = HermesCLI(model=str(MODEL), provider='qwen-local', toolsets=[], max_turns=1,
                                     run_budget=120, ignore_rules=True, verbose=False)
                cli = self.cli
                cli._single_query_mode = True
                cli.streaming_enabled = False
                cli.tool_progress_mode = 'off'
                cli._fallback_model = None
                cli.prefill_messages = []
                cli.checkpoints_enabled = False
                if not cli._ensure_runtime_credentials():
                    raise BridgeStop('Native provider unavailable')
                if cli.requested_provider != 'qwen-local' or cli.model != str(MODEL) or cli.base_url.rstrip('/') != URL or cli.api_mode != 'chat_completions':
                    raise BridgeStop('Native provider route mismatch')
                if not cli._claim_active_session('cli', stderr=True):
                    raise BridgeStop('Native session admission refused')
                self.admitted = True
                from agent.auxiliary_client import resolve_provider_client
                self.client, self.actual_model = resolve_provider_client(cli.provider, model=str(MODEL),
                    explicit_base_url=cli.base_url, explicit_api_key=cli.api_key, api_mode=cli.api_mode)
                from hermes_constants import get_hermes_home
                if self.client is None or self.actual_model != str(MODEL) or str(self.client.base_url).rstrip('/') != URL or Path(get_hermes_home()).resolve() != PROFILE.resolve():
                    raise BridgeStop('Native text client/profile mismatch')
            return self
        except BaseException:
            self.close()
            raise
    def start_run(self):
        if self.deadline_at is None:
            self.deadline_at = self.window_started_at+self.active_seconds
            signal.signal(signal.SIGALRM, self._deadline)
            signal.signal(signal.SIGTERM, self._deadline)
            signal.setitimer(signal.ITIMER_REAL, max(0.001,self.deadline_at-time.monotonic()))
            self.armed = True
    def _send(self, http_client, request, *args, **kwargs):
        location = urlsplit(str(request.url))
        if not self.armed:
            if request.method == 'GET' and location.hostname == '127.0.0.1' and location.port == 18080:
                raise self.httpx.RequestError('Native metadata probe suppressed before run', request=request)
            raise BridgeStop('Unexpected preflight network')
        if request.method != 'POST' or str(request.url) != URL+'/chat/completions' or len(self.network) >= 5:
            raise BridgeStop('Unexpected route or five-call network bound')
        if self.deadline_at is None or time.monotonic() >= self.deadline_at:
            raise BridgeStop('Active deadline exhausted')
        body = json.loads(request.content)
        digest = hashlib.sha256(canonical(body.get('messages'))).hexdigest()
        if digest not in self.counter.cache or body.get('model') != str(MODEL) or body.get('max_tokens') != {'role_1_brief_analyst':450,'role_2_creative_redactor':1200,'role_3_verifier':300}.get(self.logical_role) or body.get('stream') or body.get('tools') or body.get('chat_template_kwargs') != {'enable_thinking': False}:
            raise BridgeStop('Wire/accounting contract mismatch')
        if {str(p): sha(p) for p in self.configs} != self.config_before:
            raise BridgeStop('Configuration changed before wire')
        for name, digest_value in self.counter.cache[digest]['source_hashes'].items():
            if sha(MODEL/name) != digest_value:
                raise BridgeStop('Tokenizer epoch changed before wire')
        event = {'max_output_tokens':body.get('max_tokens'),'retries':0,'run_id': getattr(self, 'application_run_id', None), 'logical_role': self.logical_role, 'messages_sha256': digest,
                 'input_tokens': self.counter.cache[digest]['tokens'], 'outcome': 'unknown'}
        self.network.append(event)
        started = time.monotonic()
        try:
            response = self.real_send(http_client, request, *args, **kwargs)
            response.read()
        except BaseException:
            raise BridgeStop('Guard request outcome unknown; stop without retry') from None
        event.update(status=response.status_code, seconds=round(time.monotonic()-started, 3),
                     response_sha256=hashlib.sha256(response.content).hexdigest())
        data = response.json()
        event.update(model=data.get('model'), usage=data.get('usage'))
        if response.status_code >= 300:
            error = data.get('error') if isinstance(data.get('error'), dict) else {}
            event.update(error_code=error.get('code'), error_type=error.get('type'), forwarded=data.get('forwarded'))
            raise BridgeStop('Guard refused or HTTP failure; no retry')
        event['outcome'] = 'response_received'
        event['finish_reasons'] = [item.get('finish_reason') for item in data.get('choices', [])]
        # Store only the public run response; mode and Qloo provenance remain in the Director bundle.
        # Retain response content locally for precise output/JSON review, never headers.
        import re
        visible = {'model': data.get('model'), 'usage': data.get('usage'),
                   'logical_role': self.logical_role,
                   'choices': [{'finish_reason': item.get('finish_reason'), 'message': item.get('message')}
                               for item in data.get('choices', [])]}
        text = json.dumps(visible, ensure_ascii=False)
        if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|Authorization\s*:\s*Bearer|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text, re.I):
            event['response_visible_not_retained'] = 'Protected material pattern'
        else:
            fd = os.open(self.directory/f'wire-visible-{len(self.network):02d}.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as handle:
                handle.write(text+'\n')
        return response
    def inject_builder(self, original_builder):
        def build(env=None, **kwargs):
            self.start_run()
            runner = original_builder(env, native_client=self.client, count_input_tokens=self.counter)
            if runner is None:
                raise RuntimeError('Guarded native provider did not produce runner')
            runner.deadline_at = self.deadline_at
            self.runners.append(runner)
            current_context = {}
            runner.context_provider = lambda role, payload: copy.deepcopy(current_context)
            def call(role, payload):
                nonlocal current_context
                self.logical_role = role
                current_context = {}
                supplied = copy.deepcopy(payload)
                effective_role = role
                if role == 'role_3_verifier':
                    for key in ['brief', 'decisions', 'evidences', 'user_constraints']:
                        if key not in supplied:
                            raise ValueError('Verifier actual full context missing')
                        current_context[key] = supplied.pop(key)
                    # Same actual objects in context once; never silently trim evidence.
                elif role not in {'role_1_brief_analyst','role_2_creative_redactor','role_3_verifier'}:
                    raise BridgeStop('Repair or unknown role is outside this received three-role run')
                try:
                    return runner(effective_role, supplied)
                finally:
                    current_context = {}
                    self.logical_role = None
            return call
        return build
    def close(self):
        if self.closed:
            return
        self.closed = True
        self.armed = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        released = False
        release_error = None
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            if self.client is not None:
                with contextlib.suppress(BaseException):
                    self.client.close()
            if self.admitted:
                try:
                    self.cli._release_active_session()
                    self.admitted = False
                    released = True
                except BaseException as exc:
                    release_error = type(exc).__name__
        after = {str(p): sha(p) for p in self.configs}
        if self.real_send is not None:
            self.httpx.Client.send = self.real_send
        for signum, old in self.old_handlers.items():
            signal.signal(signum, old)
        for key, old in self.old_environment.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        sys.path[:] = self.old_path
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        report = {'active_seconds_budget':self.active_seconds,'native_window_elapsed_seconds':round(time.monotonic()-self.window_started_at,3),
                  'native_setup_time_ms':getattr(self,'native_setup_time_ms',None),'run_id': getattr(self, 'application_run_id', None), 'native_session_released': released, 'config_hashes_before': self.config_before,
                  'config_hashes_after': after, 'configurations_unchanged': after == self.config_before,
                  'native_session_release_error': release_error,
                  'native_source_hashes': self.native_sources,
                  'network_calls': self.network, 'runner_receipts': [r.receipts for r in self.runners],
                  'cpu_accounting': self.counter.cache, 'cloud_calls': 0, 'qloo_api_calls_in_this_worker': 0}
        fd = os.open(self.directory/'native-receipt.json', os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        if after != self.config_before:
            raise BridgeStop('Configuration epoch changed; no restoration of another owner files')
        if release_error is not None:
            raise BridgeStop('Native session release not confirmed; worker stops')
    def __exit__(self, *exc):
        self.close()
