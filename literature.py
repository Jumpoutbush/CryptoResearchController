"""Conservative literature collection for CryptoResearchController.

No fake full-text search: Crossref provides metadata, IACR ePrint RSS provides
recent announcements, and local PDFs are only extracted with optional PyMuPDF.
Full mathematical statements require original-PDF review. Download is opt-in.
"""
from __future__ import annotations

from configuration import settings_for

import datetime as dt
import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UTC = dt.timezone.utc
RSS = 'https://eprint.iacr.org/rss/rss.xml?order=recent'
EPRINT_RE = re.compile(r'^https://eprint\.iacr\.org/([12]\d{3})/(\d{1,6})/?$')


def utc_now():
    return dt.datetime.now(UTC).isoformat(timespec='seconds')


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(path)


def open_url(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'CryptoResearchController/2.1 (+local academic metadata research)'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(6 * 1024 * 1024)


def sha256_file(path):
    sha = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def update_local_pdf(project):
    local = project / 'literature' / 'pdfs'
    txt = project / 'literature' / 'text'
    local.mkdir(parents=True, exist_ok=True)
    txt.mkdir(parents=True, exist_ok=True)
    indexfile = project / 'literature' / 'pdf_index.json'
    old = {}
    if indexfile.is_file():
        try:
            obj = json.loads(indexfile.read_text(encoding='utf-8-sig'))
            old = obj.get('files', {}) if isinstance(obj, dict) else {}
        except Exception:
            old = {}
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            pymupdf = None
    new = {}
    report = {'found': 0, 'parsed': 0, 'unchanged': 0, 'needs_attention': 0,
              'parser': 'PyMuPDF' if pymupdf else 'UNAVAILABLE',
              'hint': 'Optional: python -m pip install pymupdf; no OCR performed.'}
    for pdf in sorted(local.glob('*.pdf')):
        report['found'] += 1
        target = txt / f'{pdf.stem}.txt'
        try:
            if pdf.stat().st_size > 80 * 1024 * 1024:
                raise ValueError('PDF too large (80 MB limit)')
            digest = sha256_file(pdf)
            prev = old.get(pdf.name, {}) if isinstance(old, dict) else {}
            if prev.get('sha256') == digest and (target.is_file() or prev.get('status') == 'NEEDS_OCR'):
                new[pdf.name] = prev
                report['unchanged'] += 1
                continue
            status = 'UNPARSED'
            pages = None
            if pymupdf is not None:
                chunks = []
                with pymupdf.open(str(pdf)) as doc:
                    pages = len(doc)
                    for n, page in enumerate(doc):
                        content = page.get_text('text', sort=True)
                        chunks.append(f'\n=== PDF PAGE {n + 1} ===\n{content}\n')
                data = ''.join(chunks)
                if len(data.strip()) < max(80, (pages or 1) * 25):
                    status = 'NEEDS_OCR'
                else:
                    save(target, data)
                    status = 'TEXT_EXTRACTED_UNVERIFIED'
                    report['parsed'] += 1
            new[pdf.name] = {'sha256': digest, 'status': status, 'pages': pages,
                             'text_path': f'literature/text/{target.name}' if status == 'TEXT_EXTRACTED_UNVERIFIED' else None,
                             'checked_utc': utc_now(), 'math_layout_verified': False}
            if status != 'TEXT_EXTRACTED_UNVERIFIED': report['needs_attention'] += 1
        except Exception as exc:
            report['needs_attention'] += 1
            new[pdf.name] = {'status': 'ERROR', 'error': str(exc), 'checked_utc': utc_now()}
    save(indexfile, json.dumps({'updated_utc': utc_now(), 'files': new, 'limitations':
                                 'Text extraction can corrupt mathematics, figures and footnotes; confirm against PDF.'},
                                indent=2, ensure_ascii=False))
    return report


def fetch_crossref(queries, max_per_query, failures, mailto=None):
    works = []
    for term in queries:
        if not isinstance(term, str) or not term.strip():
            failures.append({'source': 'Crossref', 'query': str(term), 'error': 'invalid query'})
            continue
        try:
            params = {'query.bibliographic': term, 'rows': min(max(int(max_per_query), 1), 15)}
            if mailto: params['mailto'] = mailto
            url = 'https://api.crossref.org/works?' + urllib.parse.urlencode(params)
            data = json.loads(open_url(url, timeout=12))
            for item in data.get('message', {}).get('items', []):
                title = item.get('title', [])
                doi = str(item.get('DOI', ''))
                works.append({'source': 'Crossref', 'title': title[0] if title else '',
                              'url': item.get('URL', ''), 'doi': doi,
                              'year': item.get('published', {}).get('date-parts', [[None]])[0][0],
                              'query': term, 'full_text_verified': False})
        except Exception as exc:
            failures.append({'source': 'Crossref', 'query': term, 'error': str(exc)})
    return works


def fetch_eprint(keywords, failures, maximum=50):
    works = []
    try:
        root = ET.fromstring(open_url(RSS, timeout=12))
        for item in root.findall('.//item'):
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            summary = item.findtext('description', '').strip()
            text = (title + ' ' + summary).lower()
            if keywords and not any(str(word).lower() in text for word in keywords):
                continue
            if link.startswith('https://eprint.iacr.org/'):
                works.append({'source': 'IACR ePrint RSS', 'title': title,
                              'url': link, 'doi': '', 'year': None,
                              'query': 'recent', 'full_text_verified': False})
            if len(works) >= maximum:
                break
    except Exception as exc:
        failures.append({'source': 'IACR ePrint RSS', 'query': 'recent', 'error': str(exc)})
    return works


class RestrictRedirect(urllib.request.HTTPRedirectHandler):
    """Only follow verified ePrint HTTPS redirects, avoiding arbitrary hosts."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlparse(newurl)
        if parts.scheme != 'https' or parts.hostname != 'eprint.iacr.org':
            raise ValueError('PDF redirect outside trusted source')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_open_pdfs(project, entries, limit=2, max_mb=25):
    pdfdir = project / 'literature' / 'pdfs'
    pdfdir.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(RestrictRedirect())
    output = []
    for item in entries:
        if len(output) >= limit: break
        hit = EPRINT_RE.fullmatch(item.get('url', ''))
        if not hit: continue
        name = f'eprint-{hit.group(1)}-{hit.group(2)}.pdf'
        dest = pdfdir / name
        if dest.is_file(): continue
        url = f'https://eprint.iacr.org/{hit.group(1)}/{hit.group(2)}.pdf'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'CryptoResearchController/2.1 research literature'})
            with opener.open(req, timeout=15) as resp:
                if int(resp.headers.get('Content-Length', '0')) > max_mb * 1024 * 1024:
                    raise ValueError(f'PDF exceeds {max_mb} MB limit')
                buf = resp.read(max_mb * 1024 * 1024 + 1)
            if len(buf) > max_mb * 1024 * 1024 or not buf.startswith(b'%PDF-'):
                raise ValueError('PDF signature or file length invalid')
            temp = dest.with_suffix('.part')
            temp.write_bytes(buf)
            temp.replace(dest)
            output.append({'file': name, 'source': url, 'status': 'DOWNLOADED_UNVERIFIED'})
        except Exception as exc:
            output.append({'file': name, 'source': url, 'status': 'ERROR', 'error': str(exc)})
    return output


def update_literature(project: pathlib.Path, offline=False):
    project = pathlib.Path(project)
    lit = project / 'literature'
    lit.mkdir(parents=True, exist_ok=True)
    queries_path = lit / 'queries.json'
    try:
        cfg = json.loads(queries_path.read_text(encoding='utf-8-sig')) if queries_path.is_file() else {}
    except Exception as exc:
        raise RuntimeError(f'Invalid literature/queries.json: {exc}')
    if not isinstance(cfg, dict):
        raise RuntimeError('literature/queries.json must be JSON object')
    old_path = lit / 'latest.json'
    old = {}
    if old_path.is_file():
        try:
            old = json.loads(old_path.read_text(encoding='utf-8-sig'))
        except Exception:
            old = {}
    catalog_path = lit / 'CATALOG.json'
    catalog = {}
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding='utf-8-sig'))
        if not isinstance(catalog, dict): raise ValueError('CATALOG.json must be an object')
    catalog_items = catalog.get('items', [])
    if not isinstance(catalog_items, list): raise ValueError('CATALOG.json items must be a list')
    prior = {str(i.get('doi') or i.get('url')).strip().lower()
             for i in catalog_items + old.get('items', []) if isinstance(i, dict)}
    queries = cfg.get('queries', [])
    if not isinstance(queries, list): raise RuntimeError('queries must be list')
    keywords = cfg.get('keywords', [])
    if not isinstance(keywords, list): raise RuntimeError('keywords must be list')
    # Rotate a bounded batch rather than silently ignoring queries beyond ten.
    history_path = lit / 'SEARCH_COVERAGE.json'
    history = json.loads(history_path.read_text(encoding='utf-8-sig')) if history_path.is_file() else {}
    history = history if isinstance(history, dict) else {}
    signature = hashlib.sha256(json.dumps(queries, ensure_ascii=False).encode('utf-8')).hexdigest()
    if history.get('query_sha256') != signature:
        history = {'schema_version': 1, 'query_sha256': signature, 'cursor': 0, 'queries': {}}
    cursor = int(history.get('cursor', 0)) % max(len(queries), 1)
    indices = [(cursor+i) % len(queries) for i in range(min(len(queries), 8))] if queries else []
    selected_queries = [queries[i] for i in indices]
    failures = []
    candidates = []
    status = 'LOCAL_ONLY' if offline else 'OK'
    if offline:
        candidates = old.get('items', []) if isinstance(old, dict) else []
    else:
        candidates.extend(fetch_crossref(selected_queries, cfg.get('max_per_query', 8), failures,
                                         cfg.get('crossref_contact_email')))
        if cfg.get('eprint_rss', True):
            candidates.extend(fetch_eprint(keywords, failures))
    unique = {}
    for paper in candidates:
        identifier = str(paper.get('doi') or paper.get('url') or '').strip()
        if identifier: unique[identifier.lower()] = paper
    entries = list(unique.values())
    # If all public sources fail, retain older known references, but mark stale explicitly.
    if not entries and failures and old.get('items'):
        entries = old['items']
        status = 'FAILED_USING_STALE_CACHE'
    elif failures:
        status = 'PARTIAL' if entries else 'FAILED'
    # Download policy comes from the controller, never from model-editable metadata.
    policy = settings_for(project)['literature']
    downloaded = []
    if not offline and policy['automatic_pdf_download']:
        downloaded = download_open_pdfs(project, entries,
                                        limit=policy['max_pdf_downloads_per_round'],
                                        max_mb=policy['max_pdf_mb'])
    local = update_local_pdf(project)
    new_entries = [p for p in entries if str(p.get('doi') or p.get('url')).strip().lower() not in prior]
    merged = {str(p.get('doi') or p.get('url')).strip().lower(): p
              for p in catalog_items + entries if isinstance(p, dict) and (p.get('doi') or p.get('url'))}
    save(catalog_path, json.dumps({'schema_version': 1, 'updated_utc': utc_now(),
                                 'items': list(merged.values())}, ensure_ascii=False, indent=2))
    if not offline:
        failed_queries = {f.get('query') for f in failures if f.get('source') == 'Crossref'}
        for i in indices:
            key = str(i)
            record = history['queries'].get(key, {'query': queries[i], 'attempts': 0, 'successful_attempts': 0})
            record['attempts'] += 1
            record['successful_attempts'] += int(queries[i] not in failed_queries)
            record['last_attempt_utc'] = utc_now()
            record['last_status'] = 'ERROR' if queries[i] in failed_queries else 'METADATA_FETCHED'
            history['queries'][key] = record
        history['cursor'] = (cursor + len(indices)) % max(len(queries), 1)
        save(history_path, json.dumps(history, ensure_ascii=False, indent=2))
    meta = {'retrieved_utc': utc_now(), 'status': status, 'items': entries,
            'failures': failures, 'new_candidate_count': len(new_entries),
            'selected_queries': selected_queries if not offline else [],
            'configured_queries': len(queries), 'catalog_count': len(merged),
            'local_pdf': local, 'downloaded': downloaded,
            'limitations': 'Metadata and RSS alone cannot establish novelty. Verify original theorem, version and proof.'}
    save(old_path, json.dumps(meta, ensure_ascii=False, indent=2))
    lines = ['# Literature retrieval snapshot', '', f'UTC: {meta["retrieved_utc"]}',
             f'STATUS: {status}',
             f'Queries in this batch: {0 if offline else len(selected_queries)} / {len(queries)}; cumulative catalog: {len(merged)}.', '',
             '**Metadata candidates only; no claim of novelty or source completeness.**', '']
    for p in entries:
        lines.append(f'- [{p["title"]}]({p["url"]}) — {p["source"]}' if p.get('url') else f'- {p.get("title")}')
    lines += ['', '## Source errors']
    lines += [f'- {f["source"]} {f["query"]}: {f["error"]}' for f in failures] or ['- None reported']
    lines += ['', '## Local PDF processing',
              f'- Found {local["found"]}, extracted {local["parsed"]}, unchanged {local["unchanged"]}, needs attention {local["needs_attention"]}.',
              '- Math expressions, figures and page alignment require checking original PDF.']
    save(lit / 'latest.md', '\n'.join(lines) + '\n')
    if new_entries:
        new_lines = ['# New candidate papers — relevance UNVERIFIED', '',
                     'New metadata since previous snapshot; assess actual overlap against claims.', '']
        new_lines += [f'- {p.get("title")} | {p.get("url")}' for p in new_entries]
        save(lit / 'NEW_CANDIDATES.md', '\n'.join(new_lines) + '\n')
    return {'status': status, 'candidate_count': len(entries), 'new_candidate_count': len(new_entries),
            'failed_sources': len(failures), 'local_pdf': local, 'downloaded': len(downloaded)}
