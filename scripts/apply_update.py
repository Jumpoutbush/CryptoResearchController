#!/usr/bin/env python3
"""Apply a framework-only update without replacing personal research files."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

FORBIDDEN={'projects','state','logs','locks','backups','.git','.codex','.venv'}
IGNORE_LINES=['/projects/','/config/projects/','/state/','/logs/','/locks/','/backups/']


def digest(data):return hashlib.sha256(data).hexdigest()


def relative_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:raise ValueError('Invalid update path')
    p=PurePosixPath(value)
    parts=p.parts
    if p.is_absolute() or '..' in parts or not parts:raise ValueError('Invalid update path')
    if parts[0].casefold() in FORBIDDEN:raise ValueError('Personal or runtime path forbidden: '+value)
    if len(parts)>1 and parts[0].casefold()=='config' and parts[1].casefold()=='projects':raise ValueError('Personal configuration forbidden')
    if value in {'config/defaults.json','config/route_policy.json','config/profiles.json'}:
        raise ValueError('Existing operator defaults must not be replaced by this update')
    return Path(*parts)


def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    mode=path.stat().st_mode if path.exists() else None
    fd,name=tempfile.mkstemp(prefix='.framework-update-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        if mode is not None:os.chmod(name,mode)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if not f.read(1):f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise RuntimeError('项目或框架正在运行，请先 stop 并等当前轮结束：'+path.name) from exc
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt;msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def update_plan(bundle,target):
    manifest=json.loads((bundle/'UPDATE_MANIFEST.json').read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version')!=1:raise ValueError('Unsupported update manifest')
    if not (target/'runner.py').is_file() or not (target/'research.py').is_file():
        raise ValueError('目标必须是现有 CryptoResearchController 根目录')
    plans=[];seen=set()
    for item in manifest['files']:
        rel=relative_path(item['path']);key=rel.as_posix().casefold()
        if key in seen:raise ValueError('Duplicate update target')
        seen.add(key)
        source=bundle/'payload'/rel
        if source.is_symlink() or not source.is_file():raise ValueError('Invalid payload file')
        source.resolve().relative_to((bundle/'payload').resolve())
        data=source.read_bytes()
        if digest(data)!=item['sha256']:raise ValueError('Payload SHA256 mismatch: '+str(rel))
        dest=target/rel;dest.resolve().relative_to(target.resolve())
        old=dest.read_bytes() if dest.is_file() else None
        action=item.get('action','replace')
        if key=='config/supervision_policy.json' and action!='preserve_existing':
            raise ValueError('Supervision policy updates must preserve existing operator settings')
        if action=='preserve_existing' and old is not None:continue
        if action=='merge_ignore':
            old=old or b'';existing=old.decode('utf-8-sig').splitlines()
            missing=[x for x in IGNORE_LINES if x not in existing]
            # Put exclusions last so old negated state rules cannot re-include private data.
            tail='\n# Personal projects and local research state\n'+'\n'.join(IGNORE_LINES)+'\n'
            data=old+(b'' if not old or old.endswith(b'\n') else b'\n')+tail.encode('utf8') if missing or not old.endswith(('\n'.join(IGNORE_LINES)+'\n').encode()) else old
        elif action not in {'replace','preserve_existing'}:raise ValueError('Unknown update action')
        if old!=data:plans.append((rel,dest,old,data))
    return plans


def active_locks(target):
    yield target/'locks/framework-update.lock'
    yield target/'locks/project-registry.lock'
    for manifest in sorted((target/'projects').glob('*/PROJECT.json')):
        obj=json.loads(manifest.read_text(encoding='utf-8-sig'));identifier=obj.get('id')
        if not isinstance(identifier,str) or not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in identifier):
            raise ValueError('Invalid project ID while checking active runs')
        yield target/'locks'/('route-'+identifier+'.lock')
        yield target/'locks'/(identifier+'.lock')


def apply(bundle,target,*,perform=False,verify=True):
    plans=update_plan(bundle,target)
    print('FRAMEWORK_FILES_TO_UPDATE:',len(plans))
    for rel,_,_,_ in plans:print('  '+rel.as_posix())
    if not perform:
        print('预览完成，未修改目标。增加 --apply 执行。');return None
    if not plans:print('ALREADY_UP_TO_DATE');return None
    with contextlib.ExitStack() as stack:
        for path in active_locks(target):stack.enter_context(lock(path))
        # Reread under locks so an operator edit between preview/apply is not lost.
        plans=update_plan(bundle,target)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup=target/'backups'/('framework-update-'+stamp);backup.mkdir(parents=True)
        journal=[]
        for rel,dest,old,data in plans:
            if old is not None:atomic_write(backup/'before'/rel,old)
            journal.append({'path':rel.as_posix(),'existed':old is not None,'before_sha256':digest(old) if old is not None else None,'after_sha256':digest(data)})
        atomic_write(backup/'JOURNAL.json',json.dumps({'schema_version':1,'files':journal},indent=2).encode())
        applied=[]
        try:
            for rel,dest,old,data in plans:
                atomic_write(dest,data);applied.append((dest,old))
            if verify:
                env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1'
                for argv in ([sys.executable,'-B',str(target/'research.py'),'--help'],
                    [sys.executable,'-B','-c','import configuration, research_quality, theory_gate, runner_core, supervision, supervision_quality, engine.initialization, engine.claim_graph, engine.knowledge_graph, engine.knowledge_links, engine.knowledge_history; configuration.settings_for()']):
                    result=subprocess.run(argv,cwd=target,env=env,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=30)
                    if result.returncode:raise RuntimeError('更新后的框架检查失败：'+result.stderr[-1600:])
        except BaseException:
            for dest,old in reversed(applied):
                if old is None:dest.unlink(missing_ok=True)
                else:atomic_write(dest,old)
            raise
        print('UPDATE_OK; BACKUP:',backup)
        print('个人项目、个人参数、状态、论文和 .git 保持原文件。')
        return backup


def rollback(target,backup):
    backup=backup.resolve();backup.relative_to((target/'backups').resolve())
    journal=json.loads((backup/'JOURNAL.json').read_text())
    plans=[]
    for item in journal['files']:
        rel=relative_path(item['path']);dest=target/rel;dest.resolve().relative_to(target.resolve())
        if not dest.is_file() or digest(dest.read_bytes())!=item['after_sha256']:
            raise ValueError('更新后文件已有变化，不能直接回滚：'+str(rel))
        old=(backup/'before'/rel).read_bytes() if item['existed'] else None
        if old is not None and digest(old)!=item['before_sha256']:raise ValueError('Backup integrity check failed')
        plans.append((dest,old))
    with contextlib.ExitStack() as stack:
        for path in active_locks(target):stack.enter_context(lock(path))
        for dest,old in reversed(plans):
            if old is None:dest.unlink()
            else:atomic_write(dest,old)
    print('ROLLBACK_OK')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--rollback')
    args=p.parse_args(argv)
    target=Path(args.target).expanduser().resolve()
    if args.rollback:rollback(target,Path(args.rollback));return 0
    apply(Path(__file__).resolve().parent,target,perform=args.apply)
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,RuntimeError,OSError,KeyError,subprocess.TimeoutExpired) as exc:
        print('UPDATE_ERROR:',exc,file=sys.stderr);sys.exit(2)
