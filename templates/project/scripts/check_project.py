#!/usr/bin/env python3
"""Generic local project schema checker; no model or network request."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    required = ['PROJECT.json','GOAL.md','RESEARCH_PROFILE.json','research/STATE.json','research/GATES.json','literature/queries.json','ideas/INDEX.json']
    for name in required:
        if not (ROOT / name).is_file(): raise ValueError('Missing '+name)
    for file in ROOT.rglob('*.json'):
        if '.control' not in file.parts and 'tmp' not in file.parts:
            json.loads(file.read_text(encoding='utf-8-sig'))
    state=json.loads((ROOT/'research/STATE.json').read_text(encoding='utf-8-sig'))
    for name in ['phase','decision','priority_problem','next_task']:
        if not isinstance(state.get(name),str) or not state[name].strip(): raise ValueError('Invalid '+name)
    print('PROJECT_CHECK_OK', ROOT.name)

if __name__ == '__main__': main()
