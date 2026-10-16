"""Read the old six-axis judgments without assigning new scientific verdicts."""
from pathlib import Path
import configuration
from research_quality import validate_technical_review
from ..source_schema import path


def read(project, explicit=()):
    directory=path(project,'literature/technical_reviews')
    result=[]
    files=set(directory.rglob('*.json')) if directory.exists() else set()
    files.update(path(project,relative) for relative in explicit)
    for file in sorted(files):
        if not file.is_file(): raise ValueError('Missing explicitly referenced technical review')
        relative=file.relative_to(project).as_posix(); path(project,relative)
        raw=configuration.load_json(file)
        if not isinstance(raw,dict): raise ValueError('Technical review must be an object')
        if not isinstance(raw.get('paper'),dict): raise ValueError('Technical review paper must be an object')
        # Protect all paths before invoking the older validator, including derivations.
        path(project,raw.get('paper',{}).get('source_file'))
        from ..build import _safe_reference
        derivations=raw.get('derivation_paths',[])
        if not isinstance(derivations,list) or any(not isinstance(r,str) for r in derivations):
            raise ValueError('Technical review derivation_paths must be a list of paths')
        for rel in derivations: _safe_reference(project,rel)
        try:
            checked=validate_technical_review(project,relative)
            error=None
        except (ValueError,OSError) as exc:
            checked=raw; error=str(exc)
        decisive=False
        if error is None:
            try: validate_technical_review(project,relative,decisive=True); decisive=True
            except (ValueError,OSError): pass
        result.append((relative,checked,error,decisive))
    return result
