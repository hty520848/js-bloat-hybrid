import unittest
from experiments.rq2.run import eligible_completion_pairs
from experiments.common import completion_gate

class CompletionAccounting(unittest.TestCase):
 def test_skips_failures_and_absent_comparisons_remain_distinct(self):
  rows=[{'library':'a','arm':'mcg-only','eligible':True,'valid':True},
        {'library':'a','arm':'mcg-only','eligible':False,'valid':None},
        {'library':'b','arm':'mcg-only','eligible':True,'valid':False},
        {'library':'c','arm':'mcg-only','eligible':False,'valid':None}]
  pairs=eligible_completion_pairs(rows)
  self.assertEqual(pairs,{('a','mcg-only'):True,('b','mcg-only'):False})
  gate=completion_gate({'formalLibraries':3,'arms':['mcg-only']},{x:{} for x in 'abc'},[k for k,v in pairs.items() if v],[k for k,v in pairs.items() if not v])
  self.assertEqual((gate['completedCells'],gate['invalidCells'],gate['missingCells']),(1,1,1))
