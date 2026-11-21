"""Contract tests for the Cohen's-kappa helper in ``scripts/adjudicate_edges.py``.

Ported from ``analysis/E3边裁定标注规范-20261027.md`` section 14.2. The spec wrote
these as pytest functions relying on the ``tmp_path`` fixture, but **pytest is
installed in none of the three interpreters this project uses** (server CPython
3.6.9, local CPython 3.12.14, local CPython 3.13.5 -- all report
``No module named pytest``). The cases are therefore expressed as
``unittest.TestCase`` methods with stdlib ``tempfile`` in place of ``tmp_path``.
**The four cases and every assertion are unchanged.**

Why these four:
  * ``pe == 1`` makes kappa mathematically undefined; the helper must return
    ``None`` rather than raise or divide by zero.
  * Two sheets that agree *and* contain both TRUE and FALSE give kappa ``1.0``,
    **not** ``None``. This distinction has to be pinned down, otherwise a reader
    may think the paper is dodging the reliability statistic.
  * An empty overlap yields ``(None, 0)``; this also freezes the current
    behaviour of gap 12.6 (out-of-queue rows in the *second* sheet are ignored).
  * A *partial* second sheet still yields a kappa -- the code basis for letting
    a reviewer judge only a disputed subset instead of the whole queue.

Run:
    python3 -m unittest discover -s tests -p 'test_adjudication_kappa.py' -v
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

E = ['f.js:1:1->f.js:2:1', 'f.js:1:1->f.js:3:1']


class AdjudicationKappaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='adjkappa-'))

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _fixture(self, edges):
        """Queue + benchmark with exactly ``edges`` unjudged under arm=full."""
        queue = [{'file': 'f.js', 'arm': 'full', 'edge': e, 'verdict': 'UNJUDGED',
                  'sourceSha256': 'x'} for e in edges]
        (self.tmp / 'q.json').write_text(json.dumps(queue), encoding='utf-8')
        n = len(edges)
        bench = {'status': 'completed', 'rows': [{
            'file': 'f.js', 'arm': 'full', 'TP': 2, 'knownFP': 0, 'knownFN': 0,
            'unjudged': n, 'predicted': 2 + n, 'knownPositiveCount': 2 + n,
            'precisionLowerBound': 2 / (2 + n), 'precisionUpperBound': 1.0,
            'knownPositiveRecall': 1.0}]}
        (self.tmp / 'b.json').write_text(json.dumps(bench), encoding='utf-8')

    def _sheet(self, name, rows):
        """``rows``: list of (edge, verdict). Writes the 6-column tool format."""
        path = self.tmp / name
        with open(str(path), 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['file', 'arm', 'edge', 'verdict', 'note', 'adjudicator'])
            for edge, verdict in rows:
                w.writerow(['f.js', 'full', edge, verdict, '', name])
        return path

    def _run(self, sheet, out, second=None):
        script = ROOT / 'scripts' / 'adjudicate_edges.py'
        argv = ['adjudicate_edges.py', '--run-id', 'selftest',
                '--queue', str(self.tmp / 'q.json'),
                '--benchmark', str(self.tmp / 'b.json'),
                '--verdicts', str(sheet), '--output', str(out)]
        if second:
            argv += ['--second-verdicts', str(second)]
        saved = sys.argv
        sys.argv = argv
        try:
            env = {'__name__': '__main__', '__file__': str(script)}
            exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), env)
        finally:
            sys.argv = saved
        return json.loads(out.read_text(encoding='utf-8'))

    # ---- the four cases from spec section 14.2 -------------------------------

    def test_kappa_none_when_both_sheets_are_unanimously_true(self):
        """pe == 1 分支：kappa 在数学上无定义，必须返回 None，不得抛异常。"""
        self._fixture(E)
        a = self._sheet('a.csv', [(e, 'TRUE') for e in E])
        b = self._sheet('b.csv', [(e, 'TRUE') for e in E])
        p = self._run(a, self.tmp / 'out.json', second=b)
        self.assertIsNone(p['cohensKappa'])          # <-- pe == 1
        self.assertEqual(p['kappaOverlapEdges'], 2)
        self.assertEqual(p['status'], 'completed')
        self.assertEqual(p['missingVerdicts'], 0)

    def test_kappa_is_one_for_identical_mixed_sheets(self):
        """两张完全一致且 TRUE/FALSE 都出现的表 -> kappa = 1.0（注意：不是 None）。"""
        self._fixture(E)
        rows = [(E[0], 'TRUE'), (E[1], 'FALSE')]
        p = self._run(self._sheet('a.csv', rows), self.tmp / 'out.json',
                      second=self._sheet('b.csv', rows))
        self.assertEqual(p['cohensKappa'], 1.0)
        self.assertEqual(p['kappaOverlapEdges'], 2)

    def test_kappa_is_none_when_overlap_is_empty(self):
        """重叠为 0 -> (None, 0)；同时固化缺口 12.6（第二张表的越界行不报错）。"""
        self._fixture(E)
        a = self._sheet('a.csv', [(E[0], 'TRUE'), (E[1], 'FALSE')])
        b = self._sheet('b.csv', [('f.js:9:9->f.js:9:9', 'TRUE')])   # 队列外！
        p = self._run(a, self.tmp / 'out.json', second=b)            # 现状：不得抛异常
        self.assertIsNone(p['cohensKappa'])
        self.assertEqual(p['kappaOverlapEdges'], 0)
        self.assertEqual(p['status'], 'completed')                   # 覆盖检查只作用于第一张表

    def test_kappa_accepts_a_partial_second_sheet(self):
        """第二张表只覆盖争议子集即可产出 kappa（规范 §16 选项 B 的代码依据）。"""
        self._fixture(E + ['f.js:1:1->f.js:4:1'])
        a = self._sheet('a.csv', [(E[0], 'TRUE'), (E[1], 'FALSE'),
                                  ('f.js:1:1->f.js:4:1', 'TRUE')])
        b = self._sheet('b.csv', [(E[0], 'TRUE'), (E[1], 'TRUE')])   # 只覆盖 2 条
        p = self._run(a, self.tmp / 'out.json', second=b)
        self.assertEqual(p['kappaOverlapEdges'], 2)
        # pa=1/2, pb=2/2 -> pe=0.5 ; po=1/2 -> kappa=0.0
        self.assertEqual(p['cohensKappa'], 0.0)
        self.assertEqual(p['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
