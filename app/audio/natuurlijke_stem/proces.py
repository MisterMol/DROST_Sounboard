"""Beheer alleen het eigen hulpproces; nooit andere programma's beëindigen."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys


class EigenProcesgroep:
    """Windows sluit onze worker ook af als de hoofdapp onverwacht wegvalt."""
    def __init__(self, process):
        self.handle=None
        if os.name != 'nt': return
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel=k
        class Basic(ctypes.Structure):
            _fields_=[('per_process',ctypes.c_int64),('per_job',ctypes.c_int64),
                      ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                      ('active',wintypes.DWORD),('affinity',ctypes.c_size_t),
                      ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                      ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]; k.CreateJobObjectW.restype=wintypes.HANDLE
        k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        k.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=k.CreateJobObjectW(None,None)
        if not handle: raise OSError(ctypes.get_last_error(),'Procesgroep aanmaken mislukt.')
        limits=Extended(); limits.basic.flags=0x2000
        if (not k.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits))
                or not k.AssignProcessToJobObject(handle,int(process._handle))):
            error=ctypes.get_last_error(); k.CloseHandle(handle)
            raise OSError(error,'De stemmotor kon niet aan de app worden gekoppeld.')
        self.handle=handle

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle=None


def start_eigen_worker(executable: Path, model: Path, error_stream):
    env=dict(os.environ)
    for key in list(env):
        if key.startswith(('_PYI_', 'PYTHON')): env.pop(key,None)
    env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    env['OMP_NUM_THREADS']='1'; env['MKL_NUM_THREADS']='1'
    if getattr(sys,'frozen',False):
        root=Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent)).resolve()
        env['PATH']=os.pathsep.join(part for part in env.get('PATH','').split(os.pathsep)
                                   if part and not Path(part).resolve().is_relative_to(root))
    old_dll=None
    if os.name=='nt' and getattr(sys,'frozen',False):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetDllDirectoryW.argtypes=[wintypes.DWORD,wintypes.LPWSTR]
        kernel.SetDllDirectoryW.argtypes=[wintypes.LPCWSTR]
        buffer=ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(buffer),buffer)
        old_dll=buffer.value
        kernel.SetDllDirectoryW(None)
    try:
        return subprocess.Popen([str(executable),'--model',str(model),'--parent',str(os.getpid())],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_stream,
                                bufsize=0, cwd=str(executable.parent), env=env,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    finally:
        if old_dll is not None: kernel.SetDllDirectoryW(old_dll or None)
