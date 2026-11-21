// Reconstruct external SOAP fixture transports while preserving WSDL endpoint
// strings and all outgoing XML/header assertions.
'use strict';
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const endpoints = new Set();
function collect(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory,{withFileTypes:true})) {
    const file=path.join(directory,entry.name);
    if (entry.isDirectory()) collect(file);
    else if (entry.name.endsWith('.wsdl')) {
      const source=fs.readFileSync(file,'utf8');
      const expression=/<(?:\w+:)?address\b[^>]*\blocation=["']([^"']+)["']/g;
      for (let match; (match=expression.exec(source));) {
        try {
          const url=new URL(match[1]);
          if (!['localhost','127.0.0.1','::1','[::1]'].includes(url.hostname)) endpoints.add(url.href);
        } catch (_) {}
      }
    }
  }
}
collect(path.join(process.cwd(),'test/wsdl'));
const originalHttp=http.request;
function redirect(original,protocol) {return function (...args) {
  const first = args[0];
  const parsed = typeof first === 'string' ? new URL(first) : first;
  const host = parsed.hostname || parsed.host;
  const pathname = parsed.path || parsed.pathname;
  let endpoint;
  try {endpoint=new URL((parsed.protocol || protocol)+'//'+host+(parsed.port ? ':'+parsed.port : '')+(pathname || '/')).href;}
  catch (_) {return original.apply(this,args);}
  if (endpoints.has(endpoint)) {
    const options = Object.assign({}, typeof first === 'string' ? require('url').urlToHttpOptions(parsed) : first,
      { protocol:'http:', hostname: '127.0.0.1', host: '127.0.0.1', port: 45571, path: '/soap' });
    args[0] = options;
    return originalHttp.apply(http,args);
  }
  return original.apply(this, args);
};}
http.request=redirect(originalHttp,'http:');
https.request=redirect(https.request,'https:');
