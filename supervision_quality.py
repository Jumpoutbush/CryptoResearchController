"""Conservative, offline signals for an independent supervision review.

These rules inspect controller receipts, never mathematical relevance or truth.
They provide evidence for a supervisor to assess; they do not certify a proof,
resolve an obligation, change a route or spend a model/research budget.
"""
from __future__ import annotations

import re


SCOPES = {'CORE', 'DIRECT_DEPENDENCY', 'SUPPORT'}
MIN_STREAK = 3
NOTE = ('Receipt-based scheduling signals only; no semantic relevance, proof, '
        'novelty or security certification. Missing historical metadata remains unknown; '
        'current file contents are never substituted for historical evidence.')


def _obligation_ids(obligations):
    if isinstance(obligations, dict):
        values = obligations.keys()
    elif isinstance(obligations, (list, tuple)):
        values = [item.get('id') if isinstance(item, dict) else item for item in obligations]
    else:
        raise ValueError('core_obligations must be an object or a list of obligation IDs')
    return sorted({value for value in values if isinstance(value, str) and value.strip()})


def _hashes(record):
    """Only a complete historical hash map can support duplicate detection."""
    value = record.get('evidence_hashes')
    if not isinstance(value, dict):
        return None
    if any(not isinstance(path, str) or not path.strip()
           or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
           for path, digest in value.items()):
        return None
    return value


def _unique(rounds):
    seen = set()
    for record in rounds:
        if not isinstance(record, dict):
            continue
        if record.get('type', 'RESEARCH_ROUND') != 'RESEARCH_ROUND':
            continue
        run_id = record.get('run_id')
        if not isinstance(run_id, str) or not run_id.strip() or run_id in seen:
            continue
        # The first accepted receipt is authoritative; later copies do not
        # overwrite its scope or inflate a consecutive-work count.
        seen.add(run_id)
        yield record


def assess_quality(rounds, *, core_obligations, anchor_id=None, window=3):
    """Assess the last ``window`` distinct accepted receipts, without I/O.

    Each receipt uses the RESEARCH_ROUND event shape: run_id, anchor_id,
    goal_alignment {scope, mainline_progress}, evidence_hashes {path: sha256}.
    A missing binding or progress flag is unknown, rather than evidence of
    irrelevant work. A non-current explicit anchor is excluded from this review.
    Three consecutive explicit support/no-progress receipts are required for
    drift/stall findings; duplicate-content evidence needs two matching receipts.
    """
    if not isinstance(rounds, (list, tuple)):
        raise ValueError('rounds must be a list of accepted receipts')
    if type(window) is not int or not 1 <= window <= 100:
        raise ValueError('window must be an integer from 1 to 100')
    if anchor_id is not None and (not isinstance(anchor_id, str) or not anchor_id.strip()):
        raise ValueError('anchor_id must be a nonempty string or None')
    obligations = _obligation_ids(core_obligations)
    selected = [record for record in _unique(rounds)
                if anchor_id is None or record.get('anchor_id') in (None, anchor_id)][-window:]
    observations = []
    for record in selected:
        alignment = record.get('goal_alignment')
        alignment = alignment if isinstance(alignment, dict) else {}
        bound = anchor_id is None or record.get('anchor_id') == anchor_id
        scope = alignment.get('scope') if alignment.get('scope') in SCOPES else None
        progress = alignment.get('mainline_progress')
        if type(progress) is not bool or not bound:
            progress = None
        hashes = _hashes(record)
        # A positive signal cannot be established by a declaration alone.
        if progress is True and (not hashes or scope not in {'CORE', 'DIRECT_DEPENDENCY'}):
            progress = None
        observations.append({'record': record, 'bound': bound,
                             'scope': scope if bound else None,
                             'progress': progress, 'hashes': hashes})

    findings = []

    def add(code, items, reason):
        findings.append({'code': code,
                         'run_ids': [item['record']['run_id'] for item in items],
                         'evidence_paths': sorted({path for item in items
                                                   for path in (item['hashes'] or {})}),
                         'obligation_ids': obligations,
                         'reason': reason})

    tail = observations[-MIN_STREAK:]
    if len(tail) == MIN_STREAK and all(item['scope'] == 'SUPPORT' for item in tail):
        add('SUPPORT_DRIFT', tail,
            'Three consecutive accepted receipts explicitly classify their work as SUPPORT; '
            'the supervisor must identify a direct return to a frozen core obligation.')
    if obligations and len(tail) == MIN_STREAK and all(item['progress'] is False for item in tail):
        add('CORE_OBLIGATION_STALLED', tail,
            'Three consecutive accepted receipts explicitly record no mainline progress; '
            'the listed frozen obligations require an evidence-based next task.')

    groups = {}
    for item in observations:
        if item['bound'] and item['hashes']:
            # Comparing content sets catches renaming but allows a new result to
            # reuse a background source alongside genuinely new evidence.
            fingerprint = tuple(sorted(set(item['hashes'].values())))
            groups.setdefault(fingerprint, []).append(item)
    for items in groups.values():
        if len(items) > 1:
            add('REPEATED_EVIDENCE', items,
                'Distinct accepted runs cite the same complete set of evidence-content hashes; '
                'renaming files does not establish fresh research progress.')

    known = (len(observations) >= MIN_STREAK
             and all(item['bound'] and item['scope'] is not None
                     and item['progress'] is not None and item['hashes'] is not None
                     for item in observations))
    assessment = 'DRIFT' if findings else ('ON_TRACK' if known else 'INSUFFICIENT_DATA')
    return {'findings': findings,
            'window_run_ids': [item['record']['run_id'] for item in observations],
            'assessment': assessment, 'note': NOTE}


def from_ledger(ledger, focus, obligations, window=3):
    """Replay accepted event metadata, preserving unknown truncated history.

    Durable counted_run_ids define chronology when available. If an accepted
    event has been truncated, an unknown receipt occupies its place; this code
    never recreates old hashes from today's files or calls a model.
    """
    if not isinstance(ledger, dict) or not isinstance(focus, dict):
        raise ValueError('ledger and focus must be objects')
    events = list(_unique(ledger.get('events', [])))
    by_id = {record['run_id']: record for record in events}
    ordered = []
    seen = set()
    for epoch in ledger.get('epochs', []):
        if not isinstance(epoch, dict):
            continue
        for run_id in epoch.get('counted_run_ids', []):
            if isinstance(run_id, str) and run_id.strip() and run_id not in seen:
                seen.add(run_id)
                ordered.append(by_id.get(run_id, {'run_id': run_id}))
    ordered.extend(record for record in events if record['run_id'] not in seen)
    return assess_quality(ordered, core_obligations=obligations,
                          anchor_id=focus.get('anchor_id'), window=window)
