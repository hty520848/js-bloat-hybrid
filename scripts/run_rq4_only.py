#!/usr/bin/env python3
"""RQ4-only supplement entry point. RQ1, RQ2 and RQ3 are NOT resampled.

`scripts/run.py:22` hard-codes the rq1 -> rq2 -> rq3 -> rq4 order and exposes no
per-stage switch, so a repair to one RQ4 input cannot be exercised without
re-running three stages that need no repair (about 53.7 h of measured wall
clock). This driver is the minimal supplement:

  * it builds a fresh `Context`, so the run id is new and the frozen
    implementation snapshot is the repaired one;
  * it reuses identity-verified unit evidence through
    `experiments/admission.py:units`. That call is not optional: it is what
    supplies `q['deployment']`, and `experiments/rq1/run.py:72` grafts the test
    harness only when `deployment` is present. A `q` assembled by hand would
    silently drop the harness and change the meaning of the `-core` comparison;
  * it then runs `experiments/rq4/run.py` alone.

Purpose. `qualification` reaches exactly two places inside RQ4 (`rq4/run.py:20`
scope string, `:21` stage formalResult). A diagnostic run must never be able to
pass for the deliverable, so `--purpose diagnostic` (the default) takes the
narrower label, records itself in `status.json`, and drops a marker beside the
artifact. `--purpose formal` is the ten-library, ten-repetition delivery run.
"""
import argparse, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.common import Context, ROOT, read, write
from experiments.admission import units
from experiments.rq4 import run as rq4


def main():
    p = argparse.ArgumentParser(description='Run RQ4 alone against reused unit evidence.')
    p.add_argument('--run-id', required=True)
    p.add_argument('--unit-evidence-run', required=True,
                   help='Run whose prepare stage supplies original suite, scope, functions, core hits and deployment materialization')
    p.add_argument('--library', action='append', default=[],
                   help='Restrict to this library (repeatable). Omit for the full manifest.')
    p.add_argument('--purpose', choices=['diagnostic', 'formal'], default='diagnostic')
    a = p.parse_args()

    manifest = read(ROOT / 'datasets/manifests/libraries.json')
    known = sorted({x['library'] for x in manifest})
    requested = sorted(set(a.library)) if a.library else known
    unknown = sorted(set(requested) - set(known))
    if unknown:
        p.error('Unknown library: ' + ','.join(unknown))
    diagnostic = a.purpose == 'diagnostic'

    c = Context(a.run_id)
    try:
        c.record['executionPolicy'] = (
            'RQ4-only supplement entry point (scripts/run_rq4_only.py). RQ1, RQ2 and RQ3 were not '
            'resampled and remain in their original runs. Unit evidence (original suites, scope, '
            'functions, core hits and deployment materialization) is reused unchanged from '
            + a.unit_evidence_run + ' through experiments/admission.py:units.')
        c.record['rq4OnlyDriver'] = {'driver': 'scripts/run_rq4_only.py',
                                     'unitEvidenceRun': a.unit_evidence_run,
                                     'purpose': a.purpose,
                                     'librariesRequested': requested}
        for cfg in c.machine['targets'].values():
            cfg['unitEvidenceRun'] = a.unit_evidence_run
        if a.library:
            c.manifest = [x for x in manifest if x['library'] in set(requested)]
        c.save()

        units(c)
        c.record['qualifiedLibraries'] = sorted(c.qualified)
        c.save()
        missing = sorted(set(requested) - set(c.qualified))
        if missing:
            raise RuntimeError('Unit evidence reuse failed for ' + ','.join(missing) + '; see '
                               + str(c.out / 'unit-evidence-reuse.json')
                               + '. RQ4 would otherwise cover fewer libraries than requested.')

        rq4.run(c, qualification=diagnostic)

        if diagnostic:
            write(c.out / 'rq4/NOT-A-DELIVERABLE.json',
                  {'purpose': 'diagnostic', 'runId': a.run_id,
                   'libraries': sorted(c.qualified),
                   'repetitions': c.protocol['rq4']['repetitions'],
                   'arms': c.protocol['arms'],
                   'statement': 'Diagnostic run, not an RQ4 deliverable. The delivery is a '
                                'ten-library, ten-repetition formal run. Do not consume this file as one.'})
        rows = read(c.out / 'rq4/preparation-cost.json')['rows']
        c.record['rq4RowsBeforeFinish'] = len(rows)
        c.finish()
        print(str(c.out / 'status.json'))
        print('RQ4 rows=%d valid=%d' % (len(rows), sum(1 for r in rows if r.get('valid'))))
        by_arm = {}
        for r in rows:
            slot = by_arm.setdefault(r['arm'], [0, 0])
            slot[0] += 1
            slot[1] += 1 if r.get('valid') else 0
        for arm in sorted(by_arm):
            print('  %-24s rows=%d valid=%d' % (arm, by_arm[arm][0], by_arm[arm][1]))
    except Exception:
        c.record.update(status='failed', error=traceback.format_exc())
        c.save()
        raise


if __name__ == '__main__':
    main()
