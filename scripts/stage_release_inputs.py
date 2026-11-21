#!/usr/bin/env python3
"""Assemble and verify frozen inputs downloaded separately from the repository."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from import_inputs import digest

ROOT = Path(__file__).resolve().parents[1]


def install(parts, destination, identity):
    if destination.exists():
        if (destination.stat().st_size, digest(destination)) != (identity['bytes'], identity['sha256']):
            raise ValueError('Existing input differs: ' + str(destination))
        return

    if sum(path.stat().st_size for path in parts) != identity['bytes']:
        raise ValueError('Input length mismatch: ' + destination.name)
    with tempfile.NamedTemporaryFile(dir=str(destination.parent), suffix='.partial', delete=False) as temp:
        pending = Path(temp.name)
    try:
        sha = hashlib.sha256()
        with pending.open('wb') as output:
            for part in parts:
                with part.open('rb') as source:
                    for block in iter(lambda: source.read(2 ** 20), b''):
                        output.write(block)
                        sha.update(block)
        if (pending.stat().st_size, sha.hexdigest()) != (identity['bytes'], identity['sha256']):
            raise ValueError('Frozen input checksum mismatch: ' + destination.name)
        # Publish the complete file without replacing another run's output.
        os.link(str(pending), str(destination))
    finally:
        pending.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path, required=True,
                        help='Directory containing downloaded Release assets or the original full archives')
    parser.add_argument('--codeql', type=Path,
                        help='Official CodeQL CLI 2.3.4 Linux x64 zip, required unless already staged')
    args = parser.parse_args()

    manifest = ROOT / 'manifest' / 'inputs.json'
    manifest_data = json.loads(manifest.read_text(encoding='utf-8'))
    inputs = {key: entry for key, entry in manifest_data.items() if 'file' in entry}
    split = json.loads((manifest.parent / 'release-parts.json').read_text(encoding='utf-8'))
    pending = {}
    try:
        for key, identity in inputs.items():
            destination = (manifest.parent / identity['file']).resolve()
            if destination.is_file() or key in ('codeqlModules', 'portableConfiguration'):
                parts = [destination]
            elif key == 'codeqlCli':
                if args.codeql is None:
                    raise ValueError('Supply the official CLI archive with --codeql')
                parts = [args.codeql]
            else:
                whole = args.assets_dir / destination.name
                parts = [whole] if whole.is_file() or key not in split else [
                    args.assets_dir / name for name in split[key]
                ]
            missing = next((part for part in parts if not part.is_file()), None)
            if missing is not None:
                raise ValueError('Required input file is absent: ' + str(missing))
            pending[key] = (parts, destination, identity)

        for parts, destination, identity in pending.values():
            install(parts, destination, identity)
            print('Verified', destination.name, flush=True)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()

