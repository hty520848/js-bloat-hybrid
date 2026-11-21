import os,subprocess,unittest
from experiments.common import ROOT,read
from release_test_support import release_machine

class CalendarClock(unittest.TestCase):
 def test_fixed_defaults_preserve_explicit_dates_and_monotonic_clock(self):
  m=release_machine();env=dict(os.environ,HYBRID_FIXED_DATE_MS='1590000000000',HYBRID_FIXED_CLOCK_APPLY='1',NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/fixed_clock.cjs'))
  code='const assert=require("assert");assert.equal(Date.now(),1590000000000);assert.equal(new Date().getTime(),1590000000000);assert.equal(new Date(1).getTime(),1);assert.equal(Date.UTC(2020,0,1),1577836800000);assert(new Date() instanceof Date);const a=process.hrtime.bigint();assert(process.hrtime.bigint()>=a);'
  subprocess.run([m['nodeTest'],'-e',code],env=env,check=True)
  env.pop('HYBRID_FIXED_CLOCK_APPLY');subprocess.run([m['nodeTest'],'-e','if(Date.now()<1700000000000)throw Error("Tooling clock was frozen")'],env=env,check=True)
if __name__=='__main__':unittest.main()
