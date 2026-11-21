import time
from ..common import write,completion_gate
from ..rq1.run import static,dynamic,build
def run(c,qualification=True):
 rows=[]
 for lib,q in sorted(c.qualified.items()):
  for rep in range(c.protocol['rq4']['repetitions']):
   for arm in c.protocol['arms']:
    tag='rq4-{}-{}-{}'.format(lib,rep,arm);start=time.monotonic();sg=dg=None
    if arm!='nodeprof-only':sg=static(c,lib,q,arm,tag+'-static')
    if arm in ['nodeprof-only','hybrid']:dg=dynamic(c,lib,q,tag+'-profile')
    if (sg and not sg['valid']) or (dg and not dg['valid']):
     rows.append({'library':lib,'arm':arm,'repetition':rep,'valid':False,'reason':'Analysis qualification failed','static':sg,'dynamic':dg});continue
    b=build(c,lib,q,arm,sg,dg,tag)
    if not b.get('transform'):
     rows.append({'library':lib,'arm':arm,'repetition':rep,'valid':False,'reason':'Target extraction or build failed','build':b});write(c.out/'rq4/preparation-cost.json',{'status':'running','rows':rows});continue
    s=sg['stage']['seconds'] if sg else 0;d=dg['stage']['seconds'] if dg else 0;m=dg.get('mapping',{}).get('seconds',0) if dg else 0;t=b['transform']['seconds'];selection=(b.get('targetExtraction') or {}).get('seconds',0)
    rows.append({'library':lib,'arm':arm,'repetition':rep,'valid':b['valid'],'staticSeconds':s,'dynamicSeconds':d,'sourceMappingSeconds':m,'targetExtractionSeconds':selection,'fusionAndTransformSeconds':t,'phaseSumSeconds':s+d+m+selection+t,'driverWallIncludingCopyAndValidationSeconds':time.monotonic()-start,'static':sg,'dynamic':dg,'build':b,'boundary':'Phase sum includes standalone NodeProf target extraction. It excludes source cloning, inventory and post-transform validation. Fusion occurs inside transformer and is not separately estimated.'})
    write(c.out/'rq4/preparation-cost.json',{'status':'running','rows':rows})
 write(c.out/'rq4/preparation-cost.json',{'status':'completed','scope':'core qualification' if qualification else 'full formal cohort','rows':rows})
 gate=completion_gate(c.protocol,c.qualified,[(r['library'],r['arm']) for r in rows if r.get('valid')],[(r['library'],r['arm']) for r in rows if not r.get('valid')])
 c.record['stages'].append(dict(gate,name='rq4',formalResult=not qualification));c.save()
