"""Fixed trusted worker; stdin is bounded integer predicate data, never code/path."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from engine.falsification import search_statement


def main():
    raw=sys.stdin.buffer.read(80001)
    if len(raw)>80000: raise ValueError('Bounded integer worker input exceeds 80 KB')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'statement','low','high','max_cases','max_seconds'}:
        raise ValueError('Integer worker accepts only exact predicate data and resource bounds')
    if type(value['max_cases']) is not int or not 1<=value['max_cases']<=10000:
        raise ValueError('Integer worker hard case cap is 10000')
    if type(value['max_seconds']) not in {int,float} or not 0<value['max_seconds']<=3:
        raise ValueError('Integer worker hard time cap is three seconds')
    result=search_statement(**value)
    print(json.dumps({'schema_version':1,'tool_version':sys.version.split()[0],'result':result},sort_keys=True))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'schema_version':1,'error':type(exc).__name__+': '+str(exc)},sort_keys=True))
        raise SystemExit(2)
