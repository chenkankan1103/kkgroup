#!/usr/bin/env python3
"""
Find all related files for a given set of changed files.
Includes: imports, same module, test files, shared utils, reverse imports.
"""
import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.resolve()

def get_changed_files(ref_spec: str) -> list[Path]:
    """Get files changed in the push ref spec."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', ref_spec],
            cwd=ROOT, capture_output=True, text=True, check=True
        )
        return [ROOT / f for f in result.stdout.strip().split('\n') if f and (ROOT / f).exists()]
    except subprocess.CalledProcessError:
        return []

def get_all_py_files() -> list[Path]:
    """Get all .py files in project (excluding venv, .claude/worktrees, etc.)."""
    exclude_dirs = {'.venv', 'venv', 'env', '__pycache__', '.git', '.claude', 'chroma_db', 'graphify-out', 'game', 'tools', 'docs_and_tests', '.claude-flow', 'node_modules'}
    files = []
    for root, dirs, filenames in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in filenames:
            if f.endswith('.py'):
                files.append(Path(root) / f)
    return files

def find_python_imports(file_path: Path) -> set[Path]:
    """Find all local python imports from a file."""
    imports = set()
    try:
        content = file_path.read_text(encoding='utf-8')
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('from ') or line.startswith('import '):
                parts = line.replace('from ', '').replace('import ', '').split()
                if parts:
                    mod = parts[0].split('.')[0]
                    for root in [ROOT / 'cogs', ROOT / 'shared', ROOT / 'web', ROOT / 'scheduled_tasks', ROOT / 'scripts', ROOT / 'bots']:
                        mod_path = root / mod.replace('.', '/')
                        for ext in ['.py', '/__init__.py']:
                            candidate = mod_path.with_suffix('') if ext == '.py' else mod_path / '__init__.py'
                            if candidate.exists():
                                imports.add(candidate)
    except Exception:
        pass
    return imports

def find_reverse_imports(file_path: Path, all_py_files: list[Path]) -> set[Path]:
    """Find files that import this file."""
    rev = set()
    mod_name = file_path.relative_to(ROOT).with_suffix('').as_posix().replace('/', '.')
    for py_file in all_py_files:
        if py_file == file_path:
            continue
        try:
            content = py_file.read_text(encoding='utf-8')
            if mod_name in content or file_path.stem in content:
                rev.add(py_file)
        except Exception:
            pass
    return rev

def find_same_module_files(file_path: Path, all_py_files: list[Path]) -> set[Path]:
    """Find files in the same directory/module."""
    same = set()
    parent = file_path.parent
    for py_file in all_py_files:
        if py_file.parent == parent and py_file != file_path:
            same.add(py_file)
    return same

def find_test_files(file_path: Path, all_py_files: list[Path]) -> set[Path]:
    """Find test files for this file."""
    tests = set()
    stem = file_path.stem
    for py_file in all_py_files:
        if py_file.name.startswith(f'test_{stem}') or py_file.name.startswith(f'{stem}_test'):
            tests.add(py_file)
        if 'tests' in py_file.parts and stem in py_file.name:
            tests.add(py_file)
    return tests

def main():
    stdin_data = sys.stdin.read().strip()
    ref_spec = None
    if stdin_data:
        parts = stdin_data.split()
        if len(parts) >= 4:
            local_sha, remote_sha = parts[1], parts[3]
            if remote_sha != '0' * 40:
                ref_spec = f'{remote_sha}..{local_sha}'
            else:
                ref_spec = local_sha

    if ref_spec:
        changed = get_changed_files(ref_spec)
    else:
        # Fallback: check staged or all uncommitted
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD'],
                cwd=ROOT, capture_output=True, text=True, check=True
            )
            changed = [ROOT / f for f in result.stdout.strip().split('\n') if f and (ROOT / f).exists()]
        except subprocess.CalledProcessError:
            changed = []

    if not changed:
        print(json.dumps([]))
        return

    all_py = get_all_py_files()
    related = set(changed)

    for f in changed:
        if f.suffix == '.py':
            related |= find_python_imports(f)
            related |= find_reverse_imports(f, all_py)
            related |= find_same_module_files(f, all_py)
            related |= find_test_files(f, all_py)

    # Common shared files that are often relevant
    shared_candidates = [
        ROOT / 'shared' / 'utils' / 'view_registry.py',
        ROOT / 'shared' / 'utils' / 'embed_views.py',
        ROOT / 'shared' / 'utils' / 'fortress_system.py',
        ROOT / 'shared' / 'db' / 'db_adapter.py',
        ROOT / 'shared' / 'db' / 'sheet_driven_db.py',
        ROOT / 'shared' / 'db' / 'ai_memory.py',
        ROOT / 'cogs' / 'common' / 'kkcoin.py',
        ROOT / 'cogs' / 'common' / 'base_cog.py',
        ROOT / 'config' / 'commands_registry.json',
        ROOT / 'config' / 'discord_commands_registry.json',
    ]
    for f in changed:
        if 'cogs' in f.parts or 'shared' in f.parts:
            related.update(p for p in shared_candidates if p.exists())

    result = [str(f.relative_to(ROOT)) for f in related if f.exists()]
    print(json.dumps(sorted(set(result))))

if __name__ == '__main__':
    main()