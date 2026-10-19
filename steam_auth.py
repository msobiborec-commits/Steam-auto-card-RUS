import ctypes
from ctypes import wintypes
import subprocess
import re
import requests

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40

kernel32 = ctypes.windll.kernel32

TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(wintypes.ULONG)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', ctypes.c_char * 260)
    ]

def get_process_pids_by_name(process_name):
    pids = []
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1 or snapshot == 0xFFFFFFFFFFFFFFFF:
        return pids
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        target = process_name.lower()
        target_exe = target if target.endswith('.exe') else (target + '.exe')
        while True:
            name = entry.szExeFile.decode('utf-8', errors='ignore').lower()
            if name == target or name == target_exe:
                pids.append(entry.th32ProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return pids

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]

def get_steam_cookies():
    """
    Automatically extracts live steamLoginSecure cookie from running steamwebhelper processes.
    """
    pids = get_process_pids_by_name("steamwebhelper")
    if not pids:
        return None

    # Regex to match steamLoginSecure JWT or session token
    # Format: 7656119...||JWT or URL-encoded 7656119...%7C%7CJWT
    jwt_pattern = re.compile(rb'(7656\d{13}(?:%7C%7C|\|\|)[A-Za-z0-9_\-\.]+)')
    
    candidates = []
    for pid in pids:
        hProcess = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not hProcess:
            continue
        try:
            address = 0
            mbi = MEMORY_BASIC_INFORMATION()
            mbi_size = ctypes.sizeof(mbi)
            while kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size):
                if mbi.State == MEM_COMMIT and mbi.Protect in (PAGE_READWRITE, PAGE_READONLY, PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE):
                    # Skip extremely large buffers to keep it fast
                    if mbi.RegionSize <= 16 * 1024 * 1024:
                        buf = ctypes.create_string_buffer(mbi.RegionSize)
                        bytesRead = ctypes.c_size_t()
                        if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(mbi.BaseAddress), buf, mbi.RegionSize, ctypes.byref(bytesRead)):
                            data = buf.raw[:bytesRead.value]
                            if b'steamLoginSecure' in data:
                                idx = 0
                                while True:
                                    pos = data.find(b'steamLoginSecure', idx)
                                    if pos == -1:
                                        break
                                    chunk = data[pos:pos+1500]
                                    matches = jwt_pattern.findall(chunk)
                                    for m in matches:
                                        val = m.decode('ascii', errors='ignore')
                                        val = val.replace('%7C%7C', '||')
                                        # Valid steamLoginSecure token has 2 parts: steamid||JWT, and JWT has 3 parts separated by dot
                                        parts = val.split('||')
                                        if len(parts) == 2 and len(parts[1].split('.')) == 3:
                                            candidates.append(val)
                                    idx = pos + 16
                address += mbi.RegionSize
                if address >= 0x7FFFFFFFFFFF or candidates:
                    break
            if candidates:
                break
        finally:
            kernel32.CloseHandle(hProcess)
            
    if not candidates:
        return None
    
    # Return first valid token
    best_cookie = candidates[0]
    return {
        'steamLoginSecure': best_cookie,
        'Steam_Language': 'russian'
    }

if __name__ == '__main__':
    cookies = get_steam_cookies()
    print("Found cookies:", bool(cookies))
    if cookies:
        print("Token sample:", cookies['steamLoginSecure'][:35] + "...")
