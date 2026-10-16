"""Read-only legacy Lean preflight, with explicit natural-statement diagnostics."""
import re
from engine import formal_verifier
from research_quality import hash_file
from candidate_search import validate


def execute(project,request):
    options=request['options']; proof=validate.safe(project,options['proof_file'],roots={'proofs'})
    source=proof.read_text(encoding='utf-8-sig'); diagnostics=[]
    declaration=options['declaration']
    if re.search(r'\b(sorry|admit|sorryAx)\b',source):
        diagnostics.append('UNFINISHED_PROOF_MARKER')
    if re.search(r'\b(?:theorem|lemma)\s+'+re.escape(declaration.rsplit('.',1)[-1])+r'\s*:\s*True\b',source):
        diagnostics.append('TRIVIAL_TRUE_DECLARATION')
    diagnostics.append('QUANTIFIERS_ASSUMPTIONS_DECLARATION_TYPE_AND_AXIOMS_REQUIRE_INDEPENDENT_CORRESPONDENCE_REVIEW')
    try:
        legacy=formal_verifier.preflight(project,request['claim_binding']['claim_id'],options['proof_file'],declaration)
        result_status='UNSUPPORTED'; status=legacy['status']
        if 'UNFINISHED_PROOF_MARKER' in diagnostics: result_status='FAILED'; status='UNFINISHED_PROOF_MARKER'
        return {'result_status':result_status,'tool_status':status,'tool_version':'NOT_PROBED_EXECUTION_BLOCKED',
            'execution_started':False,'isolation':'NOT_IMPLEMENTED',
            'os_deny_read_or_network_isolation_certified':False,'statement_match':'REQUIRES_INDEPENDENT_REVIEW',
            'diagnostics':diagnostics,'result':{'preflight':legacy,'proof_sha256':hash_file(proof),
                'declaration':declaration,'axiom_audit':'NOT_EXECUTED','declaration_type_audit':'NOT_EXECUTED'}}
    except ValueError as exc:
        return {'result_status':'FAILED','tool_status':'INPUT_REJECTED','reason':str(exc),
            'tool_version':'NOT_PROBED_EXECUTION_BLOCKED','execution_started':False,
            'statement_match':'REQUIRES_INDEPENDENT_REVIEW','diagnostics':diagnostics}
