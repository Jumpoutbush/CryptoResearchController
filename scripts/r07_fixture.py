"""Synthetic original PDFs; used only by disposable offline acceptance fixtures."""
import json
from pathlib import Path
import configuration
from literature import update_local_pdf
from research_quality import DIMENSIONS,hash_file


def pdf_bytes(pages):
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',None,b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids=[]
    for text in pages:
        page=len(objects)+1; stream=page+1; kids.append(f'{page} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream} 0 R >>'.encode())
        content=('BT /F1 12 Tf 50 700 Td ('+text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')+') Tj ET').encode()
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream')
    objects[1]=f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'.encode()
    raw=b'%PDF-1.4\n'; offsets=[0]
    for i,obj in enumerate(objects,1): offsets.append(len(raw)); raw+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start=len(raw); raw+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    raw+=b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:])
    return raw+f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


def seed(project,claim_id='C-1'):
    def put(relative,value):
        path=project/relative; path.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(value,bytes): path.write_bytes(value)
        else: configuration.atomic_json(path,value)
    uploads=[]
    for name,version in [('toy-v0','v0'),('toy-v1','v1'),('toy-v2','v2')]:
        rel='literature/pdfs/'+name+'.pdf'
        put(rel,pdf_bytes(['Synthetic abstract '+version+'; this is a controller provenance fixture only.',
            'Theorem 1. Every integer square is nonnegative. The quantified domain is integers only. '+version]))
        uploads.append({'file':rel,'sha256':hash_file(project/rel),'title':'Same synthetic title','source_url':'https://example.invalid/'+version})
    put('literature/uploads.json',{'schema_version':1,'files':uploads})
    update_local_pdf(project)
    index=configuration.load_json(project/'literature/pdf_index.json')
    # Explicit operator layout attestation for a plain ASCII synthetic page, never a theorem review.
    index['files']['toy-v1.pdf']['math_layout_verified']=True; put('literature/pdf_index.json',index)
    review={'schema_version':1,'claim_id':claim_id,'paper':{'title':'Same synthetic title','version':'v1',
        'source_file':uploads[1]['file'],'sha256':uploads[1]['sha256']},'fulltext_status':'TECHNICALLY_CHECKED',
        'author_claim':'Integer square nonnegativity','technical_statement':'Every integer square is nonnegative',
        'source_location':'Theorem 1, PDF page 2','comparison':[{'dimension':d,'idea':'Integer invariant',
            'paper':'Same integer invariant','relation':'MATCH','source_location':'PDF page 2',
            'argument':'Synthetic mapping only; no cryptographic claim'} for d in sorted(DIMENSIONS)],
        'construction_mapping':'Identical integer interface','reduction_argument':'See separate candidate derivation',
        'limitations':'Synthetic provenance fixture only','coverage_verdict':'COVERS','derivation_paths':['proofs/derivation.md']}
    rel='literature/technical_reviews/toy.json'; put(rel,review)
    import pymupdf
    span={'id':'T1','source_file':uploads[1]['file'],'sha256':uploads[1]['sha256'],'version':'v1',
        'authors':['Synthetic fixture author'],'venue':'Offline fixture','url':'https://example.invalid/v1',
        'review_file':rel,'review_sha256':hash_file(project/rel),'claim_revision':1,
        'claim_spec_sha256':next(c['spec_sha256'] for c in configuration.load_json(project/'research/discovery/CLAIM_GRAPH.json')['claims'] if c['id']==claim_id),
        'extraction':{'source_file':'literature/text/toy-v1.txt','sha256':hash_file(project/'literature/text/toy-v1.txt'),
            'parser':'PyMuPDF','version':str(pymupdf.VersionBind)},
        'location':{'page_start':2,'page_end':2,'section':'Synthetic theorem','theorem':'Theorem 1.',
            'excerpt':'Every integer square is nonnegative.'},
        'supersedes':{'source_file':uploads[0]['file'],'sha256':uploads[0]['sha256'],'version':'v0'}}
    put('literature/source_spans.json',{'schema_version':1,'spans':[span]})
    return span
