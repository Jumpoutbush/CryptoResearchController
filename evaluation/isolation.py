"""R16 temporary AppContainer access probe; never authorizes an agent runner.

The controller impersonates a live, suspended child's token for two kernel file
access checks. The fixed child only exits; it never receives the private path.
No serialized claim, changed working directory, or later process is certified.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W
import hashlib
import os
from pathlib import Path
import tempfile
import uuid


MICROSOFT_REFERENCES = (
    'https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer',
    'https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile',
    'https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-impersonateloggedonuser',
    'https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation',
    'https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile',
)


class _ProbeFailure(Exception):
    pass


class _SID_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Sid', W.LPVOID), ('Attributes', W.DWORD)]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [('AppContainerSid', W.LPVOID),
                ('Capabilities', ctypes.POINTER(_SID_ATTRIBUTES)),
                ('CapabilityCount', W.DWORD), ('Reserved', W.DWORD)]


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR),
                ('lpTitle', W.LPWSTR), ('dwX', W.DWORD), ('dwY', W.DWORD),
                ('dwXSize', W.DWORD), ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD),
                ('dwFlags', W.DWORD), ('wShowWindow', W.WORD), ('cbReserved2', W.WORD),
                ('lpReserved2', ctypes.POINTER(W.BYTE)), ('hStdInput', W.HANDLE),
                ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class _STARTUPINFOEX(ctypes.Structure):
    _fields_ = [('StartupInfo', _STARTUPINFO), ('lpAttributeList', W.LPVOID)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE),
                ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


class _Windows:
    """Typed system APIs only; this object accepts no executable or command."""
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.security = ctypes.WinDLL('advapi32', use_last_error=True)
        self.userenv = ctypes.WinDLL('userenv', use_last_error=True)
        self.ole = ctypes.WinDLL('ole32', use_last_error=True)
        self._bind(self.ole, 'CoTaskMemFree', [W.LPVOID], None)
        self._bind(self.kernel, 'GetCurrentProcess', [], W.HANDLE)
        self._bind(self.kernel, 'GetCurrentThread', [], W.HANDLE)
        self._bind(self.kernel, 'GetSystemDirectoryW', [W.LPWSTR, W.UINT], W.UINT)
        self._bind(self.kernel, 'CloseHandle', [W.HANDLE], W.BOOL)
        self._bind(self.kernel, 'LocalFree', [W.LPVOID], W.LPVOID)
        self._bind(self.kernel, 'InitializeProcThreadAttributeList',
                   [W.LPVOID, W.DWORD, W.DWORD, ctypes.POINTER(ctypes.c_size_t)], W.BOOL)
        self._bind(self.kernel, 'UpdateProcThreadAttribute',
                   [W.LPVOID, W.DWORD, ctypes.c_size_t, W.LPVOID, ctypes.c_size_t,
                    W.LPVOID, W.LPVOID], W.BOOL)
        self._bind(self.kernel, 'DeleteProcThreadAttributeList', [W.LPVOID], None)
        self._bind(self.kernel, 'CreateProcessW',
                   [W.LPCWSTR, W.LPWSTR, W.LPVOID, W.LPVOID, W.BOOL, W.DWORD,
                    W.LPVOID, W.LPCWSTR, ctypes.POINTER(_STARTUPINFOEX),
                    ctypes.POINTER(_PROCESS_INFORMATION)], W.BOOL)
        self._bind(self.kernel, 'ResumeThread', [W.HANDLE], W.DWORD)
        self._bind(self.kernel, 'WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD)
        self._bind(self.kernel, 'GetExitCodeProcess', [W.HANDLE, ctypes.POINTER(W.DWORD)], W.BOOL)
        self._bind(self.kernel, 'TerminateProcess', [W.HANDLE, W.UINT], W.BOOL)
        self._bind(self.kernel, 'CreateFileW',
                   [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE)
        self._bind(self.kernel, 'ReadFile',
                   [W.HANDLE, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD), W.LPVOID], W.BOOL)
        self._bind(self.security, 'OpenProcessToken',
                   [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)], W.BOOL)
        self._bind(self.security, 'OpenThreadToken',
                   [W.HANDLE, W.DWORD, W.BOOL, ctypes.POINTER(W.HANDLE)], W.BOOL)
        self._bind(self.security, 'GetTokenInformation',
                   [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)], W.BOOL)
        self._bind(self.security, 'ImpersonateLoggedOnUser', [W.HANDLE], W.BOOL)
        self._bind(self.security, 'RevertToSelf', [], W.BOOL)
        self._bind(self.security, 'ConvertSidToStringSidW',
                   [W.LPVOID, ctypes.POINTER(W.LPWSTR)], W.BOOL)
        self._bind(self.security, 'ConvertStringSecurityDescriptorToSecurityDescriptorW',
                   [W.LPCWSTR, W.DWORD, ctypes.POINTER(W.LPVOID), W.LPVOID], W.BOOL)
        self._bind(self.security, 'SetFileSecurityW', [W.LPCWSTR, W.DWORD, W.LPVOID], W.BOOL)
        self._bind(self.security, 'FreeSid', [W.LPVOID], W.LPVOID)
        self._bind(self.userenv, 'CreateAppContainerProfile',
                   [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPVOID, W.DWORD,
                    ctypes.POINTER(W.LPVOID)], ctypes.c_long)
        self._bind(self.userenv, 'DeleteAppContainerProfile', [W.LPCWSTR], ctypes.c_long)
        self._bind(self.userenv, 'GetAppContainerFolderPath',
                   [W.LPCWSTR, ctypes.POINTER(W.LPWSTR)], ctypes.c_long)

    @staticmethod
    def _bind(library, name, args, result):
        function = getattr(library, name)
        function.argtypes = args
        function.restype = result

    @staticmethod
    def require(value, stage):
        if not value:
            raise _ProbeFailure(stage + ':WINERROR_' + str(ctypes.get_last_error()))

    def close(self, handle):
        if handle:
            self.require(self.kernel.CloseHandle(handle), 'CLOSE_HANDLE')

    def info(self, token, kind):
        needed = W.DWORD()
        self.security.GetTokenInformation(token, kind, None, 0, ctypes.byref(needed))
        if not 0 < needed.value <= 65536:
            raise _ProbeFailure('TOKEN_INFORMATION_SIZE_INVALID')
        data = ctypes.create_string_buffer(needed.value)
        self.require(self.security.GetTokenInformation(token, kind, data, needed,
                                                       ctypes.byref(needed)), 'GET_TOKEN_INFORMATION')
        return data

    def sid_string(self, sid):
        text = W.LPWSTR()
        self.require(self.security.ConvertSidToStringSidW(sid, ctypes.byref(text)), 'SID_TO_STRING')
        try:
            return text.value
        finally:
            self.kernel.LocalFree(text)

    def token_observation(self, token, expected_sid):
        is_app = ctypes.cast(self.info(token, 29), ctypes.POINTER(W.DWORD)).contents.value
        count = ctypes.cast(self.info(token, 30), ctypes.POINTER(W.DWORD)).contents.value
        sid_buffer = self.info(token, 31)
        sid = ctypes.cast(sid_buffer, ctypes.POINTER(W.LPVOID)).contents.value
        actual_sid = self.sid_string(sid) if sid else None
        return {'is_appcontainer': is_app == 1, 'capability_count': count,
                'appcontainer_sid': actual_sid,
                'appcontainer_sid_matches_profile': actual_sid == expected_sid}

    def read(self, path):
        # OPEN_EXISTING, GENERIC_READ; no inherited file or private handle.
        handle = self.kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            return {'opened': False, 'winerror': ctypes.get_last_error(), 'data': None}
        try:
            data = ctypes.create_string_buffer(1048577)
            count = W.DWORD()
            self.require(self.kernel.ReadFile(handle, data, len(data), ctypes.byref(count), None), 'READ_FILE')
            return {'opened': True, 'winerror': 0, 'data': data.raw[:count.value]}
        finally:
            self.close(handle)

    def temporary_acl(self, path, user_sid, app_sid=None):
        # Only the newly created temporary lane is changed. No inheritance or
        # ALL APPLICATION PACKAGES grant can accidentally authorize its sibling.
        sddl = 'D:P(A;;FA;;;SY)(A;;FA;;;' + user_sid + ')'
        if app_sid:
            sddl += '(A;;GRGX;;;' + app_sid + ')'
        descriptor = W.LPVOID()
        self.require(self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None), 'TEMPORARY_SECURITY_DESCRIPTOR')
        try:
            self.require(self.security.SetFileSecurityW(str(path), 0x80000004, descriptor), 'TEMPORARY_FILE_DACL')
        finally:
            self.kernel.LocalFree(descriptor)


def _report():
    return {'schema_version': 1, 'os_probe_status': 'NOT_ISOLATED',
            'benchmark_agent_isolation': 'NOT_ISOLATED', 'formal_count': False,
            'agent_execution_allowed': False, 'real_supervision_allowed': False,
            'lean_execution_allowed': False, 'reason': 'NOT_PROBED',
            'actor': 'CONTROLLER_THREAD_IMPERSONATING_LIVE_CHILD_TOKEN',
            'child_performed_file_reads': False,
            'probe_scope': 'EXACT_DISPOSABLE_STAGED_FILE_COPIES_AND_LIVE_CHILD_TOKEN_ONLY',
            'token': {}, 'access_checks': {}, 'host_control': {},
            'process': {'fixed_command': 'SYSTEM_CMD_EXIT_0', 'inherit_handles': False,
                        'private_path_in_argv_or_environment': False},
            'cleanup': {'reverted_to_self': False, 'process_handles_closed': False,
                        'profile_deleted': False, 'temporary_lane_removed': False},
            'limitations': ['The child only exits and performs no file reads.',
                            'Only the controller impersonating the live child token performs kernel access checks.',
                            'No later process, real research agent, Codex, supervisor or Lean execution is certified.',
                            'The original input files are not re-ACLd; this proves the staged temporary copies only.',
                            'Formal benchmark agent isolation remains unverified; calibration fixtures are not formal statistics.'],
            'microsoft_references': list(MICROSOFT_REFERENCES)}


def _input(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
            raise _ProbeFailure('LINKED_INPUT_REJECTED')
    if not path.is_file():
        raise _ProbeFailure('INPUT_MUST_BE_AN_EXISTING_REGULAR_FILE')
    with path.open('rb') as stream:
        data = stream.read(1048577)
    if not data or len(data) > 1048576:
        raise _ProbeFailure('INPUT_SIZE_MUST_BE_1_TO_1048576_BYTES')
    return path, data


def _probe_windows(api, public, private, public_data, private_data, result, timeout_seconds):
    profile = 'CRC.R16.' + uuid.uuid4().hex
    app_sid = W.LPVOID()
    process = _PROCESS_INFORMATION()
    host_token = W.HANDLE()
    child_token = W.HANDLE()
    thread_token = W.HANDLE()
    attributes = None
    attributes_initialized = False
    created_profile = False
    impersonating = False
    unreverted = False
    try:
        existing = W.HANDLE()
        if api.security.OpenThreadToken(api.kernel.GetCurrentThread(), 8, True, ctypes.byref(existing)):
            api.close(existing)
            raise _ProbeFailure('CALLER_ALREADY_IMPERSONATING')
        if ctypes.get_last_error() != 1008:
            raise _ProbeFailure('CALLER_THREAD_TOKEN_UNCERTAIN')
        api.require(api.security.OpenProcessToken(api.kernel.GetCurrentProcess(), 8,
                                                 ctypes.byref(host_token)), 'OPEN_HOST_TOKEN')
        user_buffer = api.info(host_token, 1)
        user_sid = api.sid_string(ctypes.cast(user_buffer, ctypes.POINTER(W.LPVOID)).contents.value)
        hr = api.userenv.CreateAppContainerProfile(profile, profile, 'Disposable CRC R16 fixed token probe',
                                                   None, 0, ctypes.byref(app_sid))
        if hr != 0:
            raise _ProbeFailure('CREATE_APPCONTAINER_PROFILE:HRESULT_' + str(hr & 0xffffffff))
        created_profile = True
        sid = api.sid_string(app_sid)
        profile_path = W.LPWSTR()
        if api.userenv.GetAppContainerFolderPath(sid, ctypes.byref(profile_path)) != 0:
            raise _ProbeFailure('TEMPORARY_APPCONTAINER_FOLDER_UNAVAILABLE')
        try:
            profile_folder = profile_path.value
        finally:
            api.ole.CoTaskMemFree(profile_path)
        # These exact paths belong to TemporaryDirectory in the caller.
        for target in (public.parent.parent, public.parent, public):
            api.temporary_acl(target, user_sid, sid)
        for target in (private.parent, private):
            api.temporary_acl(target, user_sid)
        before_public = api.read(public)
        before_private = api.read(private)
        result['host_control'].update(public_readable_before=before_public['data'] == public_data,
                                      private_readable_before=before_private['data'] == private_data)
        if not all(result['host_control'].values()):
            raise _ProbeFailure('HOST_BEFORE_CONTROL_FAILED')
        system = ctypes.create_unicode_buffer(32768)
        length = api.kernel.GetSystemDirectoryW(system, len(system))
        if not 0 < length < len(system):
            raise _ProbeFailure('SYSTEM_DIRECTORY_UNAVAILABLE')
        executable = str(Path(system.value) / 'cmd.exe')
        result['process']['fixed_executable_sha256'] = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
        command = ctypes.create_unicode_buffer('"' + executable + '" /d /q /c exit 0')
        environment_values = {'SystemRoot': str(Path(system.value).parent),
                              'WINDIR': str(Path(system.value).parent),
                              'USERPROFILE': profile_folder, 'LOCALAPPDATA': profile_folder,
                              'APPDATA': profile_folder, 'TEMP': profile_folder, 'TMP': profile_folder}
        result['process']['environment_keys'] = sorted(environment_values, key=str.casefold)
        environment = ctypes.create_unicode_buffer('\0'.join(key + '=' + environment_values[key]
            for key in sorted(environment_values, key=str.casefold)) + '\0\0')
        size = ctypes.c_size_t()
        api.kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        if not 0 < size.value < 1048576:
            raise _ProbeFailure('PROCESS_ATTRIBUTE_SIZE_INVALID')
        attributes = ctypes.create_string_buffer(size.value)
        api.require(api.kernel.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)), 'INITIALIZE_PROCESS_ATTRIBUTES')
        attributes_initialized = True
        capabilities = _SECURITY_CAPABILITIES(app_sid, None, 0, 0)
        api.require(api.kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009,
            ctypes.byref(capabilities), ctypes.sizeof(capabilities), None, None), 'SET_EMPTY_CAPABILITIES')
        startup = _STARTUPINFOEX()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.StartupInfo.dwFlags = 1  # STARTF_USESHOWWINDOW, SW_HIDE
        startup.lpAttributeList = ctypes.cast(attributes, W.LPVOID)
        api.require(api.kernel.CreateProcessW(executable, command, None, None, False,
            0x08080404, environment, system.value, ctypes.byref(startup), ctypes.byref(process)), 'CREATE_FIXED_SUSPENDED_CHILD')
        result['process']['created_suspended'] = True
        api.require(api.security.OpenProcessToken(process.hProcess, 0x000a,
                                                  ctypes.byref(child_token)), 'OPEN_CHILD_TOKEN')
        result['token'] = api.token_observation(child_token, sid)
        if (not result['token']['is_appcontainer'] or result['token']['capability_count'] != 0
                or not result['token']['appcontainer_sid_matches_profile']):
            raise _ProbeFailure('CHILD_TOKEN_NOT_EXACT_EMPTY_CAPABILITY_APPCONTAINER')
        api.require(api.security.ImpersonateLoggedOnUser(child_token), 'IMPERSONATE_LIVE_CHILD_TOKEN')
        impersonating = True
        try:
            api.require(api.security.OpenThreadToken(api.kernel.GetCurrentThread(), 8, True,
                                                     ctypes.byref(thread_token)), 'OPEN_IMPERSONATED_THREAD_TOKEN')
            if api.token_observation(thread_token, sid) != result['token']:
                raise _ProbeFailure('THREAD_TOKEN_DIFFERS_FROM_CHILD_APPCONTAINER')
            public_check = api.read(public)
            private_check = api.read(private)
            result['access_checks'] = {'public_open_succeeded': public_check['opened'],
                'public_read_matches': public_check['data'] == public_data,
                'public_winerror': public_check['winerror'],
                'private_open_succeeded': private_check['opened'],
                'private_winerror': private_check['winerror']}
        finally:
            # Never perform subsequent host I/O if the security context cannot
            # be restored. The outer finally also avoids cleanup I/O in that case.
            if not api.security.RevertToSelf():
                unreverted = True
                raise _ProbeFailure('REVERT_TO_SELF_FAILED_NO_FURTHER_IO')
            impersonating = False
            result['cleanup']['reverted_to_self'] = True
        after_public = api.read(public)
        after_private = api.read(private)
        result['host_control'].update(public_readable_after=after_public['data'] == public_data,
                                      private_readable_after=after_private['data'] == private_data)
        if (not result['access_checks']['public_read_matches']
                or result['access_checks']['private_open_succeeded']
                or result['access_checks']['private_winerror'] != 5
                or not all(result['host_control'].values())):
            raise _ProbeFailure('KERNEL_READ_DENIAL_AND_HOST_CONTROLS_NOT_PROVEN')
        if api.kernel.ResumeThread(process.hThread) == 0xffffffff:
            raise _ProbeFailure('RESUME_FIXED_EXIT_CHILD_FAILED')
        if api.kernel.WaitForSingleObject(process.hProcess, int(timeout_seconds * 1000)) != 0:
            raise _ProbeFailure('FIXED_CHILD_DID_NOT_EXIT_WITHIN_BOUND')
        code = W.DWORD()
        api.require(api.kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code)), 'READ_FIXED_CHILD_EXIT')
        result['process']['exit_code'] = code.value
        if code.value != 0:
            raise _ProbeFailure('FIXED_EXIT_CHILD_NONZERO')
        result.update(os_probe_status='VERIFIED_READ_DENIAL', reason='TEMPORARY_LIVE_CHILD_TOKEN_DENIES_PRIVATE_COPY')
    finally:
        if unreverted:
            # No filesystem/profile cleanup under an uncertain impersonation.
            # Raise to the caller; this must not become a usable probe receipt.
            raise _ProbeFailure('REVERT_TO_SELF_FAILED_NO_FURTHER_IO')
        if impersonating:
            api.require(api.security.RevertToSelf(), 'EMERGENCY_REVERT_TO_SELF')
            result['cleanup']['reverted_to_self'] = True
        if process.hProcess:
            if api.kernel.WaitForSingleObject(process.hProcess, 0) != 0:
                api.require(api.kernel.TerminateProcess(process.hProcess, 1), 'TERMINATE_FIXED_CHILD')
                if api.kernel.WaitForSingleObject(process.hProcess, 5000) != 0:
                    raise _ProbeFailure('FIXED_CHILD_CLEANUP_TIMEOUT')
        close_errors = []
        for handle in (thread_token, child_token, host_token, process.hThread, process.hProcess):
            try:
                api.close(handle)
            except _ProbeFailure as exc:
                close_errors.append(str(exc))
        result['cleanup']['process_handles_closed'] = not close_errors
        if attributes_initialized:
            api.kernel.DeleteProcThreadAttributeList(attributes)
        if created_profile:
            hr = api.userenv.DeleteAppContainerProfile(profile)
            if hr != 0:
                # Microsoft's API contract requests another cleanup attempt if
                # deletion leaves the per-user profile in an uncertain state.
                hr = api.userenv.DeleteAppContainerProfile(profile)
            result['cleanup']['profile_deleted'] = hr == 0
            if hr != 0:
                close_errors.append('DELETE_TEMPORARY_APPCONTAINER_PROFILE_FAILED')
        if app_sid:
            api.security.FreeSid(app_sid)
        if close_errors:
            raise _ProbeFailure('TEMPORARY_PROCESS_OR_PROFILE_CLEANUP_FAILED')


def probe_isolation(public_task_file, private_sentinel_file, *, timeout_seconds=5):
    """Observe a disposable Windows boundary; formal agent counting stays off.

    Input files must already exist. Only bounded copies in a newly owned
    temporary lane receive temporary ACLs. No command, executable, token,
    profile, receipt, or certification flag can be supplied by the caller.
    """
    result = _report()
    if os.name != 'nt':
        result['reason'] = 'WINDOWS_APPCONTAINER_REQUIRED'
        return result
    if type(timeout_seconds) not in {int, float} or not 0 < timeout_seconds <= 30:
        result['reason'] = 'TIMEOUT_MUST_BE_POSITIVE_AND_AT_MOST_30_SECONDS'
        return result
    lane = None
    try:
        public_path, public_data = _input(public_task_file)
        private_path, private_data = _input(private_sentinel_file)
        if public_path.samefile(private_path):
            raise _ProbeFailure('PUBLIC_AND_PRIVATE_INPUTS_MUST_BE_DISTINCT')
        result['input_bindings'] = {'public_task_sha256': hashlib.sha256(public_data).hexdigest(),
                                    'private_sentinel_sha256': hashlib.sha256(private_data).hexdigest()}
        api = _Windows()
        lane = tempfile.TemporaryDirectory(prefix='crc-r16-token-lane-')
        root = Path(lane.name)
        (root / 'public').mkdir()
        (root / 'private').mkdir()
        public_copy = root / 'public/task.json'
        private_copy = root / 'private/sentinel.bin'
        public_copy.write_bytes(public_data)
        private_copy.write_bytes(private_data)
        _probe_windows(api, public_copy, private_copy, public_data, private_data, result, timeout_seconds)
        if public_path.read_bytes() != public_data or private_path.read_bytes() != private_data:
            raise _ProbeFailure('ORIGINAL_INPUT_CHANGED_DURING_PROBE')
    except _ProbeFailure as exc:
        if str(exc) == 'REVERT_TO_SELF_FAILED_NO_FURTHER_IO':
            # Do not delete files or perform any other I/O with an uncertain
            # thread context, including TemporaryDirectory's finalizer.
            if lane is not None:
                lane._finalizer.detach()
            raise
        result.update(os_probe_status='NOT_ISOLATED', reason=str(exc))
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        result.update(os_probe_status='NOT_ISOLATED', reason='LOCAL_PROBE_UNAVAILABLE:' + type(exc).__name__)
    finally:
        if lane is not None and lane._finalizer.alive:
            try:
                lane.cleanup()
                result['cleanup']['temporary_lane_removed'] = True
            except OSError:
                result.update(os_probe_status='NOT_ISOLATED', reason='TEMPORARY_LANE_CLEANUP_FAILED')
    return result
