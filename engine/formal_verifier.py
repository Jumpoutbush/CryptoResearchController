"""Run locally installed Lean against pinned sources; require a separate scope audit."""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import configuration
from research_quality import hash_file, local_file
from .common import policy, stamp, object_hash


def source_bindings(project, workspace):
    result = {}
    for path in workspace.rglob('*'):
        if not path.is_file(): continue
        if path.is_symlink(): raise ValueError('Symlink proof sources are not accepted')
        if path.suffix in {'.lean', '.toml', '.olean', '.ilean'} or path.name in {'lean-toolchain', 'lake-manifest.json'}:
            result[path.relative_to(project).as_posix()] = hash_file(path)
    return result


def run(project, claim_id, relative, declaration):
    from .claim_graph import get, record_tool
    item = get(project, claim_id)
    proof = local_file(project, relative, roots={'proofs'})
    workspace = (project / 'proofs/lean').resolve()
    proof.relative_to(workspace)
    if proof.suffix != '.lean' or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*', declaration):
        raise ValueError('Need a Lean source and a plain qualified declaration name')
    receipt = {'schema_version': 1, 'claim_id': claim_id, 'claim_revision': item['revision'],
        'claim_sha256': item['spec_sha256'], 'proof_file': relative, 'declaration': declaration,
        'at': stamp(), 'status': 'NOT_RUN', 'source_bindings': {}, 'statement_match': 'NOT_CHECKED'}
    elan = shutil.which('elan')
    if not elan:
        receipt.update(status='UNAVAILABLE', reason='elan not in PATH; no tool was downloaded')
        record_tool(project, claim_id, 'formal_receipt', receipt); return receipt
    toolchain = workspace / 'lean-toolchain'; manifest = workspace / 'lake-manifest.json'
    if not toolchain.is_file() or not manifest.is_file():
        raise ValueError('Need an existing pinned Lean workspace with lean-toolchain and lake-manifest.json')
    version_pin = toolchain.read_text(encoding='utf8').strip()
    if not re.fullmatch(r'leanprover/lean4:v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version_pin):
        raise ValueError('Lean toolchain must pin an exact version; floating stable/nightly is not accepted')
    bindings = source_bindings(project, workspace)
    for rel in bindings:
        if rel.endswith('.lean') and re.search(r'\b(sorry|admit|sorryAx)\b', (project / rel).read_text(encoding='utf-8-sig')):
            raise ValueError('Unfinished proof marker in pinned Lean sources: ' + rel)
    receipt['source_bindings'] = bindings
    logdir = configuration.ROOT / 'logs' / configuration.project_id(project) / 'formal'
    logdir.mkdir(parents=True, exist_ok=True)
    label = str(time.time_ns()); output = logdir / (label + '.log')
    # No lake update/cache fetch/build/install command is issued here. A missing local
    # toolchain/package remains a failed check. elan run has no --install flag.
    env = os.environ.copy()
    receipt['environment'] = {'LEAN_PATH': env.get('LEAN_PATH', ''), 'toolchain': version_pin}
    prefix = [elan, 'run', version_pin, 'lake']
    timeout = policy(project)['verifier_timeout_seconds']
    audit_file = None
    try:
        try:
            version = subprocess.run([*prefix, 'env', 'lean', '--version'], cwd=workspace, env=env,
                capture_output=True, text=True, encoding='utf8', errors='replace', timeout=min(timeout, 15))
        except (OSError, subprocess.TimeoutExpired) as exc:
            receipt.update(status='UNAVAILABLE', reason=type(exc).__name__)
            record_tool(project, claim_id, 'formal_receipt', receipt); return receipt
        receipt['tool_version'] = version.stdout.strip()
        if version.returncode:
            receipt.update(status='UNAVAILABLE', reason=version.stderr[-2000:])
            record_tool(project, claim_id, 'formal_receipt', receipt); return receipt
        # Inspect the actual target, including its axioms, in the same checked file.
        fd, name = tempfile.mkstemp(prefix='ControllerAudit_', suffix='.lean', dir=proof.parent)
        audit_file = Path(name)
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            stream.write(proof.read_text(encoding='utf-8-sig'))
            stream.write('\n#print axioms ' + declaration + '\n#check @' + declaration + '\n')
        argv = [*prefix, 'env', 'lean', str(audit_file.relative_to(workspace))]
        receipt['argv'] = argv
        started = time.monotonic()
        with output.open('wb') as stream:
            process = subprocess.Popen(argv, cwd=workspace, env=env, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=(os.name != 'nt'),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0))
            try: code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                from runner_core import kill_process_tree
                kill_process_tree(process); process.wait(); code = None
        receipt.update(seconds=time.monotonic() - started, exit_code=code,
                       output_file=str(output), output_sha256=hash_file(output))
        content = output.read_text(encoding='utf8', errors='replace') if output.stat().st_size <= 8*1024*1024 else ''
        receipt['output_excerpt'] = content[-6000:]
        after = source_bindings(project, workspace)
        after.pop(audit_file.relative_to(project).as_posix(), None)
        if after != bindings: receipt.update(status='SOURCE_CHANGED', reason='Proof inputs changed while Lean ran')
        elif code is None: receipt['status'] = 'TIMEOUT'
        elif code != 0 or not content or 'sorryAx' in content or re.search(r"uses ['\"]sorry['\"]", content): receipt['status'] = 'FAILED'
        else: receipt['status'] = 'TOOL_PASSED_AUDIT_PENDING'
    finally:
        if audit_file is not None: audit_file.unlink(missing_ok=True)
    receipt['scope'] = 'Tool success still requires independent theorem-statement, imports and axiom audit; never auto-certifies novelty'
    record_tool(project, claim_id, 'formal_receipt', receipt)
    return receipt
