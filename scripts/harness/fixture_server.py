"""Local HTTP/TLS fixtures for expired external test endpoints.

This is a reconstructed test environment, not the original remote services.
"""
import atexit
import os
import json
import ssl
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path

ROOT=Path(os.environ['HYBRID_HARNESS_ROOT'])
HTTP_PORT=45571
HTTPS_PORT=45572
class Server(ThreadingMixIn, HTTPServer):
    daemon_threads=True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, code, content, kind):
        self.send_response(code)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(content)))
        self.end_headers();self.wfile.write(content)
    def do_GET(self):
        fixtures=ROOT/'environment/test-fixtures/network'
        route=self.path.split('?')[0]
        boilerplates={'/boilerplates/harp-boilerplates/default/master.zip':'harp-boilerplates-default.zip',
            '/boilerplates/harp-boilerplates/hb-start/master.zip':'harp-boilerplates-hb-start.zip',
            '/boilerplates/zeke/harp-sample/master.zip':'zeke-harp-sample.zip'}
        if route in boilerplates:
            archive=ROOT/'environment/test-fixtures/harp-boilerplates'/boilerplates[route]
            if archive.is_file():self.send(200,archive.read_bytes(),'application/zip')
            else:self.send(404,b'Missing verified boilerplate archive','text/plain')
            return
        name={'/db':'jsonplaceholder-db.json','/image.png':'image.png','/CODE_OF_CONDUCT.md':'webpack-code-of-conduct.md'}.get(self.path.split('?')[0])
        if name and (fixtures/name).is_file():
            kind='image/png' if name.endswith('.png') else 'application/json' if name.endswith('.json') else 'text/plain'
            self.send(200,(fixtures/name).read_bytes(),kind)
        else:
            request=urllib.parse.unquote(self.path.split('?')[0]).lstrip('/')
            if request.startswith('tarballs/'):
                filename=request.split('/')[-1];kind='application/octet-stream'
            else:
                filename=urllib.parse.quote(request,safe='')+'.json';kind='application/json'
            cache=ROOT/'environment/client-cache/npm-mirror'/filename
            if cache.is_file():self.send(200,cache.read_bytes(),kind);return
            if _restore_downloads:
                state=ROOT/'results/repair-audit-001/registry-gateway.json'
                if state.is_file():
                    try:
                        gateway=json.loads(state.read_text())['url']
                        with urllib.request.urlopen(gateway+self.path,timeout=120) as response:content=response.read()
                        self.send(200,content,kind);return
                    except Exception as error:self.send(502,str(error).encode(),'text/plain');return
            self.send(404,b'Fixture not restored in frozen cache','text/plain')
    def do_POST(self):
        if self.headers.get('Transfer-Encoding','').lower() == 'chunked':
            chunks=[]
            while True:
                length=int(self.rfile.readline().split(b';')[0].strip(),16)
                if not length:
                    while self.rfile.readline().strip(): pass
                    break
                chunks.append(self.rfile.read(length));self.rfile.read(2)
            request=b''.join(chunks)
        else:request=self.rfile.read(int(self.headers.get('Content-Length','0')))
        # example.com is a placeholder, not a SOAP provider. The frozen async
        # tests explicitly expect rejected calls. Reconstruct a deterministic
        # fault endpoint while preserving the outgoing request/header behavior.
        if b'<html' in request:
            body='<soap:Fault><faultcode>soap:Client</faultcode><faultstring>Invalid html SOAP request</faultstring></soap:Fault>'
            status=500
        else:
            body='<soap:Fault><faultcode>soap:Server</faultcode><faultstring>Unimplemented example fixture operation</faultstring></soap:Fault>';status=500
        response=('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'+body+'</soap:Body></soap:Envelope>').encode()
        self.send(status,response,'text/xml')

_servers=[]
_restore_downloads=False
def start(allow_downloads=False):
    global _restore_downloads
    _restore_downloads=allow_downloads
    if _servers:return
    http=Server(('127.0.0.1',HTTP_PORT),Handler)
    try:
        https=Server(('127.0.0.1',HTTPS_PORT),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.load_cert_chain(str(ROOT/'environment/test-fixtures/reload/test-only.crt'),str(ROOT/'data/clients/serve-static/reload/test/api/https/test-only.key'))
        https.socket=context.wrap_socket(https.socket,server_side=True)
    except Exception:
        http.server_close();raise
    _servers.extend([http,https])
    for server in _servers:
        threading.Thread(target=server.serve_forever,daemon=True).start()
    atexit.register(stop)
def stop():
    for server in _servers:server.shutdown();server.server_close()
    _servers[:]=[]

if __name__ == "__main__":
 import time
 start(allow_downloads=False)
 print("Frozen local fixture service ready", flush=True)
 while True:time.sleep(30)
