"""R03 advisory-only executor. R01 contracts and R02 costs remain authoritative.

The native Windows deny-read boundary has NOT been certified. The Codex backend
therefore fails closed before reservation/dispatch. There is no CLI/config flag
that bypasses this gate. Fake execution evaluates data only and starts no tools.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import threading
import time

import supervision
import supervision_calls as calls
import supervision_contracts as contracts
import supervision_ledger as queue
import supervision_scheduler as scheduler
from supervision_snapshot import FIXED, ROOTS

METHOD = Path(__file__).parent / 'method/SUPERVISOR_REVIEW.md'


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(value): raise ValueError('Non-finite JSON value')
    try: return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, UnicodeError) as exc: raise ValueError('Invalid JSON encoding/depth') from exc


def _hash(raw): return hashlib.sha256(raw).hexdigest()


def _safe_source(relative):
    parts = PurePosixPath(relative).parts
    forbidden = {'.git', '.codex', '.ssh', '.aws', 'auth.json', 'credentials.json',
                 'secrets.json', 'tokens.json', 'token.json', 'config.toml', 'id_rsa', 'id_ed25519'}
    if (not parts or relative.startswith('/') or '\\' in relative or ':' in relative
            or any(p in {'', '.', '..'} or p.endswith((' ', '.')) or '\x00' in p
                   or p.casefold() in forbidden or p.casefold().startswith('.env') for p in relative.split('/'))
            or Path(relative).suffix.casefold() in {'.pem', '.key', '.pfx', '.p12'}
            or (relative not in FIXED and parts[0] not in ROOTS)):
        raise ValueError('SOURCE_OUTSIDE_REVIEW_ALLOWLIST')


def review_data(record):
    """Only frozen bodies; never resolve or re-read their original host paths."""
    event, snapshot = record['event'], record['snapshot']
    contracts.validate_event(event, snapshot)
    manifest = [s for s in snapshot['source_manifest'] if s['scope'] == 'PROJECT']
    for source in manifest: _safe_source(source['path'])
    sources = []
    bodies = {s['path']: s['content'] for s in snapshot['sources'] if s['scope'] == 'PROJECT'}
    for index, source in enumerate(manifest):
        text = bodies.get(source['path'])
        if text is None: continue
        raw = text.encode('utf8')
        if len(raw) != source['captured_bytes'] or (not source['truncated'] and _hash(raw) != source['sha256']):
            raise ValueError('FROZEN_BODY_HASH_MISMATCH')
        sources.append({**source, 'file': f'data/source-{index:04d}.txt', 'content': text})
    return copy.deepcopy({'schema_version': 1, 'event': event,
        'input_snapshot_sha256': snapshot['input_snapshot_sha256'],
        'focus': snapshot['focus'], 'obligation_ids': snapshot['obligation_ids'],
        'route_summary': snapshot['route_summary'], 'claim_status': snapshot['claim_status'],
        'missing': [s for s in snapshot['missing'] if s['scope'] == 'PROJECT'],
        'sources': sources, 'source_manifest': manifest,
        'trust': 'UNVERIFIED_RESEARCH_DATA; NO NEW PROOF OR ROUTE AUTHORITY'})


def fake_proposal(data):
    """Deterministic transport fixture; never a mathematical judgement."""
    source = next((s for s in data['sources'] if s['evidence_eligible'] and not s['truncated']
                   and s['captured_bytes']), None)
    if source is None: raise ValueError('INSUFFICIENT_EVIDENCE')
    event = data['event']
    return {'schema_version': 1, 'event_id': event['event_id'], 'project_id': event['project_id'],
        'goal_anchor_id': event['focus']['anchor_id'], 'input_snapshot_sha256': data['input_snapshot_sha256'],
        'action': 'KEEP_GUIDE', 'evidence_refs': [{'path': source['path'], 'sha256': source['sha256'], 'scope': 'SUPPORT'}],
        'reason': 'OFFLINE FAKE: transport acceptance only. No scientific conclusion or proof upgrade.',
        'next_obligation_id': None, 'next_task': 'Continue reviewing the unchanged frozen research obligations.',
        'success_criterion': 'Check evidence under the original assumptions and quantifiers.',
        'falsification_criterion': 'Require a reproducible counterexample under the frozen security model.',
        'requires_operator_approval': False, 'guide_notes': ['Offline fixture; do not apply as research guidance.']}


@dataclass(frozen=True)
class ExecutionResult:
    raw_output: str = ''
    log: str = ''
    exit_code: int | None = 0
    elapsed_seconds: float = 0
    failure: str | None = None
    outcome_known: bool = True


class FakeSupervisorExecutor:
    backend = 'fake'

    def __init__(self, response=None, *, failure=None, outcome_known=True):
        self.response, self.failure, self.outcome_known = response, failure, outcome_known
        self.calls = 0

    def preflight(self):
        return {'backend': self.backend, 'compatible': True, 'isolation_verified': False,
                'mode': 'IN_PROCESS_DATA_ONLY_NO_TOOLS'}

    def argv(self, workspace, model_route): return ['offline-fake-supervisor', 'R03', contracts.canonical_hash(model_route)]

    def run(self, workspace, data, model_route, seconds, limit):
        self.calls += 1
        raw = self.response(data) if callable(self.response) else self.response
        if raw is None: raw = json.dumps(fake_proposal(data), ensure_ascii=False)
        return ExecutionResult(raw, 'Offline fake provider; no subprocess or model.',
            1 if self.failure else 0, .01, self.failure, self.outcome_known)


def inspect_cli(binary='codex'):
    """Metadata only. Capability flags are necessary, never isolation proof."""
    executable = shutil.which(binary)
    if not executable: return {'compatible': False, 'isolation_verified': False, 'reason': 'CLI_NOT_FOUND'}
    try:
        version = subprocess.run([executable, '--version'], capture_output=True, timeout=10, check=True)
        help_result = subprocess.run([executable, 'exec', '--help'], capture_output=True, timeout=10, check=True)
        help_text = help_result.stdout.decode('utf8', errors='replace')
        required = ('read-only', '--output-schema', '--json', '--ephemeral', '--ignore-user-config',
                    '--ignore-rules', '--cd', '--skip-git-repo-check')
        compatible = all(flag in help_text for flag in required)
        return {'compatible': compatible, 'isolation_verified': False, 'binary': executable,
            'binary_sha256': _hash(Path(executable).read_bytes()),
            'version': version.stdout.decode('utf8', errors='replace').strip()[:200],
            'help_sha256': _hash(help_result.stdout),
            'reason': 'BLOCKED_UNVERIFIED_OS_SANDBOX' if compatible else 'CLI_CAPABILITY_MISSING'}
    except subprocess.TimeoutExpired:
        return {'compatible': False, 'isolation_verified': False, 'reason': 'CLI_PREFLIGHT_TIMEOUT'}
    except PermissionError:
        return {'compatible': False, 'isolation_verified': False, 'reason': 'CLI_PERMISSION_DENIED'}
    except (OSError, subprocess.CalledProcessError):
        return {'compatible': False, 'isolation_verified': False, 'reason': 'CLI_PREFLIGHT_FAILED'}


def _run_process(argv, cwd, prompt, seconds, limit, env):
    """Bounded transport; kill the whole process tree on timeout/output overflow.

    No caller may mistake a killed process or lost final result for a safe retry.
    This helper is exercised with offline child programs, never paid models.
    """
    started = time.monotonic()
    from supervision_process import ProcessTree
    try:
        tree = ProcessTree()
        process = tree.start(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return ExecutionResult(failure='SPAWN_FAILED', exit_code=None,
            elapsed_seconds=time.monotonic() - started, outcome_known=False)
    buffers = [bytearray(), bytearray()]; overflow = threading.Event()
    def read(stream, buffer):
        try:
            while chunk := stream.read(4096):
                available = max(0, limit - len(buffer))
                buffer.extend(chunk[:available])
                if len(chunk) > available: overflow.set()
        finally: stream.close()
    def write():
        try: process.stdin.write(prompt.encode('utf8')); process.stdin.flush()
        except (BrokenPipeError, OSError): pass
        finally: process.stdin.close()
    threads = [threading.Thread(target=read, args=(stream, buffer), daemon=True)
               for stream, buffer in zip((process.stdout, process.stderr), buffers)]
    threads.append(threading.Thread(target=write, daemon=True))
    failure = None
    started_threads = []
    try:
        for thread in threads:
            thread.start(); started_threads.append(thread)
        while process.poll() is None:
            if overflow.is_set() or time.monotonic() - started >= seconds:
                failure = 'OUTPUT_LIMIT' if overflow.is_set() else 'TIMEOUT'
                break
            time.sleep(.01)
    finally:
        # Also close on interrupts/startup failures, and after early parent exit.
        tree.close()
        for thread in started_threads: thread.join(timeout=2)
        if not threads[-1].is_alive() and not process.stdin.closed: process.stdin.close()
    if overflow.is_set(): failure = failure or 'OUTPUT_LIMIT'
    if any(thread.is_alive() for thread in threads): failure = failure or 'PIPE_NOT_CLOSED'
    raw, log = (bytes(b) for b in buffers)
    try: output, diagnostic = raw.decode('utf8'), log.decode('utf8')
    except UnicodeError:
        return ExecutionResult(raw.decode('utf8', errors='replace'), log.decode('utf8', errors='replace'),
            process.returncode, time.monotonic() - started, 'INVALID_UTF8', not bool(failure))
    return ExecutionResult(output, diagnostic, process.returncode, time.monotonic() - started,
        failure or ('EXIT_NONZERO' if process.returncode else None), not bool(failure))


class CodexSupervisorExecutor:
    backend = 'codex'

    def __init__(self, binary='codex'): self.binary = binary

    def preflight(self):
        return {**inspect_cli(self.binary), 'backend': self.backend}

    @staticmethod
    def _require_isolation():
        # Neither read-only flags, chmod, help output nor a user Boolean certify
        # host/other-project/credential deny-read and tool-network isolation.
        raise ValueError('BLOCKED_UNVERIFIED_OS_SANDBOX')

    def argv(self, workspace, model_route):
        self._require_isolation()
        return self._argv(workspace, model_route)

    def _argv(self, workspace, model_route):
        # Prepared transport for a future certified OS adapter. No writable output
        # path, user config/rules, sessions, additional roots or shell invocation.
        return [self.binary, 'exec', '--sandbox', 'read-only', '--ignore-user-config', '--ignore-rules',
            '--ephemeral', '--skip-git-repo-check', '--json', '--output-schema', str(workspace / 'proposal_schema.json'),
            '--cd', str(workspace), '--model', model_route['model'],
            '-c', 'model_reasoning_effort=' + json.dumps(model_route['effort']),
            '-c', 'web_search="disabled"', '-c', 'features.shell_tool=false',
            '-c', 'features.unified_exec=false', '-c', 'features.multi_agent=false',
            '-c', 'features.apps=false', '-c', 'features.plugins=false', '-c', 'features.hooks=false', '-']

    def run(self, workspace, data, model_route, seconds, limit):
        self._require_isolation()
        # Deliberately unreachable until an OS adapter is certified. Never accept
        # an environment/config override that would silently weaken this gate.
        prompt = METHOD.read_text(encoding='utf8') + '\nREVIEW_DATA_JSON:\n' + json.dumps(data, ensure_ascii=False)
        env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC'}}
        result = _run_process(self._argv(workspace, model_route), workspace, prompt, seconds, limit, env)
        if result.failure: return result
        try:
            messages = [strict_json(line) for line in result.raw_output.splitlines() if line.strip()]
            final = [m['item']['text'] for m in messages if m.get('type') == 'item.completed'
                     and isinstance(m.get('item'), dict) and m['item'].get('type') == 'agent_message']
            if len(final) != 1: raise ValueError('Missing/ambiguous final response')
        except (ValueError, KeyError, TypeError, AttributeError):
            return ExecutionResult(result.raw_output, result.log, result.exit_code,
                result.elapsed_seconds, 'MISSING_FINAL_OUTPUT', False)
        return ExecutionResult(final[0], result.log, result.exit_code, result.elapsed_seconds)


def _audit(controller, project, event_id, payload):
    # Parent-owned, separate from research logs/checkpoints. No model instructions
    # are executed and no provider argv/environment (possibly secret) is persisted.
    payload = {'schema_version': 1, 'event_id': event_id, 'advisory_only': True, **payload}
    key = contracts.canonical_hash(payload)
    queue._write_immutable(queue._event_path(controller, project, key, 'executor-audits'), payload)


def _validate_output(raw, record, data):
    proposal = contracts.validate_proposal(strict_json(raw), record['event'], record['snapshot'])
    delivered = {s['path']: s for s in data['sources'] if s['evidence_eligible'] and not s['truncated']}
    if any(ref['path'] not in delivered for ref in proposal['evidence_refs']):
        raise ValueError('Evidence was not delivered to the supervisor')
    # Conservative rejection of explicit operational payloads; this is not a
    # semantic proof checker. All remaining prose stays unverified advice.
    text = '\n'.join(proposal[k] for k in ('reason', 'next_task', 'success_criterion', 'falsification_criterion'))
    text += '\n' + '\n'.join(proposal['guide_notes'])
    forbidden = (r'https?://|```|`|\$\(|&&|\|\|',
        r'\bgit\s+(?:reset|clean|checkout|restore|commit|push)\b',
        r'\b(?:curl|wget|powershell|cmd\.exe|bash|invoke-expression|start-process)\b',
        r'\b(?:PROVED|THEOREM_ACCEPTED|APPROVE_THEOREM|FORMALLY_VERIFIED)\b',
        r'(?:overwrite|rewrite|edit|modify|replace|relax|change|weaken|修改|改写|放宽|覆盖|删除).{0,60}'
        r'(?:GOAL|security model|安全模型|冻结目标|证明义务|original.{0,20}requirement)',
        r'(?:reset|replenish|重置|补充).{0,30}(?:budget|预算)')
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in forbidden):
        raise ValueError('Explicit operational/goal/proof payload is forbidden')
    return proposal


def _replay(controller, project, event_id, saved, record):
    receipt = calls._read_completion(controller, project, event_id, saved)
    if receipt is None:
        return {'status': 'BLOCKED', 'reason': calls.recovery_info(controller, project, event_id, saved)['call_phase'],
                'automatic_retry_allowed': False, 'advisory_only': True}
    result = calls.recover_completion(controller, project, event_id, saved['claim_token'])
    proposal = None
    if receipt['state'] == 'PROPOSED':
        # Do not blindly elevate legacy/raw R02 receipts to validated proposals.
        try:
            proposal = _validate_output(receipt['raw_output'], record, review_data(record))
            metadata = strict_json(receipt['log'])
            if not isinstance(metadata, dict) or metadata.get('executor_protocol') != 'R03':
                raise ValueError('Receipt is not R03 validated output')
        except ValueError:
            return {**result, 'status': 'BLOCKED', 'reason': 'RECEIPT_NOT_ACCEPTED_AS_R03_PROPOSAL',
                    'replayed': True, 'advisory_only': True, 'proposal': None, 'automatic_retry_allowed': False}
    with scheduler._locks(controller, project, execution=True):
        if proposal is not None and not scheduler._event_guard(controller, project, record)['claim_allowed']:
            return {**result, 'status': 'BLOCKED', 'reason': 'CURRENT_BINDING_OR_RESTRICTION_CHANGED',
                    'replayed': True, 'advisory_only': True, 'proposal': None, 'automatic_retry_allowed': False}
        return {**result, 'status': 'COMPLETED', 'replayed': True, 'advisory_only': True,
                'proposal': proposal, 'automatic_retry_allowed': False}


def execute(controller, project, event_id, *, executor=None, dry_run=False):
    """Explicit one-event consumer. Runner remains R02 queue-only in this round."""
    executor = executor or FakeSupervisorExecutor()
    if dry_run:
        record = queue.read_event(controller, project, event_id)
        view = scheduler.pending(controller, project)
        _, reservations = queue.reservations(controller, project)
    else:
        with scheduler._locks(controller, project, execution=True):
            # Missing frozen input must retain the R02 durable path/hash diagnostic.
            record = queue.read_for_claim(controller, project, event_id)
            view = scheduler.pending(controller, project)
            _, reservations = queue.reservations(controller, project)
    saved = reservations.get(event_id)
    if dry_run:
        return {'status': 'DRY_RUN', 'event_id': event_id, 'backend': executor.backend,
            'enabled': view['enabled'], 'advisory_only': True, 'automatic_retry_allowed': False,
            'call_phase': calls.recovery_info(controller, project, event_id, saved)['call_phase']}
    if saved: return _replay(controller, project, event_id, saved, record)
    if not view['enabled']: return {'status': 'BLOCKED', 'reason': 'DISABLED', 'advisory_only': True}
    try:
        data = review_data(record)
        if record['snapshot']['defaults']['max_snapshot_bytes'] < 8192: raise ValueError('RECEIPT_BOUND_TOO_SMALL')
        fake_proposal(data)  # Evidence sufficiency, without fabricating any reference.
    except ValueError as exc:
        _audit(controller, project, event_id, {'status': 'FAILED', 'reason': str(exc)[:120], 'stage': 'INPUT'})
        return {'status': 'FAILED', 'reason': 'INPUT_REJECTED', 'advisory_only': True}
    capability = executor.preflight()
    if not capability.get('compatible') or (executor.backend == 'codex' and not capability.get('isolation_verified')):
        _audit(controller, project, event_id, {'status': 'BLOCKED', 'stage': 'PREFLIGHT', 'capability': capability})
        return {'status': 'BLOCKED', 'reason': capability.get('reason', 'EXECUTOR_UNAVAILABLE'), 'advisory_only': True}
    # A disposable directory outside ALL controller projects; original filenames
    # (especially AGENTS/.codex) never become automatically loaded instructions.
    with tempfile.TemporaryDirectory(prefix='crc-review-') as directory:
        workspace = Path(directory)
        if workspace.resolve().is_relative_to(Path(controller).resolve()):
            raise ValueError('Review workspace must be outside the controller')
        for source in data['sources']:
            path = workspace / source['file']; path.parent.mkdir(exist_ok=True)
            path.write_text(source['content'], encoding='utf8', newline='')
            if _hash(path.read_bytes()) != _hash(source['content'].encode('utf8')):
                raise ValueError('Review copy changed')
        (workspace / 'REVIEW_INPUT.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
        (workspace / 'proposal_schema.json').write_text(json.dumps(contracts.proposal_schema()), encoding='utf8')
        claim = scheduler.claim_event(controller, project, event_id)
        if not claim['claimed']: return {'status': 'BLOCKED', **claim, 'advisory_only': True}
        token = claim['claim_token']
        _, reserved = queue.reservations(controller, project)
        model_route = reserved[event_id]['model_route']
        try: argv = executor.argv(workspace, model_route)
        except ValueError:
            scheduler.finish_claim(controller, project, event_id, token, state='FAILED', elapsed_seconds=0)
            return {'status': 'BLOCKED', 'reason': 'EXECUTOR_PREPARATION_FAILED', 'advisory_only': True}
        dispatch = calls.mark_dispatched(controller, project, event_id, token, argv=argv)
        if not dispatch['dispatch_allowed']: return {'status': 'BLOCKED', **dispatch, 'advisory_only': True}
        bound = record['snapshot']['defaults']['max_snapshot_bytes']
        limit = min(32768, (bound - 3000) // 8)
        result = executor.run(workspace, data, model_route, claim['max_seconds'], limit)
    raw_bytes = result.raw_output.encode('utf8'); log_bytes = result.log.encode('utf8')
    overflow = len(raw_bytes) > limit or len(log_bytes) > limit
    raw = raw_bytes[:limit].decode('utf8', errors='ignore')
    log = log_bytes[:min(limit // 4, 4096)].decode('utf8', errors='ignore')
    state, reason, proposal = 'FAILED', result.failure, None
    if not result.outcome_known:
        _audit(controller, project, event_id, {'status': 'UNKNOWN_EXTERNAL_OUTCOME', 'reason': reason,
            'backend': executor.backend, 'input_snapshot_sha256': record['snapshot']['input_snapshot_sha256'],
            'output_sha256': _hash(raw_bytes), 'output_truncated': overflow, 'diagnostic': log,
            'model_route': model_route, 'elapsed_seconds': result.elapsed_seconds, 'exit_code': result.exit_code})
        return {'status': 'BLOCKED', 'reason': 'UNKNOWN_EXTERNAL_OUTCOME',
                'automatic_retry_allowed': False, 'advisory_only': True}
    if overflow: reason = 'OUTPUT_LIMIT'
    elif result.exit_code != 0: reason = reason or 'EXIT_NONZERO'
    elif not reason:
        try:
            proposal = _validate_output(raw, record, data)
            state, reason = 'PROPOSED', 'VALIDATED_STRUCTURE_REQUIRES_CURRENT_GUARD'
        except ValueError:
            state, reason = 'REJECTED', 'INVALID_PROPOSAL'
    metadata = {'executor_protocol': 'R03', 'backend': executor.backend, 'capability': capability,
        'model': model_route['model'], 'effort': model_route['effort'], 'exit_code': result.exit_code,
        'elapsed_seconds': result.elapsed_seconds, 'snapshot_hash': record['snapshot']['input_snapshot_sha256'],
        'output_hash': _hash(raw_bytes), 'output_truncated': overflow, 'reason': reason,
        'diagnostic': log, 'advisory_only': True, 'proof_authority': False}
    completed = calls.save_completion(controller, project, event_id, token, state=state,
        elapsed_seconds=result.elapsed_seconds, raw_output=raw, log=json.dumps(metadata, ensure_ascii=False),
        acceptance_guard=lambda: scheduler._event_guard(controller, project, record)['claim_allowed'])
    state = completed['state']
    if state == 'CONFLICT': reason = 'CURRENT_BINDING_OR_RESTRICTION_CHANGED'
    elif state == 'PROPOSED': reason = 'VALIDATED_ADVISORY'
    return {**completed, 'status': 'COMPLETED', 'reason': reason, 'advisory_only': True,
            'proposal': proposal if state == 'PROPOSED' else None, 'automatic_retry_allowed': False}
