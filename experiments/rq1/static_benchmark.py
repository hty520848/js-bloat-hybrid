import zipfile
from pathlib import Path
from ..common import ROOT,read,write,sha

# Reviewer 2.2.1 asks for an isolated evaluation of the enhanced static
# component. A 2x2 factor needs four cells; the historical run only had three
# (full / no-index / no-module-filter) and therefore could not observe the
# interaction between index resolution and module scoping.
ARMS={
 'full':{},
 'no-index':{'MCG_DISABLE_INDEX':'1'},
 'no-module-filter':{'MCG_DISABLE_MODULE_FILTER':'1'},
 'no-both':{'MCG_DISABLE_INDEX':'1','MCG_DISABLE_MODULE_FILTER':'1'},
}
# Arms used only by the supplement: `no-file-scope` drops the paper 2.1 file
# range step (tests and dev-only sources enter the forest) and keeps both
# runtime switches on, so it contrasts the analysis input, not the guards.
EXTRA_ARMS={'no-file-scope':{}}
def flags(arm):
 """Single source of truth for arm -> environment.

 An arm name that is not in the table raises. Silently falling back to "all
 switches on" is how five nominally different arms were once run with identical
 flags, producing a complete set of zero differences that looked like a
 finding."""
 table=dict(ARMS);table.update(EXTRA_ARMS)
 if arm not in table:raise KeyError('Unknown static ablation arm: '+arm)
 e={'MCG_DISABLE_INDEX':'0','MCG_DISABLE_MODULE_FILTER':'0'};e.update(table[arm]);return e
def canonical_arm(arm):
 """Accept the protocol spelling (`mcg-only`, `mcg-no-index`, ...) and the short
 spelling. The protocol and the benchmark row used two vocabularies, and a
 name that fell through the comparison silently kept both switches on."""
 aliases={'mcg-only':'full','mcg-no-index':'no-index','mcg-no-module-filter':'no-module-filter','mcg-no-both':'no-both','hybrid':'full'}
 return aliases.get(arm,arm)

MULTIFILE_LIBRARIES = ('debug', 'express', 'jshint', 'request', 'passport', 'doctrine')

def run_multifile(c, library=None):
 subjects = [library] if library else MULTIFILE_LIBRARIES
 if not set(subjects) <= set(MULTIFILE_LIBRARIES):
  raise ValueError('Unknown multi-file subject: '+library)
 root = Path(c.machine['staticMultifileRoot'])
 rows = []
 for subject in subjects:
  source = root / subject
  identity = read(source / 'package.json')
  for arm in ('full', 'no-module-filter'):
   output = c.out / 'rq1' / 'static-multifile' / (subject+'-'+arm+'.json')
   output.parent.mkdir(parents=True, exist_ok=True)
   stage = c.run('static-multifile-'+subject+'-'+arm,
                 [c.machine['nodeStatic'], ROOT/'src/static/src/index.js', source, output],
                 c.work, dict(flags(arm), NODE_PATH=c.machine['staticNodeModules']))
   valid = stage['exitCode']==0 and output.is_file()
   rows.append(dict(library=subject, version=identity['version'], arm=arm, valid=valid,
                    edges=len(read(output)) if valid else None, stage=stage))
 write(c.out / 'rq1' / 'static-multifile.json', rows)
 return all(row['valid'] for row in rows)

def run(c, program=None):
 ref=read(ROOT/'datasets/manifests/static-benchmark.json');archive=ROOT/'artifacts/StaticJSCallGraphs.zip'
 if not archive.is_file() or sha(archive)!=ref['annotationsSha256']:
  write(c.out/'rq1/static-benchmark.json',{'status':'blocked','reason':'Missing authenticated annotation archive'});return
 rows=[];queue=[];arms=list(ARMS)
 sources=[p for p in ref['sources'] if program is None or p['name']==program]
 if not sources:raise ValueError('Unknown static benchmark program: '+str(program))
 source_root=Path(c.machine.get('staticSourceRoot',ROOT/'artifacts/sunspider'))
 with zipfile.ZipFile(str(archive)) as z:
  for p in sources:
   source=source_root/p['name'];assert sha(source)==p['sha256']
   labels=__import__('json').loads(z.read('results/SunSpider/compared-evaluated/poshandled_'+source.stem+'.json').decode('utf-8'))
   ids={n['id']:n['pos'] for n in labels['nodes']};judged={ids[e['source']]+'->'+ids[e['target']]:e['valid'] for e in labels['links'] if 'valid' in e}
   positive={k for k,v in judged.items() if v};negative={k for k,v in judged.items() if not v}
   for arm in arms:
    out=c.out/'rq1/static'/(source.stem+'-'+arm+'.json');out.parent.mkdir(parents=True,exist_ok=True)
    stats=out.with_suffix('.ablation.json')
    st=c.run('rq1-sunspider-'+source.stem+'-'+arm,[c.machine['nodeStatic'],ROOT/'experiments/rq1/single_benchmark.js',ROOT/'src/static',source,out],ROOT,dict({'NODE_PATH':c.machine['staticNodeModules'],'MCG_ABLATION_STATS':str(stats)},**flags(arm)))
    d=read(out) if out.is_file() else {};pred=set(d.get('edges',[]));defs={n['file']+':'+str(n['line'])+':'+str(n['column']+1) for n in d.get('functionDefinitions',[])}
    unmatched=sorted({v for edge in positive for v in edge.split('->') if v.startswith(source.name+':') and v not in defs})
    tp=len(pred&positive);fp=len(pred&negative);unknown=sorted(pred-set(judged))
    rows.append({'file':source.name,'arm':arm,'armFlags':flags(arm),'stage':st,'valid':st['exitCode']==0 and not unmatched,'annotationPositionAligned':not unmatched,'unmatchedNodes':unmatched,'TP':tp,'knownFP':fp,'knownFN':len(positive-pred),'unjudged':len(unknown),'predicted':len(pred),'knownPositiveCount':len(positive),'precisionLowerBound':tp/len(pred) if pred else None,'precisionUpperBound':(tp+len(unknown))/len(pred) if pred else None,'knownPositiveRecall':tp/len(positive) if positive else None,'ablation':read(stats) if stats.is_file() else None,'sourceSha256':sha(source)})
    queue.extend({'file':source.name,'arm':arm,'edge':edge,'verdict':'UNJUDGED','sourceSha256':sha(source)} for edge in unknown)
    write(c.out/'rq1/static-benchmark.json',{'status':'running','rows':rows})
 write(c.out/'rq1/static-benchmark.json',{'status':'completed' if len(rows)==len(sources)*len(arms) and all(x['valid'] for x in rows) else 'invalid','rows':rows,'arms':arms,'factorial':'indexResolution x moduleScope, 2x2; no-both is the only cell absent from the historical run','limitations':ref['limitations']});write(c.out/'rq1/adjudication-queue.json',queue)
