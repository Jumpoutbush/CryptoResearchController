"""Local paper/version/span projection. No fetch, ingest, extraction or source writes."""
import re
from pathlib import Path
import configuration
from research_quality import hash_file
from supervision_contracts import canonical_hash
from . import source_schema as contract
from .adapters import technical_reviews


def _object(project,relative,default):
    file=contract.path(project,relative)
    return configuration.load_json(file) if file.exists() else default


def _pdf_pages(path):
    try:
        try: import pymupdf as pdf
        except ImportError: import fitz as pdf
    except ImportError: return None,None
    if path.stat().st_size>80*1024*1024: return None,None
    try:
        with pdf.open(str(path)) as doc:
            return [p.get_text('text',sort=True) for p in doc],str(pdf.VersionBind)
    except Exception: return None,None


def _normal(value): return ' '.join(value.split())


def _location(project,span,paper,index):
    """Check original PDF pages, both frozen hashes, and the declared extractor."""
    source=contract.path(project,paper['source_file'])
    action='Re-ingest the intended original using paper ingest, extract locally, then review a new frozen span.'
    if not source.is_file(): return 'MISSING_PRIMARY_SOURCE',action
    if hash_file(source)!=paper['sha256']: return 'SOURCE_HASH_MISMATCH',action
    if source.suffix.lower()!='.pdf' or not source.read_bytes()[:8].startswith(b'%PDF-'):
        return 'MISSING_PRIMARY_SOURCE',action
    if not span or span.get('location') is None: return 'LOCATION_UNVERIFIED','Record a structured, original-page checked location.'
    extract=span['extraction']; txt=contract.path(project,extract['source_file'])
    if not txt.is_file(): return 'EXTRACTION_UNAVAILABLE','Run the existing local paper extraction interface.'
    if hash_file(txt)!=extract['sha256']: return 'EXTRACTION_HASH_MISMATCH','Review the changed extraction and record a new hash.'
    if index.get('sha256')!=paper['sha256'] or index.get('text_path')!=extract['source_file']:
        return 'EXTRACTION_INDEX_MISMATCH','Refresh the existing PDF index for the intended source.'
    if index.get('status')!='TEXT_EXTRACTED_UNVERIFIED':
        return 'EXTRACTION_UNAVAILABLE','Inspect the original PDF; OCR or extraction repair may be necessary.'
    pages,version=_pdf_pages(source)
    if pages is None: return 'EXTRACTION_UNAVAILABLE','Install/repair the optional local PDF parser or inspect the original manually.'
    if extract['parser']!='PyMuPDF' or extract['version']!=version:
        return 'EXTRACTION_VERSION_MISMATCH','Recheck the source with the declared extractor version.'
    loc=span['location']; start,end=loc['page_start'],loc['page_end']
    if end>len(pages): raise ValueError('Invalid source location outside original PDF')
    original=_normal('\n'.join(pages[start-1:end]))
    text=txt.read_text(encoding='utf-8-sig')
    chunks=re.split(r'\n=== PDF PAGE (\d+) ===\n',text)
    if chunks[0].strip() or [int(chunks[i]) for i in range(1,len(chunks)-1,2)]!=list(range(1,len(pages)+1)):
        raise ValueError('Invalid or duplicate extracted source location page markers')
    mapped={int(chunks[i]):chunks[i+1] for i in range(1,len(chunks)-1,2)}
    if len(mapped)!=len(pages) or any(_normal(mapped.get(i+1,''))!=_normal(p) for i,p in enumerate(pages)):
        raise ValueError('Extracted source location does not match original PDF pages')
    if _normal(loc['theorem']) not in original or _normal(loc['excerpt']) not in original:
        raise ValueError('Source location marker/excerpt absent from original page')
    return 'FULLTEXT_LOCATED',None


def project(g,claim_nodes):
    project=g.project
    uploads=_object(project,'literature/uploads.json',{'schema_version':1,'files':[]})
    if not isinstance(uploads,dict) or uploads.get('schema_version')!=1 or not isinstance(uploads.get('files'),list):
        raise ValueError('Unsupported upload registry')
    index=_object(project,'literature/pdf_index.json',{'files':{}})
    if not isinstance(index,dict) or not isinstance(index.get('files'),dict): raise ValueError('Invalid PDF extraction index')
    registry=_object(project,contract.REGISTRY,{'schema_version':1,'spans':[]})
    spans=contract.validate(project,registry)['spans']
    by_review={}
    for s in spans: by_review.setdefault(s['review_file'],[]).append(s)
    primary={}
    def source(relative,sha,**metadata):
        contract.path(project,relative); contract.digest(sha)
        key=(relative,sha)
        if key in primary:
            node=g.nodes[primary[key]]
            if metadata.get('version') is not None and node.get('version') not in {None,metadata['version']}:
                raise ValueError('Conflicting metadata for exact paper version')
            for k,v in metadata.items():
                if node.get(k) is None and v is not None: node[k]=v
            return primary[key]
        actual=g.digest(relative)
        meta={k:metadata.get(k) for k in ('title','authors','version','venue','url')}
        uid=g.node('SOURCE_VERSION','paper/'+relative,sha,relative,record_kind='PRIMARY_PAPER',
            source_file=relative,sha256=sha,pinned_sha256=sha,current_sha256=actual,
            validity='SOURCE_BOUND' if actual==sha else 'PENDING_REVALIDATION',**meta)
        primary[key]=uid
        return uid
    # Duplicate bytes/paths never imply paper identity or precedence.
    seen_uploads=set()
    for upload in uploads['files']:
        if not isinstance(upload,dict): raise ValueError('Invalid upload record')
        relative=upload.get('file'); sha=upload.get('sha256'); contract.path(project,relative); contract.digest(sha)
        key=(relative,sha)
        if key in seen_uploads: g.gaps.add('DUPLICATE_UPLOAD:'+relative)
        seen_uploads.add(key)
        source(relative,sha,title=upload.get('title'),url=upload.get('source_url'))
    consumed=set(); bound_metadata={}
    for relative,review,error,decisive in technical_reviews.read(project,by_review):
        paper=review.get('paper',{}); sha=paper.get('sha256'); contract.digest(sha)
        matching=by_review.get(relative) or [None]
        for span in matching:
            if span:
                consumed.add(span['id'])
                if (span['source_file']!=paper['source_file'] or span['sha256']!=sha or span['version']!=paper['version']
                        or span['review_sha256']!=g.digest(relative)):
                    raise ValueError('Citation does not bind the exact technical review and PDF version')
            metadata={**paper,**({k:span.get(k) for k in ('authors','venue','url')} if span else {})}
            key=(paper['source_file'],sha)
            bound={k:metadata.get(k) for k in ('title','authors','version','venue','url') if metadata.get(k) is not None}
            previous=bound_metadata.setdefault(key,{})
            if any(k in previous and previous[k]!=v for k,v in bound.items()):
                raise ValueError('Conflicting metadata for exact paper version')
            previous.update(bound)
            sid=source(paper['source_file'],sha,**{k:metadata.get(k) for k in ('title','authors','version','venue','url')})
            # Enrich registry metadata only from an explicitly bound technical review.
            g.nodes[sid].update(previous)
            record=index['files'].get(Path(paper['source_file']).name,{})
            if not isinstance(record,dict): raise ValueError('PDF index record must be an object')
            state,recovery=_location(project,span,paper,record)
            math='LAYOUT_ATTESTED_NOT_PROOF' if record.get('math_layout_verified') is True else 'MATH_RENDER_UNCERTAIN'
            eligible=bool(state=='FULLTEXT_LOCATED' and error is None and decisive and math=='LAYOUT_ATTESTED_NOT_PROOF')
            full=review.get('fulltext_status')=='TECHNICALLY_CHECKED'
            verdict=review.get('coverage_verdict','UNVERIFIED')
            effective=verdict if error is None and full and (verdict not in {'COVERS','CONTRADICTS'} or eligible) else 'UNVERIFIED'
            rid=g.source(relative)
            loc=span.get('location') if span else None
            citation='::'.join((g.project_id,sha,canonical_hash(loc),g.digest(relative)))
            tid=g.node('THEOREM_SPAN',relative+'/'+(span['id'] if span else 'UNLOCATED'),canonical_hash(span or review),relative,
                source_file=paper['source_file'],sha256=sha,source_version=paper['version'],location=loc,
                location_status=state,review_status=effective,original_coverage_verdict=verdict,
                section_status='UNVERIFIED_METADATA',verified_location_fields=['page_start','page_end','theorem','excerpt'] if state=='FULLTEXT_LOCATED' else [],
                fulltext_status=review.get('fulltext_status'),technical_review_path=relative,review_sha256=g.digest(relative),
                extraction=span.get('extraction') if span else None,citation_id=citation,math_render_status=math,
                decisive_eligible=eligible,recovery_action=recovery,review_error=error,
                verified_status='SOURCE_LOCATION_ONLY' if state=='FULLTEXT_LOCATED' else 'UNVERIFIED_SOURCE')
            g.edge(tid,sid,'USES_SOURCE',relative,provenance='ORIGINAL_PDF_LOCATION',location=loc,pdf_sha256=sha,
                verified=state,review_sha256=g.digest(relative))
            g.edge(tid,rid,'REVIEWED_BY',relative,provenance='ORIGINAL_TECHNICAL_REVIEW',verified=effective)
            # Without an explicit revision the judgment is an unbound candidate, never silently attached to latest.
            target=claim_nodes.get((review.get('claim_id'),span.get('claim_revision'))) if span else None
            if target:
                if g.nodes[target]['spec_sha256']!=span['claim_spec_sha256']:
                    raise ValueError('Citation claim specification hash mismatch')
                g.edge(target,tid,'USES_SOURCE',relative,provenance='TECHNICAL_REVIEW_MAPPING',verified=effective,
                    review_status=effective,review_sha256=g.digest(relative),pdf_sha256=sha,location=loc)
            else: g.gaps.add('UNBOUND_TECHNICAL_REVIEW:'+relative)
            if state!='FULLTEXT_LOCATED': g.gaps.add(state+':'+relative)
            if math=='MATH_RENDER_UNCERTAIN': g.gaps.add(math+':'+relative)
    if consumed!={s['id'] for s in spans}: raise ValueError('Source citation references a missing technical review')
    # Supersession is explicit, hash-bound and never removes the prior source.
    for span in spans:
        old=span.get('supersedes')
        if old:
            prior=source(old['source_file'],old['sha256'],version=old.get('version'))
            if prior==primary[(span['source_file'],span['sha256'])]: raise ValueError('A source cannot supersede itself')
            g.edge(primary[(span['source_file'],span['sha256'])],prior,'SUPERSEDES',contract.REGISTRY,
                provenance='EXPLICIT_SOURCE_VERSION_DECLARATION',verified='UNVERIFIED_SOURCE')
