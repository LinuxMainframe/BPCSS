# system_info.py
# Module to gather and store system hardware and environment information for BPCSS workflow.
# Focuses on gathering CPU, RAM, OS, GPU, PATH information.
# Avoids storing PII. Stores data in ~/.bpcss/system_info.json and detects changes between runs.

import os
import platform
import json
import subprocess
from pathlib import Path
import shutil

CONFIG_DIR = Path.home() / ".bpcss"
INFO_FILE = CONFIG_DIR / "system_info.json"


def get_cpu_info():
    """Gather CPU model, architecture, and flags."""
    info = {}
    # Architecture
    info['machine'] = platform.machine()
    info['processor'] = platform.processor()
    # /proc/cpuinfo parsing
    try:
        with open('/proc/cpuinfo') as f:
            model_name = None
            flags = None
            for line in f:
                if line.startswith('model name') and model_name is None:
                    model_name = line.split(':', 1)[1].strip()
                if line.startswith('flags') and flags is None:
                    flags = line.split(':', 1)[1].strip().split()
                if model_name and flags:
                    break
            if model_name:
                info['model_name'] = model_name
            if flags:
                info['flags'] = flags
    except Exception:
        pass
    return info


def get_memory_info():
    """Gather total RAM in KB."""
    info = {}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal'):
                    parts = line.split()
                    # e.g., MemTotal:       16384256 kB
                    if len(parts) >= 2:
                        info['MemTotal_kB'] = int(parts[1])
                    break
    except Exception:
        pass
    return info


def get_os_info():
    """Gather Linux distribution info from /etc/os-release."""
    info = {}
    try:
        with open('/etc/os-release') as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    v = v.strip().strip('"')
                    if k in ('NAME', 'VERSION', 'ID', 'VERSION_ID'):
                        info[k] = v
    except Exception:
        pass
    # Kernel version
    info['kernel'] = platform.release()
    return info


def _run_command(cmd):
    """Run a command and return (stdout, stderr), or (None, None) if fails."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout.strip(), result.stderr.strip()
    except Exception:
        return None, None


def get_gpu_info():
    """Detect GPUs: NVIDIA, AMD, Intel. Check availability via nvidia-smi, lspci fallback."""
    gpus = []
    # Check NVIDIA via nvidia-smi
    out, err = _run_command(['which', 'nvidia-smi'])
    if out:
        out2, _ = _run_command(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'])
        if out2:
            for line in out2.splitlines():
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    gpus.append({'vendor': 'NVIDIA', 'name': parts[0], 'driver': parts[1]})
    # TODO: AMD detection (rocm-smi?)
    # Fallback: parse lspci for GPU entries
    out, _ = _run_command(['which', 'lspci'])
    if out:
        out2, _ = _run_command(['lspci'])
        if out2:
            for line in out2.splitlines():
                low = line.lower()
                if 'vga compatible controller' in low or '3d controller' in low:
                    if 'nvidia' in low:
                        continue  # already handled
                    elif 'amd' in low or 'advanced micro devices' in low or 'radeon' in low:
                        gpus.append({'vendor': 'AMD/ATI', 'description': line.split(':', 1)[1].strip()})
                    elif 'intel' in low:
                        gpus.append({'vendor': 'Intel', 'description': line.split(':', 1)[1].strip()})
    return gpus


def get_path_info():
    """Gather PATH entries and check existence."""
    paths = os.environ.get('PATH', '').split(os.pathsep)
    info = []
    for p in paths:
        exists = os.path.isdir(p)
        info.append({'path': p, 'exists': exists})
    return info


def check_executables(executables):
    """Check if executables are in PATH."""
    found = {}
    for exe in executables:
        path = shutil.which(exe)
        found[exe] = bool(path)
    return found


def gather_info():
    """Gather all system info into a dict."""
    info = {}
    info['cpu'] = get_cpu_info()
    info['memory'] = get_memory_info()
    info['os'] = get_os_info()
    info['gpus'] = get_gpu_info()
    info['path_entries'] = get_path_info()
    # Example executables to check; adjust per workflow
    executables = ['gmx', 'python3', 'pip3', 'lspci']
    info['executables'] = check_executables(executables)
    # Permissions: check write access to config dir
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        writable = os.access(CONFIG_DIR, os.W_OK)
    except Exception:
        writable = False
    info['config_dir'] = {'path': str(CONFIG_DIR), 'writable': writable}
    return info


def load_previous_info():
    """Load previous info from INFO_FILE, or return None if not exists."""
    if INFO_FILE.exists():
        try:
            with open(INFO_FILE) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def compare_info(prev, curr):
    """Compare two info dicts. Return dict of changes."""
    changes = {}
    if not prev:
        changes['initial_run'] = True
        return changes
    # Compare CPU model
    prev_cpu = prev.get('cpu', {})
    curr_cpu = curr.get('cpu', {})
    if prev_cpu.get('model_name') != curr_cpu.get('model_name'):
        changes['cpu_model_changed'] = {'old': prev_cpu.get('model_name'), 'new': curr_cpu.get('model_name')}
    # Compare memory
    if prev.get('memory', {}).get('MemTotal_kB') != curr.get('memory', {}).get('MemTotal_kB'):
        changes['memory_changed'] = {'old': prev.get('memory', {}).get('MemTotal_kB'), 'new': curr.get('memory', {}).get('MemTotal_kB')}
    # Compare GPU list by names
    prev_gpus = { (g.get('vendor'), g.get('name', g.get('description'))) for g in prev.get('gpus', []) }
    curr_gpus = { (g.get('vendor'), g.get('name', g.get('description'))) for g in curr.get('gpus', []) }
    if prev_gpus != curr_gpus:
        changes['gpus_changed'] = {'old': list(prev_gpus), 'new': list(curr_gpus)}
    # Compare executables availability
    prev_exe = prev.get('executables', {})
    curr_exe = curr.get('executables', {})
    exe_changes = {}
    for exe in curr_exe:
        if prev_exe.get(exe) != curr_exe.get(exe):
            exe_changes[exe] = {'old': prev_exe.get(exe), 'new': curr_exe.get(exe)}
    if exe_changes:
        changes['executables_changed'] = exe_changes
    # OS changes
    prev_os = prev.get('os', {})
    curr_os = curr.get('os', {})
    for key in ('NAME', 'VERSION_ID', 'kernel'):
        if prev_os.get(key) != curr_os.get(key):
            changes.setdefault('os_changed', {})[key] = {'old': prev_os.get(key), 'new': curr_os.get(key)}
    # PATH entries count change
    prev_paths = {e['path'] for e in prev.get('path_entries', []) if e.get('exists')}
    curr_paths = {e['path'] for e in curr.get('path_entries', []) if e.get('exists')}
    if prev_paths != curr_paths:
        changes['path_entries_changed'] = {'old_count': len(prev_paths), 'new_count': len(curr_paths)}
    return changes


def prompt_user_for_changes(changes):
    """Prompt user about detected changes. Returns True if user wants to update stored info."""
    if not changes:
        print("No changes detected in system configuration.")
        return False
    if 'initial_run' in changes:
        print("Initial run: no previous system info found. Storing current configuration.")
        return True
    print("Detected changes in system configuration:")
    for key, val in changes.items():
        print(f"- {key}: {val}")
    resp = input("Do you want to update stored system info? [Y/n]: ").strip().lower()
    return (resp == '' or resp.startswith('y'))


def save_info(info):
    """Save current info to INFO_FILE."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(INFO_FILE, 'w') as f:
            json.dump(info, f, indent=2)
        print(f"System info saved to {INFO_FILE}")
    except Exception as e:
        print(f"Failed to save system info: {e}")


def main():
    curr = gather_info()
    prev = load_previous_info()
    changes = compare_info(prev, curr)
    if prompt_user_for_changes(changes):
        save_info(curr)
    else:
        print("Stored system info left unchanged.")


if __name__ == '__main__':
    main()
