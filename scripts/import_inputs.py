#!/usr/bin/env python3
"""Verify and import the frozen offline inputs without replacing an existing configuration."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(2 ** 20), b''):
            result.update(block)
    return result.hexdigest()


def verified(manifest, identity):
    path = (manifest.parent / identity['file']).resolve()
    if path.stat().st_size != identity['bytes'] or digest(path) != identity['sha256']:
        raise ValueError('Input differs from its frozen identity: ' + str(path))
    return path


def unpack(archive, root):
    # These are hash-verified local input archives. GNU tar extracts into an
    # empty tree without preserving ownership or following outside links.
    root.mkdir(parents=True, exist_ok=False)
    subprocess.run(['tar', '--extract', '--gzip', '--file', str(archive),
                    '--directory', str(root), '--no-same-owner', '--keep-old-files'], check=True)


def relocate(value, inputs):
    if isinstance(value, str):
        return value.replace('{INPUTS}', str(inputs)).replace('{PACKAGE}', str(ROOT))
    if isinstance(value, list):
        return [relocate(item, inputs) for item in value]
    if isinstance(value, dict):
        return {key: relocate(item, inputs) for key, item in value.items()}
    return value


def preserve_copy(src, dest):
    if dest.exists():
        if digest(src) != digest(dest):
            raise ValueError('Existing input differs: ' + str(dest))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('archive', nargs='?', type=Path)
    cli.add_argument('--sha256')
    cli.add_argument('--name', default='frozen-10x5')
    cli.add_argument('--manifest', type=Path)
    cli.add_argument('--config', type=Path, default=ROOT / 'config' / 'machine.frozen.json')
    cli.add_argument('--codeql', type=Path)
    cli.add_argument('--codeql-search-path', type=Path)
    cli.add_argument('--coverage-node-modules', type=Path)
    cli.add_argument('--runtime-config', type=Path, help='Optional JSON with validated per-library NodeProf runtime paths')
    args = cli.parse_args()
    portable_config = None
    if args.manifest:
        if args.archive or args.sha256:
            cli.error('Choose a manifest or a positional archive with --sha256')
        manifest_path = args.manifest.resolve()
        identity = json.loads(manifest_path.read_text(encoding='utf-8'))
        archive = verified(manifest_path, identity['experimentInputs'])
        static_zip = verified(manifest_path, identity['staticReference'])
        static_sources = verified(manifest_path, identity['staticSources'])
        static_multifile = verified(manifest_path, identity['staticMultifile'])
        profiles = verified(manifest_path, identity['profileRuntimes'])
        codeql_zip = verified(manifest_path, identity['codeqlCli'])
        codeql_pack = verified(manifest_path, identity['codeqlLibrary'])
        codeql_modules = verified(manifest_path, identity['codeqlModules'])
        if 'portableConfiguration' in identity:
            portable_config = verified(manifest_path, identity['portableConfiguration'])
    else:
        if not args.archive or not args.sha256:
            cli.error('Use --manifest, or supply an archive and --sha256')
        archive = args.archive.resolve()
        if digest(archive) != args.sha256:
            raise ValueError('Bundle hash mismatch')
        static_zip = static_sources = None
    if args.name in ('', '.', '..') or not all(c.isalnum() or c in '-_.' for c in args.name):
        cli.error('Invalid private input directory name')
    if bool(args.codeql) != bool(args.codeql_search_path):
        cli.error('Supply both --codeql and --codeql-search-path')
    config = args.config.resolve()
    if config.exists():
        raise FileExistsError('Existing machine configuration preserved: ' + str(config))
    root = (ROOT / 'artifacts' / args.name).resolve()
    unpack(archive, root)
    portable_config = portable_config or root / 'portable-machine.json'
    machine = relocate(json.loads(portable_config.read_text(encoding='utf-8')), root)
    # An archive may identify its historical roots for diagnostics, but runs use private clones.
    machine.pop('protectedLegacyRoots', None)
    if args.manifest:
        planned = json.loads((ROOT / 'datasets' / 'manifests' / 'clients.json').read_text(encoding='utf-8'))['libraries']
        for lib, clients in planned.items():
            configured = machine.get('clients', {}).get(lib, [])
            if len(configured) != 5 or {row['directory'] for row in configured} != {row['directory'] for row in clients}:
                raise ValueError('Archive client cohort differs for ' + lib)
            for row in configured:
                if not (Path(row['root']) / 'package.json').is_file():
                    raise ValueError('Client source is absent: ' + row['directory'])
    coverage = args.coverage_node_modules or (Path(machine['targets']['css-loader']['root']) / 'node_modules'
                                              if args.manifest else Path(machine['transformerNodeModules']))
    machine['stubbifierBaselines'] = {'coverageNodeModules': str(coverage.resolve())}
    if args.manifest:
        unpack(profiles, root / 'profile-runtimes')
        profile = relocate(identity['profileConfiguration'], root)
        default_profile = profile['default']
        for key in ('graalNode', 'nodeprofJar', 'nodeprofLoader'):
            machine[key] = default_profile[key]
        machine['runtimeOverrides'] = profile['overrides']
        if not args.codeql:
            codeql_root = root / 'codeql-tools'
            codeql_root.mkdir()
            subprocess.run(['unzip', '-q', str(codeql_zip), '-d', str(codeql_root)], check=True)
            unpack(codeql_pack, codeql_root / 'libraries')
            args.codeql = codeql_root / 'codeql' / 'codeql'
            packs = [p for p in (codeql_root / 'libraries').iterdir() if p.is_dir()]
            if len(packs) != 1 or not args.codeql.is_file():
                raise ValueError('Unexpected CodeQL archive layout')
            args.codeql_search_path = packs[0]
            modules_query = packs[0] / 'javascript/ql/src/semmle/javascript/Modules.qll'
            if not modules_query.is_file():
                raise ValueError('CodeQL JavaScript pack does not have the expected module query')
            shutil.copy2(str(codeql_modules), str(modules_query))
    if args.codeql:
        machine['stubbifierBaselines'].update(
            codeql=str(args.codeql.resolve()), searchPath=str(args.codeql_search_path.resolve()),
            querySha256=digest(ROOT / 'src' / 'baselines' / 'stubbifier-recovery.ql'))
    if args.runtime_config:
        machine['runtimeOverrides'] = json.loads(args.runtime_config.read_text(encoding='utf-8'))
    for source in (root / 'npm').glob('*.tgz'):
        preserve_copy(source, ROOT / 'artifacts' / 'npm' / source.name)
    if static_zip:
        preserve_copy(static_zip, ROOT / 'artifacts' / 'StaticJSCallGraphs.zip')
        static_root = (ROOT / 'artifacts' / (args.name + '-static')).resolve()
        unpack(static_sources, static_root)
        machine['staticSourceRoot'] = str(static_root / 'artifacts' / 'sunspider')
        multifile_root = static_root / 'multi-file'
        unpack(static_multifile, multifile_root)
        machine['staticMultifileRoot'] = str(multifile_root / 'mcg' / 'src' / 'jieguo' / 'nodes')
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open('x', encoding='utf-8') as target:
        target.write(json.dumps(machine, indent=2) + '\n')
    print(config)


if __name__ == '__main__':
    main()
