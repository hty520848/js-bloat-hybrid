#!/usr/bin/env python3
"""Download immutable inputs; validate SHA256 before use. No npm install scripts."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def get(url,dest,expected):
 dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest()==expected:return
 tmp=dest.with_suffix(dest.suffix+'.partial')
 with urllib.request.urlopen(url,timeout=60) as response,tmp.open('wb') as f:
  while True:
   b=response.read(1024*1024)
   if not b:break
   f.write(b)
 assert hashlib.sha256(tmp.read_bytes()).hexdigest()==expected,'SHA256 mismatch: '+url
 tmp.replace(dest)
def main():
 libs=json.loads((R/'datasets/manifests/libraries.json').read_text())
 for x in libs:get(x['dist']['tarball'],R/'artifacts/npm'/x['archive'],x['sha256'])
 ref=json.loads((R/'datasets/manifests/static-benchmark.json').read_text())
 get(ref['annotationsUrl'],R/'artifacts/StaticJSCallGraphs.zip',ref['annotationsSha256'])
 for x in ref['sources']:get(x['url'],R/'artifacts/sunspider'/x['name'],x['sha256'])
 print('All frozen downloads verified. Prepare production dependencies and complete target/client harnesses before formal runs.')
if __name__=='__main__':main()
