"""Offline contract tests for the reviewer-2.x supplement code.

These do not need the frozen server image: they pin the parts that are pure
logic (MECS aggregation, the completion gate, edge adjudication, and the
scope partition used by the static ablation) so that a change which silently
reintroduces an always-None metric or an always-completed gate fails here.

--------------------------------------------------------------------------------
PORT NOTE (2026-10-27) -- form changed, assertions unchanged
--------------------------------------------------------------------------------
This file used to be written in pytest style: module-level ``test_*`` functions
taking the ``tmp_path`` fixture. **pytest is not installed in any interpreter
this project uses** (server CPython 3.6.9, local 3.12.14, local 3.13.5 all
report ``No module named pytest``), and the runner the repository itself
documents is ``python3 -m unittest discover -s tests -v`` (README.md:35 and
docs/SUPPLEMENT_POLICY_20261025b.md:23). Under that runner ``unittest`` collects
module-level functions **not at all**, so this file previously contributed
**zero** executed tests: the two adjudication contract assertions below
(``precisionExact == 2/3`` and the missing-verdict ``exit 2``) had never
actually run.

The file is therefore re-expressed as ``unittest.TestCase`` methods with stdlib
``tempfile`` in place of the ``tmp_path`` fixture. **Every test and every
assertion is carried over verbatim**; nothing was relaxed, removed or re-judged.
The original pytest-style source is archived at
``analysis/e3-port-orig/test_supplement_code.py.orig``
(sha256 dce78f77142f7cd4767e2098b0ac8cbcf6440d0a94758dd4d0b55f9fcccddfde).
"""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import metrics
from experiments.common import completion_gate


def _fn(name, body_start, body_end, file='node_modules/pkg/index.js'):
    return {'id': name,
            'file': file,
            'loc': {'start': {'line': body_start[0], 'column': 0}, 'end': {'line': body_end[0], 'column': body_end[1]}},
            'bodyLoc': {'start': {'line': body_start[0], 'column': body_start[1]},
                        'end': {'line': body_end[0], 'column': body_end[1]}}}


class SupplementCodeContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='suppcode-'))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # ------------------------------------------------------------------ MECS

    def test_mecs_zero_is_measurement(self):
        self.assertEqual(metrics.mecs_kb(0), 0.0)
        self.assertIsNone(metrics.mecs_kb(None))
        self.assertEqual(metrics.mecs_kb(2048), 2.0)

    def test_mecs_aggregate_excludes_ineligible_and_keeps_zero(self):
        rows = [
            {'library': 'l', 'arm': 'hybrid', 'workload': 'c1', 'eligible': True, 'MECS': 4.0},
            {'library': 'l', 'arm': 'hybrid', 'workload': 'c2', 'eligible': True, 'MECS': 0.0},
            {'library': 'l', 'arm': 'hybrid', 'workload': 'c3', 'eligible': False, 'MECS': None},
        ]
        cell = metrics.aggregate(rows)[0]
        self.assertEqual(cell['eligibleWorkloads'], 2)
        self.assertEqual(cell['meanMECS'], 2.0)
        self.assertEqual(cell['zeroExpansionWorkloads'], 1)

    # -------------------------------------------------------- completion gate

    def test_gate_refuses_to_call_a_pilot_completed(self):
        protocol = {'arms': ['a', 'b'], 'formalLibraries': 10}
        # Two libraries fully done out of ten is not "completed".
        gate = completion_gate(protocol, {f'l{i}': 1 for i in range(10)},
                               [(f'l{i}', a) for i in range(2) for a in ('a', 'b')])
        self.assertEqual(gate['status'], 'partial')
        self.assertEqual(gate['librariesCovered'], 2)
        self.assertEqual(gate['missingCells'], 16)
        # Ten libraries, both arms, nothing invalid -> completed.
        full = completion_gate(protocol, {f'l{i}': 1 for i in range(10)},
                               [(f'l{i}', a) for i in range(10) for a in ('a', 'b')])
        self.assertEqual(full['status'], 'completed')
        # One invalid cell is enough to stop calling it completed.
        broken = completion_gate(protocol, {f'l{i}': 1 for i in range(10)},
                                 [(f'l{i}', a) for i in range(10) for a in ('a', 'b') if (i, a) != (3, 'b')],
                                 [('l3', 'b')])
        self.assertEqual(broken['status'], 'partial')
        self.assertEqual(broken['invalidCells'], 1)

    # ------------------------------------------------------------ adjudication

    def _adjudicate(self, verdicts):
        queue = [{'file': 'f.js', 'arm': 'full', 'edge': 'f.js:1:1->f.js:2:1', 'verdict': 'UNJUDGED', 'sourceSha256': 'x'},
                 {'file': 'f.js', 'arm': 'full', 'edge': 'f.js:1:1->f.js:3:1', 'verdict': 'UNJUDGED', 'sourceSha256': 'x'}]
        (self.tmp / 'q.json').write_text(json.dumps(queue), encoding='utf-8')
        bench = {'status': 'completed', 'rows': [{'file': 'f.js', 'arm': 'full', 'TP': 1, 'knownFP': 0, 'knownFN': 2, 'unjudged': 2,
                                                  'predicted': 3, 'knownPositiveCount': 3, 'precisionLowerBound': 1 / 3,
                                                  'precisionUpperBound': 1.0, 'knownPositiveRecall': 1 / 3}]}
        (self.tmp / 'b.json').write_text(json.dumps(bench), encoding='utf-8')
        sheet = self.tmp / 'v.csv'
        with open(str(sheet), 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['file', 'arm', 'edge', 'verdict', 'note', 'adjudicator'])
            for edge, verdict in zip([q['edge'] for q in queue], verdicts):
                w.writerow(['f.js', 'full', edge, verdict, '', 'test'])
        out = self.tmp / 'out.json'
        return sheet, out

    def _run_adjudicator(self, sheet, out):
        script = ROOT / 'scripts/adjudicate_edges.py'
        argv = ['adjudicate_edges.py', '--run-id', 'selftest', '--queue', str(self.tmp / 'q.json'),
                '--benchmark', str(self.tmp / 'b.json'),
                '--verdicts', str(sheet), '--output', str(out)]
        saved = sys.argv
        sys.argv = argv
        try:
            env = {'__name__': '__main__', '__file__': str(script)}
            exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), env)
        finally:
            sys.argv = saved

    def test_adjudication_closes_the_interval(self):
        sheet, out = self._adjudicate(['TRUE', 'FALSE'])
        self._run_adjudicator(sheet, out)
        cell = json.loads(out.read_text())['cells'][0]
        self.assertEqual(cell['remainingUnjudged'], 0)
        self.assertIs(cell['adjudicationComplete'], True)
        self.assertEqual(cell['precisionExact'], 2 / 3)        # TP 1 + adjudicated TRUE 1, over 3 predicted
        self.assertEqual(cell['TP'], 2)
        self.assertEqual(cell['knownFP'], 1)

    def test_adjudication_rejects_missing_verdicts(self):
        sheet, out = self._adjudicate(['TRUE', 'UNJUDGED'])
        try:
            self._run_adjudicator(sheet, out)
        except SystemExit as exit_code:
            self.assertEqual(exit_code.code, 2)          # incomplete, never silently accepted
        else:
            raise AssertionError('an unjudged edge must not be accepted as complete')

    # --------------------------------------------------------- scope partition

    def test_scope_partition_separates_caller_from_callee(self):
        from experiments.static_scope import classify
        scope = {'index.js', 'lib/util.js'}
        # Endpoints are printed relative to the analysis directory, exactly as the
        # analyzer emits them: own files, dependency files, and call sites that
        # live in the bound client tree outside the library root.
        edges = [
            'index.js:<1,0>--<2,1> -> lib/util.js:<3,0>--<4,1>',                 # production -> production
            'index.js:<1,0>--<2,1> -> node_modules/dep/index.js:<1,0>--<2,1>',    # production -> dependency
            '../client/test/a.js:<1,0>--<2,1> -> index.js:<1,0>--<2,1>',          # outside -> production
        ]
        result = classify(edges, scope, 'mylib', '/libs/mylib')
        self.assertEqual(result['totalEdges'], 3)
        self.assertEqual(result['inScopeCallerEdges'], 2)      # the module switch acts on the call site
        self.assertEqual(result['outOfScopeCallerEdges'], 1)
        self.assertEqual(result['inScopeCalleeEdges'], 2)      # the callee side is a different question
        self.assertEqual(result['outOfScopeCalleeEdges'], 1)

    # ------------------------------------------------------- Istanbul mapping

    def test_istanbul_ignore_is_not_a_mapping_loss(self):
        from experiments import coverage_map
        # Istanbul's fnMap records the body range, so the body anchor is the key.
        key = coverage_map.absolute('/r', 'node_modules/pkg/index.js')
        coverage = {key: {'fnMap': {'0': {'loc': {'start': {'line': 45, 'column': 35},
                                                 'end': {'line': 55, 'column': 1}}}}}}
        functions = [_fn('mapped', (45, 35), (55, 1)),
                     _fn('ignored', (33, 16), (33, 66))]
        ignored = {key: {'33:16:33:66': {'key': '33:16:33:66', 'hint': 'next'}}}
        result = coverage_map.map_manifest(functions, coverage, '/r', ignored)
        self.assertEqual(result['totals'], {'measured': 2, 'mapped': 1, 'ignored': 1, 'missing': 0})
        self.assertEqual(result['ignored'][0]['id'], 'ignored')
        self.assertEqual(result['missing'], [])

    def test_unexplained_absence_still_fails_qualification(self):
        from experiments import coverage_map
        key = coverage_map.absolute('/r', 'node_modules/pkg/index.js')
        coverage = {key: {'fnMap': {'0': {'loc': {'start': {'line': 1, 'column': 10},
                                                 'end': {'line': 3, 'column': 1}}}}}}
        functions = [_fn('present', (1, 10), (3, 1)), _fn('lost', (7, 4), (9, 2))]
        result = coverage_map.map_manifest(functions, coverage, '/r', {})
        # No hint, no slot: the location genuinely did not map and must be reported.
        self.assertEqual(result['totals']['mapped'], 1)
        self.assertEqual(result['totals']['missing'], 1)
        self.assertEqual(result['missing'][0]['id'], 'lost')

    def test_body_anchor_requires_exact_columns(self):
        from experiments import coverage_map
        key = coverage_map.absolute('/r', 'node_modules/pkg/index.js')
        coverage = {key: {'fnMap': {'0': {'loc': {'start': {'line': 1, 'column': 12},
                                                 'end': {'line': 3, 'column': 1}}}}}}
        # One column off is a different function, not a tolerance question.
        result = coverage_map.map_manifest([_fn('shifted', (1, 11), (3, 1))], coverage, '/r', {})
        self.assertEqual(result['totals']['mapped'], 0)
        self.assertEqual(result['totals']['missing'], 1)

    def test_file_absent_from_coverage_is_reported_not_dropped(self):
        from experiments import coverage_map
        result = coverage_map.map_manifest([_fn('x', (2, 4), (4, 1))], {}, '/r', {})
        self.assertEqual(result['filesAbsentFromCoverage'][0]['file'], 'node_modules/pkg/index.js')
        self.assertEqual(result['totals']['missing'], 1)

    # ------------------------------------------------------------- arm naming

    def test_arm_names_drive_the_switches(self):
        from experiments.rq1.run import arm_env
        # Protocol spelling and row spelling must reach the same environment.
        self.assertEqual(arm_env('mcg-no-index'), arm_env('no-index'))
        self.assertEqual(arm_env('mcg-no-index')['MCG_DISABLE_INDEX'], '1')
        self.assertEqual(arm_env('mcg-no-module-filter')['MCG_DISABLE_MODULE_FILTER'], '1')
        self.assertEqual(arm_env('mcg-no-both'), {'MCG_DISABLE_INDEX': '1', 'MCG_DISABLE_MODULE_FILTER': '1'})
        self.assertEqual(arm_env('mcg-only'), {'MCG_DISABLE_INDEX': '0', 'MCG_DISABLE_MODULE_FILTER': '0'})
        # no-file-scope changes the analysis input, not the guards.
        self.assertEqual(arm_env('no-file-scope'), {'MCG_DISABLE_INDEX': '0', 'MCG_DISABLE_MODULE_FILTER': '0'})
        # An unknown arm must not silently fall back to "both switches on": that is
        # how five nominally different arms were once run with identical flags.
        try:
            arm_env('mcg-typo')
        except KeyError:
            pass
        else:
            raise AssertionError('unknown arm silently kept both switches on')


if __name__ == '__main__':
    unittest.main()
