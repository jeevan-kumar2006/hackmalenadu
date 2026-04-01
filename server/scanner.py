"""File system scanner — walks a directory and returns file metadata + content."""
import os
import re

MAX_FILE_SIZE = 512 * 1024  # 512 KB

SUPPORTED = {
    '.py', '.c', '.h', '.cpp', '.hpp', '.cc', '.cxx',
    '.js', '.jsx', '.ts', '.tsx', '.mjs',
    '.java', '.rs', '.go', '.rb', '.swift', '.kt', '.scala',
    '.md', '.markdown', '.txt', '.rst',
    '.sh', '.bash', '.zsh', '.ps1',
    '.html', '.css', '.scss', '.less', '.sql',
    '.r', '.R', '.jl', '.lua', '.vim', '.el', '.ex', '.exs',
    '.zig', '.nim', '.dart', '.cu', '.cuh'
}

BINARY = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', '.xz',
    '.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.bin', '.dat',
    '.mp3', '.mp4', '.avi', '.mkv', '.wav', '.flac',
    '.pyc', '.pyo', '.class', '.jar', '.war', '.whl', '.egg',
    '.ttf', '.otf', '.woff', '.woff2', '.eot'
}

IGNORE_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules',
    '.venv', 'venv', 'env', '.env', '.tox', '.mypy_cache',
    '.pytest_cache', '.idea', '.vscode', 'dist', 'build',
    '.next', '.nuxt', 'target', 'out', '.cache', 'coverage'
}


def scan_directory(root_path, progress_cb=None):
    """
    Walk root_path and yield file dicts.
    progress_cb(scanned_count, total_estimate) called periodically.
    """
    root_path = os.path.abspath(root_path)
    if not os.path.isdir(root_path):
        raise FileNotFoundError(f"Directory not found: {root_path}")

    # First pass: count total files for progress
    total = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SUPPORTED:
                total += 1

    scanned = 0
    results = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SUPPORTED:
                continue
            full_path = os.path.join(dirpath, fn)
            try:
                fsize = os.path.getsize(full_path)
                if fsize > MAX_FILE_SIZE:
                    scanned += 1
                    if progress_cb:
                        progress_cb(scanned, total)
                    continue
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                rel_dir = os.path.relpath(dirpath, root_path)
                if rel_dir == '.':
                    rel_dir = ''
                mod_time = os.path.getmtime(full_path)
                from datetime import datetime
                modified = datetime.fromtimestamp(mod_time).isoformat()
                results.append({
                    'path': full_path,
                    'filename': fn,
                    'extension': ext,
                    'directory': rel_dir,
                    'size': fsize,
                    'modified': modified,
                    'content': content
                })
            except (OSError, PermissionError) as e:
                pass
            scanned += 1
            if progress_cb and scanned % 5 == 0:
                progress_cb(scanned, total)

    if progress_cb:
        progress_cb(scanned, total)
    return results
