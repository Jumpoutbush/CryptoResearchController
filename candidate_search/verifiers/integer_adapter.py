"""Run only the fixed trusted integer worker with bounded JSON and lifecycle."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from supervision_process import ProcessTree

WORKER=Path(__file__).with_name('trusted_integer_worker.py').resolve()


def execute(request):
    options=request['options']
    payload={k:options[k] for k in ('low','high','max_cases','max_seconds')}
    payload['statement']=request['statement']
    argv=[sys.executable,'-I','-B',str(WORKER)]
    tree=None; process=None
    result={'tool_version':'CPython '+sys.version.split()[0], 'execution_started':False,
            'isolation':'TRUSTED_DATA_ONLY_CHILD_WITH_PROCESS_TREE_LIFETIME_BOUND',
            'os_deny_read_or_network_isolation_certified':False,'worker_argv':argv,
            'result_status':'FAILED'}
    try:
        tree=ProcessTree()
        with tempfile.TemporaryDirectory(prefix='crc trusted integer ') as work:
            try:
                environment={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
                process=tree.start(argv,cwd=work,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                result['execution_started']=True
                try:
                    output,errors=process.communicate(json.dumps(payload,sort_keys=True).encode('utf8'),
                        timeout=options['wall_timeout_seconds'])
                except subprocess.TimeoutExpired:
                    result.update(tool_status='TIMEOUT',reason='Trusted integer process exceeded its wall-clock bound')
                    return result
            finally:
                # Windows keeps the child's current directory open. Reap its
                # complete Job before TemporaryDirectory tries to remove it.
                tree.close()
                if process is not None:
                    for stream in (process.stdin,process.stdout,process.stderr):
                        if stream is not None: stream.close()
            if len(output)>65536 or len(errors)>65536:
                result.update(tool_status='OUTPUT_LIMIT',reason='Trusted integer output exceeded its receipt bound')
                return result
            decoded=json.loads(output)
            if (not isinstance(decoded,dict) or type(decoded.get('schema_version')) is not int
                    or decoded['schema_version']!=1): raise ValueError('Invalid trusted worker envelope')
            result['tool_version']='CPython '+str(decoded.get('tool_version',sys.version.split()[0]))
            if process.returncode!=0 or 'error' in decoded:
                result.update(tool_status='WORKER_FAILED',reason=decoded.get('error',errors.decode('utf8','replace')))
                return result
            data=decoded['result']
            if (set(decoded)!={'schema_version','tool_version','result'} or not isinstance(decoded['tool_version'],str)
                    or not isinstance(data,dict) or set(data)!={'status','witness','tested_cases','undefined_cases','bounds','seconds'}
                    or data['status'] not in {'EXACT_COUNTEREXAMPLE','SEARCHED_NOT_FOUND'}
                    or data['bounds']!=[options['low'],options['high']]
                    or type(data['tested_cases']) is not int or not 0<=data['tested_cases']<=options['max_cases']
                    or type(data['undefined_cases']) is not int or not 0<=data['undefined_cases']<=data['tested_cases']
                    or type(data['seconds']) not in {int,float} or not math.isfinite(data['seconds']) or data['seconds']<0
                    or (data['status']=='EXACT_COUNTEREXAMPLE')!=(data['witness'] is not None)):
                raise ValueError('Invalid bounded exact-integer worker result')
            result.update(result=data,tool_status=data['status'],result_status=
                'COUNTEREXAMPLE_FOUND' if data['status']=='EXACT_COUNTEREXAMPLE' else 'NO_COUNTEREXAMPLE_WITHIN_BOUND')
            return result
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result.update(tool_status='WORKER_UNAVAILABLE_OR_INVALID',reason=type(exc).__name__+': '+str(exc))
        return result
    finally:
        if tree is not None: tree.close()
        if process is not None:
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None: stream.close()
