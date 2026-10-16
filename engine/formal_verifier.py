"""Validate Lean inputs and refuse execution until OS isolation is certified."""
from __future__ import annotations
from pathlib import Path
import re
import shutil
import subprocess
from research_quality import hash_file, local_file
from .common import stamp


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
        'at': stamp(), 'status': 'NOT_RUN', 'source_bindings': {}, 'statement_match': 'NOT_CHECKED',
        'execution_started': False, 'isolation': 'NOT_IMPLEMENTED'}
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
    # The research sandbox does not enclose controller-launched Lean/Lake. Even
    # a version probe can load workspace configuration, and Lean #eval can run
    # arbitrary IO. Neither pinned inputs nor a proof-marker scan certifies OS
    # isolation. All callers, including explicit CLI and accepted candidates,
    # stop before subprocesses, audit copies, logs, or inherited environments.
    # No configuration/environment flag may opt the automatic path back in.
    receipt.update(status='ISOLATION_UNCERTIFIED',
        reason='Lean/Lake execution is blocked: no certified OS isolation backend is implemented',
        scope='Input validation only; no Lean execution or theorem certification occurred')
    record_tool(project, claim_id, 'formal_receipt', receipt)
    return receipt
