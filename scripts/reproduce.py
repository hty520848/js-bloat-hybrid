#!/usr/bin/env python3
"""Run fresh analyses and measurements on the frozen paper-artifact cohort."""
import argparse
import hashlib
import json
import random
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments import clients, metrics, prepare, stubbifier_baselines as baselines
from experiments.common import Context, ROOT, read, same, write
from experiments.ordered_revision import build_one
from experiments.recovery_repair import reconcile_payload_events
from experiments.rq1 import run as graphs
from experiments.rq1 import static_benchmark
from experiments.rq3 import run as runtime

METHODS = ('sscg', 'sdcg', 'hybrid')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def analyze(c, lib, methods, tag):
    q = c.qualified[lib]
    analyses = {}
    if {'hybrid', 'mcg-only'} & set(methods):
        analyses['mcg'] = graphs.static(c, lib, q, 'mcg-only', tag + '-mcg')
    if {'hybrid', 'nodeprof-only'} & set(methods):
        analyses['dynamic'] = graphs.dynamic(c, lib, q, tag + '-nodeprof')
    else:
        analyses['dynamic'] = None
    if 'sscg' in methods:
        analyses['sscg'] = baselines.sscg(c, lib, q)
    if 'sdcg' in methods:
        analyses['sdcg'] = baselines.sdcg(c, lib, q)
    for name, value in analyses.items():
        require(value is None or value['valid'], '{} {} analysis failed; see command logs'.format(lib, name))
    return {lib: analyses}


def measure_rq1(c, lib, method, build, prefix):
    functions = read(build['manifest'])['functions']
    rows = []
    for index, client in enumerate(c.clients[lib]):
        row = {'library': lib, 'arm': method, 'client': client['name'], 'eligible': clients.comparison_eligible(client)}
        if row['eligible']:
            tag = prefix + '-client-' + str(index)
            target = clients.bind(c, client['cfg'], build['target'], tag)
            stage = c.run(tag, client['cfg']['command'], target)
            hits = set(read(client['hits']))
            counts = dict.fromkeys(('TP', 'FP', 'TN', 'FN'), 0)
            for function in functions:
                bloated = function['predictedBloated'][method]
                called = function['id'] in hits
                counts[('FP' if called else 'TP') if bloated else ('TN' if called else 'FN')] += 1
            valid = same(client['baseline'], stage)
            row.update(valid=valid, stage=stage, confusion=counts,
                       Accuracy=(counts['TP'] + counts['TN']) / len(functions) if valid else None)
        rows.append(row)
    return rows


def measure_rq2(c, lib, method, analyses, prefix):
    q = c.qualified[lib]
    build = build_one(c, lib, method, analyses, prefix, instrument=True)
    controls = {client['name']: client for client in c.clients[lib]}
    rows = []
    for index, cfg in enumerate(c.machine['clients'][lib]):
        name = cfg['directory']
        client = controls.get(name)
        tag = prefix + '-' + str(index)
        row = {'library': lib, 'arm': method, 'client': name, 'valid': False, 'MECS': None}
        if client and clients.comparison_eligible(client):
            original = clients.bind(c, cfg, q['deployment'], tag + '-original')
            transformed = clients.bind(c, cfg, build['target'], tag + '-transformed')
            original_bytes = metrics.application_js_bytes(original)
            initial_bytes = metrics.application_js_bytes(transformed)
            output = c.out / 'rq2' / 'payload' / tag
            output.mkdir(parents=True)
            stage = c.run(tag, cfg['command'], transformed, {'HYBRID_PAYLOAD_OUT': output})
            events = []
            for path in sorted(output.glob('payload-*.jsonl')):
                events.extend(json.loads(line) for line in path.read_text().splitlines())
            normalized, audit = reconcile_payload_events(events, build['target'])
            loaded_bytes = metrics.loaded_bytes(normalized)
            row.update(valid=same(client['baseline'], stage), stage=stage,
                       LFL=len({e['path'] for e in normalized if e['kind'] == 'file'}),
                       LFT=len({e['path'] for e in normalized if e['kind'] == 'function'}),
                       uniquePayloadBytes=loaded_bytes, payloadAudit=audit, payloadEvents=normalized)
            if row['valid']:
                row.update(metrics.expanded_size(original_bytes, initial_bytes, loaded_bytes))
        rows.append(row)
    return rows


def select(c, args, cost_library=None):
    planned = read(ROOT / 'datasets/manifests/clients.json')['libraries']
    libraries = {cost_library or args.library} if cost_library or args.library else set(planned)
    require(libraries <= set(planned), 'Unknown library')
    c.manifest = [entry for entry in c.manifest if entry['library'] in libraries]
    configs = {}
    for lib in libraries:
        require(lib in c.machine.get('targets', {}), 'Missing imported target: ' + lib)
        wanted = {entry['directory'] for entry in planned[lib]}
        if args.client:
            require(args.client in wanted, 'Client is not on frozen cohort for ' + lib)
            wanted = {args.client}
        entries = [entry for entry in c.machine.get('clients', {}).get(lib, []) if entry['directory'] in wanted]
        if not cost_library:
            require(len(entries) == len(wanted) and {entry['directory'] for entry in entries} == wanted,
                    'Import frozen client inputs for ' + lib)
            configs[lib] = entries
    c.machine['clients'] = configs
    c.protocol['formalLibraries'] = len(c.manifest)
    if args.smoke:
        c.protocol['rq3'].update(warmups=0, measuredRuns=1)
        c.protocol['rq4']['repetitions'] = 1
        c.protocol['formalClientQuorum'] = 1
    write(c.out / 'effective-protocol.json', c.protocol)
    write(c.out / 'effective-machine.json', c.machine)
    prepare.run(c)
    require(set(c.qualified) == libraries, 'Library input or original test qualification failed')
    if not cost_library:
        for lib in libraries:
            require(any(clients.comparison_eligible(row) for row in c.clients.get(lib, [])),
                    'No qualified client is available for ' + lib)


def measure_rq4(c, args, methods):
    rows = []
    for lib in sorted(c.qualified):
        for repetition in range(c.protocol['rq4']['repetitions']):
            order = list(methods)
            random.Random('{}/{}'.format(lib, repetition)).shuffle(order)
            for method in order:
                key = '{}/{}/{}/{}'.format(args.run_id, lib, repetition, method)
                child = Context('cost-' + hashlib.sha256(key.encode()).hexdigest()[:24], args.config)
                select(child, args, cost_library=lib)
                analyses = analyze(child, lib, [method], 'rq4')
                build = build_one(child, lib, method, analyses, 'rq4-transform')
                stages = []
                for analysis in analyses[lib].values():
                    if analysis:
                        stages.extend(analysis.get('stages', []))
                        stages.extend(analysis[key] for key in ('stage', 'mapping') if key in analysis)
                stages = [stage for stage in stages if not stage['label'].startswith('sscg-index-control-')]
                if build.get('targetExtraction'):
                    stages.append(build['targetExtraction'])
                analysis_seconds = sum(stage['seconds'] for stage in stages)
                rewrite_seconds = build['transform']['seconds']
                child.finish()
                require(child.record['status'] == 'completed', 'RQ4 inputs changed')
                rows.append({'library': lib, 'arm': method, 'repetition': repetition,
                             'valid': True, 'analysisSeconds': analysis_seconds,
                             'rewriteSeconds': rewrite_seconds, 'totalSeconds': analysis_seconds + rewrite_seconds,
                             'run': child.record['runId']})
                write(c.out / 'rq4' / 'preparation-cost.json', rows)
    return rows


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--config', type=Path)
    cli.add_argument('--run-id', required=True)
    cli.add_argument('--library')
    cli.add_argument('--client')
    cli.add_argument('--methods', nargs='+', choices=METHODS, default=METHODS)
    cli.add_argument('--components', action='store_true', help='Also run the two Hybrid components in RQ1')
    cli.add_argument('--smoke', action='store_true', help='One library, one client, one timing pair and one cost repetition')
    cli.add_argument('--static-benchmark', action='store_true', help='Run the standalone SunSpider driver only')
    cli.add_argument('--static-multifile', action='store_true', help='Run MCG on the archived multi-file subjects')
    cli.add_argument('--program', help='Run one named SunSpider source in standalone mode')
    args = cli.parse_args()
    if args.smoke and not (args.library and args.client):
        cli.error('--smoke requires --library and --client')
    if args.client and not args.library:
        cli.error('--client requires --library')
    if args.program and not args.static_benchmark:
        cli.error('--program requires --static-benchmark')
    require(sys.platform.startswith('linux'), 'Use Linux for the packaged runtimes and suite commands')
    c = Context(args.run_id, args.config)
    try:
        if args.static_multifile:
            require(static_benchmark.run_multifile(c, args.library), 'Multi-file static analysis failed')
            c.finish()
            return 0
        if args.static_benchmark:
            static_benchmark.run(c, args.program)
            require(read(c.out / 'rq1/static-benchmark.json')['status'] == 'completed', 'Static benchmark did not complete')
            c.finish()
            return 0
        select(c, args)
        methods = list(dict.fromkeys(args.methods))
        require('sscg' not in methods or all(k in c.machine.get('stubbifierBaselines', {})
                for k in ('codeql', 'searchPath', 'querySha256')), 'Import with the pinned CodeQL CLI and search path for SSCG')
        first = methods + (['mcg-only', 'nodeprof-only'] if args.components else [])
        c.protocol['arms'] = methods
        c.builds = []
        sizes = []
        classifications = []
        recovery = []
        for lib in sorted(c.qualified):
            analyses = analyze(c, lib, first, 'analysis-' + lib)
            for method in first:
                prefix = lib + '-' + method
                build = build_one(c, lib, method, analyses, 'rq1-' + prefix)
                sizes.append(build)
                classifications.extend(measure_rq1(c, lib, method, build, 'rq1-' + prefix))
                if method in methods:
                    c.builds.append(build)
                    recovery.extend(measure_rq2(c, lib, method, analyses, 'rq2-' + prefix))
                write(c.out / 'rq1' / 'clients.json', classifications)
                write(c.out / 'rq1' / 'sizes.json', sizes)
                write(c.out / 'rq2' / 'loading.json', recovery)
        write(c.out / 'rq2' / 'loading-cells.json', metrics.aggregate_expanded(recovery))
        runtime.run(c, qualification=False)
        timing = read(c.out / 'rq3' / 'runtime.json')['rows']
        costs = measure_rq4(c, args, methods)
        if args.smoke:
            require(classifications and all(row.get('valid') for row in classifications), 'RQ1 smoke classification failed')
            require(recovery and all(row['valid'] and row['MECS'] is not None for row in recovery), 'RQ2 smoke failed')
            require(timing and all(row['valid'] for row in timing), 'RQ3 smoke timing failed')
            require(costs and all(row['valid'] for row in costs), 'RQ4 smoke timing failed')
        c.finish()
        if c.record['status'] == 'invalid-input-or-implementation-changed':
            raise RuntimeError('Inputs changed during execution')
        print(str(c.out / 'status.json'))
        return 0
    except Exception:
        c.record.update(status='failed', error=traceback.format_exc())
        c.save()
        raise


if __name__ == '__main__':
    sys.exit(main())

