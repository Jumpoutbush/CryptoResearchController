"""Bound a supervisor transport's process lifetime, not filesystem permissions.

Windows: start suspended, assign to a kill-on-close Job, then resume. Descendants
cannot outlive the parent-owned Job even when the direct child has already quit.
This does NOT certify the Windows sandbox's deny-read/network security boundary.
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
"""
import os
import signal
import subprocess


class ProcessTree:
    def __init__(self):
        self.process = None
        self.job = None
        if os.name == 'nt': self._create_job()

    def _create_job(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('ProcessTime', c.c_longlong), ('JobTime', c.c_longlong), ('Flags', w.DWORD),
                ('MinWorkingSet', c.c_size_t), ('MaxWorkingSet', c.c_size_t), ('ActiveProcesses', w.DWORD),
                ('Affinity', c.c_size_t), ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class Limits(c.Structure):
            _fields_ = [('Basic', Basic), ('IO', IO), ('ProcessMemory', c.c_size_t),
                ('JobMemory', c.c_size_t), ('PeakProcessMemory', c.c_size_t), ('PeakJobMemory', c.c_size_t)]
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL)):
            fn = getattr(self.kernel, name); fn.argtypes = args; fn.restype = result
        self.job = self.kernel.CreateJobObjectW(None, None)
        if not self.job: raise c.WinError(c.get_last_error())
        limits = Limits(); limits.Basic.Flags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway.
        if not self.kernel.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)):
            error = c.WinError(c.get_last_error()); self.close(); raise error

    def start(self, argv, **kwargs):
        try:
            self.process = subprocess.Popen(argv, **kwargs,
                creationflags=0x4 if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
            if os.name == 'nt':
                import ctypes as c
                if not self.kernel.AssignProcessToJobObject(self.job, int(self.process._handle)):
                    raise c.WinError(c.get_last_error())
                self._resume()
            return self.process
        except BaseException:
            # A failed assignment must never resume the suspended child.
            if self.process is not None and self.process.poll() is None:
                self.process.kill(); self.process.wait(timeout=10)
            self.close()
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream is not None: stream.close()
            raise

    def _resume(self):
        import ctypes as c
        from ctypes import wintypes as w
        class ThreadEntry(c.Structure):
            _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('threadID', w.DWORD),
                ('ownerPID', w.DWORD), ('basePriority', w.LONG), ('deltaPriority', w.LONG), ('flags', w.DWORD)]
        kernel = self.kernel
        for name, args, result in (
            ('CreateToolhelp32Snapshot', [w.DWORD, w.DWORD], w.HANDLE),
            ('Thread32First', [w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            ('Thread32Next', [w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            ('OpenThread', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ('ResumeThread', [w.HANDLE], w.DWORD)):
            fn = getattr(kernel, name); fn.argtypes = args; fn.restype = result
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD.
        if snapshot == c.c_void_p(-1).value: raise c.WinError(c.get_last_error())
        try:
            entry = ThreadEntry(); entry.dwSize = c.sizeof(entry)
            available = kernel.Thread32First(snapshot, c.byref(entry))
            while available:
                if entry.ownerPID == self.process.pid:
                    handle = kernel.OpenThread(2, False, entry.threadID)  # THREAD_SUSPEND_RESUME.
                    if not handle: raise c.WinError(c.get_last_error())
                    try:
                        if kernel.ResumeThread(handle) == 0xffffffff: raise c.WinError(c.get_last_error())
                        return
                    finally: kernel.CloseHandle(handle)
                available = kernel.Thread32Next(snapshot, c.byref(entry))
            raise OSError('Suspended supervisor thread not found')
        finally: kernel.CloseHandle(snapshot)

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job); self.job = None
        elif os.name != 'nt' and self.process is not None:
            try: os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        if self.process is not None:
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=10)
