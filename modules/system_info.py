# system_info.py
# Module to gather and store system hardware and environment information for BPCSS workflow.
# Focuses on gathering CPU, RAM, OS, GPU, PATH information, CUDA, and GROMACS setup.
# Avoids storing PII. Stores data in ~/.bpcss/system_info.json and detects changes between runs.

import os
import platform
import json
import subprocess
from pathlib import Path
import shutil
import sys

CONFIG_DIR = Path.home() / ".bpcss"
INFO_FILE = CONFIG_DIR / "system_info.json"


def get_cpu_info():
    """Gather CPU model, architecture, flags, and interpret capabilities for GROMACS optimizations."""
    info = {}
    # Architecture
    info['machine'] = platform.machine()
    info['processor'] = platform.processor()
    # /proc/cpuinfo parsing
    flags = []
    try:
        with open('/proc/cpuinfo') as f:
            model_name = None
            for line in f:
                if line.startswith('model name') and model_name is None:
                    model_name = line.split(':', 1)[1].strip()
                if line.startswith('flags') and not flags:
                    flags = line.split(':', 1)[1].strip().split()
                if model_name and flags:
                    break
            if model_name:
                info['model_name'] = model_name
            if flags:
                info['flags'] = flags
    except Exception:
        pass
    # Interpret CPU flags for GROMACS
    if flags:
        info['capabilities'] = interpret_cpu_flags(flags)
    return info


def interpret_cpu_flags(flags):
    """Interpret CPU flags to determine SIMD capabilities and recommendations for GROMACS."""
    caps = {}
    flag_set = set(flags)
    descriptions = {
        'sse4_1': 'SSE4.1: Basic SIMD instructions, minimal speedup for GROMACS.',
        'sse4_2': 'SSE4.2: Improved string and CRC instructions; minor benefit.',
        'avx': 'AVX: 256-bit SIMD; good speedup if GROMACS built with AVX support.',
        'avx2': 'AVX2: Enhanced 256-bit SIMD integer operations; significant speedup.',
        'avx512f': 'AVX-512: 512-bit SIMD; highest speedup if available and supported by build.',
        'fma': 'FMA: Fused Multiply-Add; important for optimized math routines.',
        'bmi1': 'BMI1: Bit Manipulation Instruction Set 1; may help certain operations.',
        'bmi2': 'BMI2: Bit Manipulation Instruction Set 2.',
    }
    supported = [flag for flag in descriptions if flag in flag_set]
    caps['supported_flags'] = supported
    # Determine highest SIMD level
    simd_levels = []
    if 'avx512f' in flag_set and 'fma' in flag_set:
        simd_levels.append('AVX512')
    if 'avx2' in flag_set and 'fma' in flag_set:
        simd_levels.append('AVX2')
    if 'avx' in flag_set:
        simd_levels.append('AVX')
    if 'sse4_1' in flag_set:
        simd_levels.append('SSE4.1')
    caps['simd_levels'] = simd_levels
    # Recommendation highest
    if 'AVX512' in simd_levels:
        caps['recommended_cpu_build'] = 'GROMACS build with AVX-512 support'
    elif 'AVX2' in simd_levels:
        caps['recommended_cpu_build'] = 'GROMACS build with AVX2 support'
    elif 'AVX' in simd_levels:
        caps['recommended_cpu_build'] = 'GROMACS build with AVX support'
    elif 'SSE4.1' in simd_levels:
        caps['recommended_cpu_build'] = 'GROMACS build with SSE4.1 support'
    else:
        caps['recommended_cpu_build'] = 'No advanced SIMD detected; use generic build or consider upgrading CPU for performance.'
    caps['descriptions'] = {flag: descriptions.get(flag, '') for flag in supported}
    return caps


def get_memory_info():
    """Gather total RAM in KB."""
    info = {}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal'):
                    parts = line.split()
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
    """Detect GPUs: NVIDIA, AMD, Intel. Check availability via nvidia-smi, rocminfo, lspci fallback."""
    gpus = []
    # NVIDIA detection
    out, _ = _run_command(['which', 'nvidia-smi'])
    if out:
        out2, _ = _run_command(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'])
        if out2:
            for line in out2.splitlines():
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    gpus.append({'vendor': 'NVIDIA', 'name': parts[0], 'driver': parts[1]})
    # AMD detection via ROCm tools
    out, _ = _run_command(['which', 'rocminfo'])
    if out:
        out2, _ = _run_command(['rocminfo'])
        names = []
        if out2:
            for line in out2.splitlines():
                if 'Agent' in line and 'gfx' in line:
                    names.append(line.strip())
        if names:
            gpus.append({'vendor': 'AMD ROCm', 'details': names})
    else:
        out, _ = _run_command(['which', 'rocm-smi'])
        if out:
            out2, _ = _run_command(['rocm-smi', '-i'])
            details = out2.splitlines() if out2 else []
            gpus.append({'vendor': 'AMD ROCm', 'details': details})
    # Fallback: parse lspci for GPU entries
    out, _ = _run_command(['which', 'lspci'])
    if out:
        out2, _ = _run_command(['lspci'])
        if out2:
            for line in out2.splitlines():
                low = line.lower()
                if 'vga compatible controller' in low or '3d controller' in low:
                    if 'nvidia' in low:
                        continue
                    elif 'amd' in low or 'advanced micro devices' in low or 'radeon' in low:
                        gpus.append({'vendor': 'AMD/ATI', 'description': line.split(':', 1)[1].strip()})
                    elif 'intel' in low:
                        gpus.append({'vendor': 'Intel', 'description': line.split(':', 1)[1].strip()})
    return gpus


def get_cuda_info():
    """Check for CUDA Toolkit installation via nvcc."""
    info = {'installed': False}
    nvcc_path = shutil.which('nvcc')
    if nvcc_path:
        info['installed'] = True
        out, _ = _run_command(['nvcc', '--version'])
        if out:
            info['version_info'] = out.splitlines()[-1].strip()
    else:
        cuda_path = Path('/usr/local/cuda/bin/nvcc')
        if cuda_path.exists():
            info['installed'] = True
            out, _ = _run_command([str(cuda_path), '--version'])
            if out:
                info['version_info'] = out.splitlines()[-1].strip()
    return info


def check_gromacs_setup(interactive=True):
    """Check GROMACS availability: whether 'gmx' is in PATH or install exists but not sourced.
    If interactive, can attempt sourcing GMXRC scripts and prompt user to make permanent.
    After sourcing, update PATH in current process for immediate detection."""
    info = {'gmx_in_path': False, 'possible_install_paths': [], 'gmrc_scripts': []}
    gmx_path = shutil.which('gmx')
    if gmx_path:
        info['gmx_in_path'] = True
        info['gmx_path'] = gmx_path
        return info
    # Not in PATH: check common locations
    common_paths = [Path('/usr/local/gromacs/bin/gmx'), Path('/opt/gromacs/bin/gmx')]
    for p in common_paths:
        if p.exists() and os.access(p, os.X_OK):
            info['possible_install_paths'].append(str(p))
    # Check for GMXRC scripts
    common_rc = [Path('/usr/local/gromacs/bin/GMXRC'), Path('/opt/gromacs/bin/GMXRC')]
    for rc in common_rc:
        if rc.exists():
            info['gmrc_scripts'].append(str(rc))
    # If interactive and GMXRC scripts found, test sourcing
    if interactive and info['gmrc_scripts']:
        for rc in info['gmrc_scripts']:
            cmd = ['bash', '-c', f'source {rc} >/dev/null 2>&1 && command -v gmx']
            out, _ = _run_command(cmd)
            if out:
                print(f"Found GMXRC script at {rc}. After sourcing, 'gmx' is available at: {out}")
                resp = input("Do you want to add this source line to your shell rc for permanent access? [Y/n]: ").strip().lower()
                if resp == '' or resp.startswith('y'):
                    add_source_to_shell(rc)
                    # Update PATH in current process for immediate use
                    gmx_dir = str(Path(out).parent)
                    current_path = os.environ.get('PATH', '')
                    if gmx_dir not in current_path.split(os.pathsep):
                        os.environ['PATH'] = gmx_dir + os.pathsep + current_path
                    info['gmx_in_path'] = True
                    info['gmx_path'] = out
                else:
                    print("Skipping permanent source. You will need to source GMXRC manually or set PATH for GROMACS.")
    return info


def add_source_to_shell(rc_path):
    """Append source line to user's shell rc file."""
    shell = os.environ.get('SHELL', '')
    home = Path.home()
    if shell.endswith('bash'):
        rc_file = home / '.bashrc'
    elif shell.endswith('zsh'):
        rc_file = home / '.zshrc'
    else:
        rc_file = home / '.profile'
    line = f"\n# Source GROMACS environment\nsource {rc_path}\n"
    try:
        with open(rc_file, 'a') as f:
            f.write(line)
        print(f"Appended 'source {rc_path}' to {rc_file}")
    except Exception as e:
        print(f"Failed to append to {rc_file}: {e}")


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


def gather_info(interactive=True):
    """Gather all system info into a dict, including recommendations."""
    info = {}
    info['cpu'] = get_cpu_info()
    info['memory'] = get_memory_info()
    info['os'] = get_os_info()
    info['gpus'] = get_gpu_info()
    info['cuda'] = get_cuda_info()
    info['gromacs'] = check_gromacs_setup(interactive=interactive)
    info['path_entries'] = get_path_info()
    executables = ['gmx', 'python3', 'pip3', 'lspci', 'nvcc', 'rocminfo', 'rocm-smi']
    executables_status = check_executables(executables)
    # If gmx was added via sourcing, ensure executables_status updated
    if info['gromacs'].get('gmx_in_path'):
        executables_status['gmx'] = True
    info['executables'] = executables_status
    # Recommendations: CPU and GPU builds
    rec = {}
    cpu_cap = info['cpu'].get('capabilities', {})
    if cpu_cap.get('recommended_cpu_build'):
        rec['cpu'] = cpu_cap['recommended_cpu_build']
    # GPU recommendation
    gpu_list = info.get('gpus', [])
    cuda = info.get('cuda', {})
    gpu_recs = []
    for gpu in gpu_list:
        if gpu.get('vendor') == 'NVIDIA' and cuda.get('installed'):
            gpu_recs.append('GROMACS with CUDA GPU support')
        elif gpu.get('vendor') in ('AMD ROCm', 'AMD/ATI'):
            # Could check ROCm availability
            # If rocm detected?
            if shutil.which('rocminfo') or shutil.which('rocm-smi'):
                gpu_recs.append('GROMACS with ROCm GPU support')
    if gpu_recs:
        rec['gpu'] = gpu_recs
    info['recommendations'] = rec
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
    # Compare GPU list by vendor and identifier
    def gpu_identifier(g):
        vendor = g.get('vendor')
        name = g.get('name') or g.get('description') or (','.join(g.get('details')) if g.get('details') else None)
        return (vendor, name)
    prev_gpus = {gpu_identifier(g) for g in prev.get('gpus', [])}
    curr_gpus = {gpu_identifier(g) for g in curr.get('gpus', [])}
    if prev_gpus != curr_gpus:
        changes['gpus_changed'] = {'old': list(prev_gpus), 'new': list(curr_gpus)}
    # Compare CUDA installation
    prev_cuda = prev.get('cuda', {})
    curr_cuda = curr.get('cuda', {})
    if prev_cuda.get('installed') != curr_cuda.get('installed') or prev_cuda.get('version_info') != curr_cuda.get('version_info'):
        changes['cuda_changed'] = {'old': prev_cuda, 'new': curr_cuda}
    # Compare GROMACS setup
    prev_gmx = prev.get('gromacs', {})
    curr_gmx = curr.get('gromacs', {})
    if prev_gmx.get('gmx_in_path') != curr_gmx.get('gmx_in_path') or prev_gmx.get('possible_install_paths') != curr_gmx.get('possible_install_paths'):
        changes['gromacs_changed'] = {'old': prev_gmx, 'new': curr_gmx}
    # Compare executables availability
    prev_exe = prev.get('executables', {})
    curr_exe = curr.get('executables', {})
    exe_changes = {}
    for exe in curr_exe:
        if prev_exe.get(exe) != curr_exe.get(exe):
            exe_changes[exe] = {'old': prev_exe.get(exe), 'new': curr_exe.get(exe)}
    if exe_changes:
        changes['executables_changed'] = exe_changes
    # Compare recommendations
    prev_rec = prev.get('recommendations', {})
    curr_rec = curr.get('recommendations', {})
    if prev_rec != curr_rec:
        changes['recommendations_changed'] = {'old': prev_rec, 'new': curr_rec}
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
    interactive = True
    curr = gather_info(interactive=interactive)
    prev = load_previous_info()
    changes = compare_info(prev, curr)
    if prompt_user_for_changes(changes):
        save_info(curr)
    else:
        print("Stored system info left unchanged.")


if __name__ == '__main__':
    main()

