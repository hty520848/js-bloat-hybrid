"use strict";
import fs from 'fs';
import tar from 'tar';
import path from 'path';

class Stubbifier {
    constructor(filePath, testingMode = false) {
        this.filePath = filePath;
        this.stubMap = new Map();
        this.testingMode = testingMode;
    }

    copyFunctionProperties (source, dest) {
        // copy the associated properties
        try {
            if (!source || source === null) {
                throw new Error('source is not defined for ' + dest);
            }
            for (var prop in source) {
                dest[prop] = source[prop];
            }
            Object.keys(source).forEach(function (key) {
                dest[key] = source[key];
            });
            dest.prototype = source.prototype;
        }
        catch (error) {
            // console.error('[copyFunctionProperties] ' + error);
            // console.error('Error in: ' + this.filePath);
        }
        return dest;
    }

    getStub(functionName) {
        return this.stubMap.get(functionName);
    }

    setStub(functionName, evaledFunString) {
        this.stubMap.set(functionName, evaledFunString);
    }

    getCode(searchName) {
        if (!fs.existsSync(this.filePath + '.dir')) {
            tar.x({
                file: this.filePath + '.dir' + '.tgz',
                sync: true,
                cwd: path.dirname(this.filePath)
            }); // , [this.filePath + '.dir' + '.tgz']);
        }
        // StubFunction records expansion bytes separately; do not inject
        // console diagnostics into a client's production bundle.
        var filename = this.filePath + ".dir/" + searchName + ".BIGG";
        if(this.testingMode && process.env.HYBRID_PAYLOAD_OUT) {
            fs.mkdirSync(process.env.HYBRID_PAYLOAD_OUT,{recursive:true});
            fs.appendFileSync(path.join(process.env.HYBRID_PAYLOAD_OUT,'payload-'+process.pid+'.jsonl'),JSON.stringify({kind:'function',path:filename,bytes:fs.statSync(filename).size})+'\n');
        }
        return fs.readFileSync(filename, 'utf-8');
    }
}

export {Stubbifier};
export default Stubbifier;
