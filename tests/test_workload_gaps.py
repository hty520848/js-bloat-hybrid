import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from experiments.clients import formal_ready
from experiments.common import read
from experiments.rq3.run import run

class FrozenWorkloadGaps(unittest.TestCase):
 def test_valid_zero_hit_is_retained_but_missing_original_blocks_admission(self):
  # 2026-10-27 rewrite (option A). The previous body encoded a 5-of-5 rule:
  # five clients present -> ready, drop one -> not ready. The admission contract
  # was deliberately changed (see experiments/clients.py:26-31: a failed
  # original control must no longer block admission) to
  # ``eligible >= formalClientQuorum``, so the old threshold is arithmetically
  # incompatible with quorum=3: dropping one of five leaves four, which is still
  # >= 3. The two properties this case was written to pin are preserved --
  #   (1) a valid zero-hit client is RETAINED in the cohort, not dropped, and
  #   (2) losing originals eventually blocks admission --
  # but (2) now fires when the quorum is actually breached rather than when the
  # first client is lost. Both properties were checked against the current
  # implementation, and the quorum boundary is asserted explicitly.
  libs=['a','b']
  def cohort(lib,eligible,zero_hit=0):
   return ([{'name':'%s-e%d'%(lib,i),'methodComparisonEligible':True} for i in range(eligible)]+
           [{'name':'%s-z%d'%(lib,i),'methodComparisonEligible':False} for i in range(zero_hit)])
  c=SimpleNamespace(qualified={x:{} for x in libs},protocol={'formalLibraries':2,'clientsPerLibrary':5,'formalClientQuorum':3},clients={'a':cohort('a',5),'b':cohort('b',5,1)})
  self.assertTrue(formal_ready(c,libs))
  # (1) the zero-hit client is retained: measured counts it, eligible does not.
  self.assertEqual(c.formalCoverage['b']['measured'],6)
  self.assertEqual(c.formalCoverage['b']['eligible'],5)
  self.assertEqual(c.formalCoverage['b']['targetUnexercised'],1)
  # (2) admission survives exactly down to the quorum ...
  c.clients['b']=cohort('b',3,1);self.assertTrue(formal_ready(c,libs))
  # ... and is blocked the moment the quorum is breached.
  c.clients['b']=cohort('b',2,1);self.assertFalse(formal_ready(c,libs))
 def test_zero_hit_runtime_cell_never_executes_or_invents_an_estimate(self):
  with tempfile.TemporaryDirectory() as td:
   def unexpected(*args,**kwargs):raise AssertionError('A zero-hit workload was resampled')
   # 2026-10-27 repair: ``completion_gate()`` reads ``protocol['arms']``
   # (experiments/common.py:121) and the real ``config/protocol.json`` always
   # carries it (6 arms). This synthetic dict predated that requirement, which
   # is why the case reported ``KeyError: 'arms'`` under the standard runner.
   # Only the missing keys were added; no assertion was touched.
   c=SimpleNamespace(out=Path(td),protocol={'rq3':{'warmups':2,'measuredRuns':10,'seed':1,'bootstrapSamples':10},'arms':['mcg-only','hybrid'],'formalLibraries':1},builds=[{'library':'a','arm':'hybrid','valid':True}],qualified={'a':{}},clients={'a':[{'name':'zero','methodComparisonEligible':False}]},record={'stages':[]},save=lambda:None,run=unexpected)
   run(c,qualification=False);data=read(Path(td)/'rq3/runtime.json');self.assertEqual(data['rows'],[]);self.assertEqual(data['summary'],[]);self.assertEqual(data['coverageGaps'][0]['status'],'not-run-target-unexercised');self.assertEqual(c.record['stages'][0]['status'],'blocked')
