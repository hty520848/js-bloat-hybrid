#!/usr/bin/env python3
"""Independent child end timestamps verify completion latency and deadline handling."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,write,read
c=Context(sys.argv[1]);rows=[]
for i,delay in enumerate([.05,.10,.15]):
 output=c.out/('probe-'+str(i)+'.json')
 code="import time,json;time.sleep({});open({!r},'w').write(json.dumps({{'end':time.monotonic()}}))".format(delay,str(output))
 st=c.run('timer-probe-'+str(i),['python3','-c',code],c.work)
 # Child timestamp is independent of the parent runner's completion detection.
 lag=time.monotonic()-read(output)['end'];rows.append({'delay':delay,'observation':st,'completionLagUpperBoundSeconds':lag})
timeout=c.run('timer-deadline',['python3','-c','import time;time.sleep(5)'],c.work,timeout=.1)
assert timeout['exitCode']==124 and timeout['timeout']
write(c.out/'timer-validation.json',{'rows':rows,'timeout':timeout,'note':'Completion lag upper bound includes log hashing and metadata serialization; raw timings are retained, not a scientific performance claim.'})
c.finish();print(c.out)
