// DO NOT INSTRUMENT
// Reconstruction from the manuscript, surviving node_prof.json files, and the
// recovered NodeProf 20.2.0-dev callback API. This is not the lost original hook.
"use strict";

(function (sandbox) {
  const fs = require("fs");
  const path = require("path");
  const root = path.resolve(process.env.BLOAT_DYN_ROOT || process.cwd());
  const output = process.env.BLOAT_DYN_OUT;
  if (!output) throw new Error("Set BLOAT_DYN_OUT to a new output file");
  if (fs.existsSync(output) || fs.existsSync(output + ".meta.json")) {
    throw new Error("Refusing to overwrite dynamic-analysis results: " + output);
  }

  const graph = new Map();
  const frames = [];
  let lastCall;
  let stackMismatches = 0;
  let userEntries = 0;
  let nativeEntries = 0;
  let handling = false;
  const locations = new Map();
  const sourceRecords = new Map();
  const production = require('../static/src/utils/dependencies').productionPackages(root);
  const productionRoots = Array.from(production.keys());
  const sourceFiles=new Set();
  function collectFiles(directory, skipModules) {
    for (const entry of fs.readdirSync(directory,{withFileTypes:true})) {
      if (['.git','coverage','.nyc_output'].includes(entry.name) || (skipModules && entry.name==='node_modules')) continue;
      const filename=path.join(directory,entry.name);
      if (entry.isDirectory()) collectFiles(filename,true);
      else if (entry.isFile() && /\.(js|ts|mjs|cjs)$/.test(entry.name)) sourceFiles.add(filename);
    }
  }
  if (!process.env.SQJ_SCOPE_FILES) throw new Error('Explicit common SQJ_SCOPE_FILES required');
  const scope = JSON.parse(fs.readFileSync(process.env.SQJ_SCOPE_FILES, 'utf8'));
  for (const relative of scope.files) sourceFiles.add(path.resolve(root, relative));
  const filterAudit = { included: [], excludedCount: 0, excludedSamples: [] };
  const nativeEdges = process.env.BLOAT_DYN_NATIVE === '1';

  function location(iid) {
    if (locations.has(iid)) return locations.get(iid);
    let value = String(sandbox.iidToLocation(iid));
    if (value[0] === "(" && value[value.length - 1] === ")") {
      value = value.slice(1, -1);
    }
    // Keep the historical file:line:column:line:column/synthetic-node format.
    const match = value.match(/^(.*?)(:\d+:\d+:\d+:\d+|:\{\{.*\}\})$/);
    if (match && path.isAbsolute(match[1])) {
      value = path.relative(root, match[1]).split(path.sep).join("/") + match[2];
    }
    locations.set(iid, value);
    return value;
  }

  function functionName(f) {
    return typeof f === "function" && f.name ? f.name : "anon";
  }

  function enter(kind, key, label) {
    const caller = frames.length ? frames[frames.length - 1].label : "system (Native)";
    if (!graph.has(caller)) graph.set(caller, new Set());
    graph.get(caller).add(label);
    frames.push({ kind: kind, key: key, label: label });
  }

  function leave(kind, key) {
    const frame = frames.pop();
    if (!frame || frame.kind !== kind || frame.key !== key) stackMismatches++;
  }

  const analysis = {
    invokeFunPre: function (iid, f) {
      lastCall = { iid: iid, f: f };
    },
    invokeFun: function () {
      lastCall = undefined;
    },
    functionEnter: function (iid, f) {
      userEntries++;
      if (!sourceRecords.has(iid)) {
        const loc = location(iid), match = loc.match(/^(.*):(\d+):(\d+):(\d+):(\d+)$/);
        if (match && !/(^|\/)(__tests__|test|tests)(\/|$)/.test(match[1])) {
          const filename = path.resolve(root, match[1]);
          if (sourceFiles.has(filename)) sourceRecords.set(iid, {
            label:functionName(f) + ' (' + loc + ')', name:functionName(f), location:loc,
            source:sandbox.iidToSourceObject(iid), code:sandbox.iidToCode(iid)
          });
        }
      }
      enter("user", iid, functionName(f) + " (" + location(iid) + ")");
    },
    functionExit: function (iid) {
      // Unlike invokeFun, functionExit also runs when a user function throws.
      leave("user", iid);
    },
    builtinEnter: function (name, f) {
      nativeEntries++;
      const site = lastCall && lastCall.f === f ? "(" + location(lastCall.iid) + ")" : "";
      enter("native", f, functionName(f) + " (Native)" + site);
      lastCall = undefined;
    },
    builtinExit: function (name, f) {
      leave("native", f);
    },
    endExecution: function () {
      fs.writeFileSync(output + '.sources.json',JSON.stringify(Array.from(sourceRecords.values()),null,2)+'\n',{flag:'wx'});
      const openFrames = frames.map(function (frame) { return { kind: frame.kind, label: frame.label }; });
      const result = Object.create(null);
      for (const caller of Array.from(graph.keys()).sort()) {
        result[caller] = Array.from(graph.get(caller)).sort();
      }
      fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", { flag: "wx" });
      fs.writeFileSync(output + ".meta.json", JSON.stringify({
        provenance: "reconstructed; not the original project-specific dyn.js",
        exactPaperHook: false,
        format: "legacy-nodeprof-adjacency",
        root: root,
        userEntries: userEntries,
        nativeEntries: nativeEntries,
        nativeEdges: nativeEdges,
        stackMismatches: stackMismatches,
        remainingFrames: openFrames.length,
        remainingUserFrames: openFrames.filter(function (frame) { return frame.kind === "user"; }).length,
        remainingApplicationFrames: openFrames.filter(function (frame) {
          return frame.kind === 'user' && !frame.label.includes('../');
        }).length,
        instrumentationScope: 'frozen common published-own and production-dependency file manifest; excludes harness, test frameworks and synthetic VM bundles',
        sourceFilter: filterAudit,
        openFrames: openFrames,
        callers: graph.size,
        edges: Array.from(graph.values()).reduce(function (n, values) { return n + values.size; }, 0),
      }, null, 2) + "\n", { flag: "wx" });
    },
  };
  // The bloat decision uses user-function reachability. Global builtin
  // callbacks also instrument excluded Jest/Babel machinery in NodeProf 20,
  // making startup prohibitively expensive. Keep the full legacy mode opt-in.
  if (!nativeEdges) {
    ['invokeFunPre', 'invokeFun', 'builtinEnter', 'builtinExit'].forEach(function (name) { delete analysis[name]; });
  }
  // Old NodeProf can report native operations used by the analysis itself.
  // Exclude re-entry so Map/Array/JSON operations do not pollute the graph.
  Object.keys(analysis).forEach(function (name) {
    const callback = analysis[name];
    analysis[name] = function () {
      if (handling) return;
      handling = true;
      try {
        return callback.apply(this, arguments);
      } finally {
        handling = false;
      }
    };
  });
  sandbox.addAnalysis(analysis, function (source) {
    if (source.internal) {filterAudit.excludedCount++; return false;}
    const rawName = String(source.name);
    // Calling Node's path helpers here recursively triggers this source filter
    // in NodeProf 20. Normalize with string operations instead.
    const segments=(rawName[0] === '/' ? rawName : root+'/'+rawName).split('/');
    const normalized=[];
    for (const segment of segments) {
      if (segment==='..') normalized.pop();
      else if (segment && segment!=='.') normalized.push(segment);
    }
    const name='/'+normalized.join('/');
    const application = name.startsWith(root + '/') && !name.slice(root.length+1).split('/').includes('node_modules');
    const dependency = productionRoots.some(function (dir) { return name.startsWith(dir + path.sep); });
    // VM bundles use synthetic names such as test.js. They do not have an
    // original AST/file range and cannot be mapped to transformation inputs.
    const include = sourceFiles.has(name) && (application || dependency);
    if (include) filterAudit.included.push(name);
    else {
      filterAudit.excludedCount++;
      if (filterAudit.excludedSamples.length < 20) filterAudit.excludedSamples.push(rawName);
    }
    return include;
  });
})(J$);
