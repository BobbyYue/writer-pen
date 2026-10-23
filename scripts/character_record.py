#!/usr/bin/env python3
"""Preserve local character notes; integrity checks do not assess literary quality."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


def digest(data):
    return hashlib.sha256(data).hexdigest()


def seal(source, directory, record_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', record_id):
        raise ValueError('Use a short record id with letters, digits, underscores or hyphens.')
    data = Path(source).read_bytes()
    if not data.decode('utf-8').strip():
        raise ValueError('Character analysis is empty.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / (record_id + '.md')
    manifest = directory / (record_id + '.record.json')
    if snapshot.exists() or snapshot.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise FileExistsError('Record id already exists; choose a new version, never overwrite.')
    record = dict(format_version=1, record_id=record_id, snapshot=snapshot.name,
                  created_at=datetime.now(timezone.utc).isoformat(),
                  sha256=digest(data), bytes=len(data))
    created_snapshot = False
    try:
        with snapshot.open('xb') as handle:
            created_snapshot = True
            handle.write(data)
        with manifest.open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    except Exception:
        # Only remove the new snapshot owned by this failed call.
        if created_snapshot:
            snapshot.unlink()
        raise
    return dict(record, manifest=str(manifest), snapshot_path=str(snapshot))


def verify(manifest):
    manifest = Path(manifest)
    record = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(record, dict) or record.get('format_version') != 1:
        raise ValueError('Unsupported character record.')
    name = record.get('snapshot')
    record_id = record.get('record_id')
    if not isinstance(record_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', record_id):
        raise ValueError('Invalid record id.')
    if name != record_id + '.md' or manifest.name != record_id + '.record.json':
        raise ValueError('Record filenames do not match the id.')
    snapshot = manifest.parent / name
    if snapshot.is_symlink():
        raise ValueError('Snapshot must be a local file, not a symbolic link.')
    data = snapshot.read_bytes()
    if digest(data) != record.get('sha256') or len(data) != record.get('bytes'):
        raise ValueError('Snapshot has changed; do not use it as the original baseline.')
    return dict(status='content_matches_record', record_id=record_id,
                snapshot=str(snapshot), sha256=record['sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    create = sub.add_parser('seal')
    create.add_argument('source')
    create.add_argument('directory')
    create.add_argument('--id', required=True, dest='record_id')
    check = sub.add_parser('verify')
    check.add_argument('manifest')
    args = parser.parse_args()
    try:
        result = seal(args.source, args.directory, args.record_id) if args.action == 'seal' else verify(args.manifest)
    except (OSError, ValueError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
