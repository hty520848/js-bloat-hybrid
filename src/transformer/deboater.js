const fs = require("fs");
const path = require("path");
const { stubFunction } = require("./stubFunction.js");
const { execSync } = require('child_process');
const { flagFunctionForStubbing } = require("./functionFlagging.js");
const { stubFile } = require("./stubFile.js");
const {
  getTargetFromStatic,
  getTargetsFromCoverageReport,
  getTargetsFromACG,
  buildHappyName,
  getFileName,
  getAllFiles,
  shouldStubbify,
  generateBundlerConfig,
  fileFunctionCount,
  staticgetFromACG
} = require("./stubUtils.js");

let removedFunctionCount = 0;
let bundlerMode = "no"; // default: don't bundle
let bundleOptions = {
  no: "no",
  only_bundle: "only_bundle",
  stub_bundle: "stub_bundle",
  bundle_and_stub: "bundle_and_stub"
  // no, only_bundle, stub_bundle, bundle_and_stub
}

// RQ2 needs runtime probes, while RQ1 should be able to measure deployable
// code without those probes. Enable instrumentation only when requested.
let testingMode = process.env.STUBBIFIER_INSTRUMENTATION === "1";
let safeEvalMode = false;
let recurseThroughDirs = true;
let cur_dir = `Data/${process.argv[3]}`;
// let cur_dir = `Data/memfs`;
// console.log('Reading ' + filename);

let callgraphpath = path.join(cur_dir, 'static.csv');
let sscg_path = path.join(cur_dir, 'sscg_path.csv');
let node_profpath = path.join(cur_dir, 'node_prof.json')
let coverageReportPath = path.join(cur_dir, 'coverage/coverage-final.json');
let removeFunsPath = null;
let functions = [];
let listedFiles = new Set()
let removeFuns = [];
let noCG = true;
let uncoveredMode = true;
let depList;

// 合并动态分析与静态分析结果
let targets = []

let analysis_mode = process.argv[2]
// let analysis_mode =  'sscg'
const startTime = new Date().getTime();
if (analysis_mode == 'static') {
  targets = getTargetFromStatic(callgraphpath)
  functions = [...new Set(targets.map(item => path.join(__dirname, item)).map(buildHappyName))]
}
else if (analysis_mode == 'sscg') { 
   const rawTargets = staticgetFromACG(sscg_path);
   targets = require('./codeqlTargets').getCodeQLTargets(rawTargets, path.join(__dirname, cur_dir), cur_dir, __dirname);
  functions = [...new Set(targets.map(item => path.join(__dirname, item)).map(buildHappyName))];
  targets.map(getFileName).forEach(item => listedFiles.add(item));
  noCG = false;
}
else if (analysis_mode == 'sdcg') {
  targets = getTargetsFromCoverageReport(coverageReportPath);
  functions = [...new Set(targets.map(item => path.join(__dirname, item)).map(buildHappyName))]
} else {
  targets = getTargetsFromACG(callgraphpath, node_profpath, coverageReportPath, cur_dir);
  functions = [...new Set(targets.map(item => path.join(__dirname, item)).map(buildHappyName))]

}
targets.forEach(item => {
  listedFiles.add(path.join(__dirname, getFileName(item)))
})
// let ddtargets = getTargetsFromCoverageReport(coverageReportPath);
// let ddfunctions = ddtargets.map(buildHappyName);
noCG = false;

let zipFiles = false; // Currently don't ever do this.
if (removeFunsPath) {
  removeFuns = getTargetsFromACG(removeFunsPath).map(buildHappyName);
}
// console.log(path.join(__dirname,cur_dir, 'dep_list.txt'));
depList = fs.readFileSync(path.join(__dirname, cur_dir, 'dep_list.txt'), 'utf-8').split("\n");

if (bundlerMode != "no") {
  if (bundlerMode == "bundle_and_stub" || bundlerMode == "only_bundle") {
    let files = getAllFiles(path.join(__dirname, cur_dir), recurseThroughDirs);
    files.forEach(function (file, index) {
      let curPath = cur_dir + file;
      curPath = file;
      if (shouldStubbify(curPath, file, depList)) { // don't even try to stub externs
        if (noCG || listedFiles.indexOf(curPath) > -1) { // file is reachable, so only stubify functions
          console.log("FUNCTION CASE: flagging to be stubbed: " + curPath);
          try {
            flagFunctionForStubbing(curPath, process.cwd(), functions, uncoveredMode);
          }
          catch (e) {
            console.log("ERROR: cannot stubbify function in: " + curPath);
            console.log(e);
          }
        }
        else {
          console.log("FILE CASE: flagging all functions to be stubbed in: " + curPath);
          try {
            flagFunctionForStubbing(curPath, process.cwd(), [], uncoveredMode);
          }
          catch (e) {
            console.log("ERROR: cannot stubbify all functions in file: " + curPath);
            // console.log(e);
          }
        }
      }
    });
    // By now, the functions that should be stubbed are flagged as such with 
    // eva("STUB_FLAG_STUB_THIS_STUB_FCT") as the first thing in the function body.
    // Now, we need to call the bundler.
    // To do this, we should just dispatch a shell command which invokes the bundler.
    // Notes:
    // 1. Bundler needs to be installed globally.
    // 2. Bundler needs to be called from the project being stubbified.
    // 3. Bundler config file is needed. 
    // create bundler config file
    generateBundlerConfig(path.resolve(path.join(__dirname, cur_dir)));
    // cd into project directory (filename is the path to the tgt project)
    // save current directory first to chdir back
    // let stubsDir = process.cwd();
    // process.chdir(path.resolve(path.join(__dirname, cur_dir)));
    // // call bundler
    // execSync('rollup --config rollup.stubbifier.config.js');
    // // cd back into stubbifier
    // process.chdir(stubsDir);
  }
  // Once bundled, we need to read in the bundle and stubbify the functions with
  // the eval.
  if (bundlerMode == "bundle_and_stub" || bundlerMode == "stub_bundle")
    stubFunction(
      path.resolve(filename) + '/stubbifyBundle.js',
      __dirname,
      new Map(),
      functions,
      removeFuns,
      uncoveredMode,
      safeEvalMode,
      testingMode,
      zipFiles,
      true);
}
else {
  // stubbing section; no bundling 
  if (fs.lstatSync(path.resolve(path.join(__dirname, cur_dir))).isDirectory()) {
    let files = getAllFiles(path.resolve(path.join(__dirname, cur_dir)), recurseThroughDirs, [], depList);
    files.forEach(function (file, index) {
      // console.log(file);
      // only stubify JS files
      let curPath = file
      // console.log("decision: " + shouldStubbify(curPath, file, depList));
      // let curAbsPath: string = process.cwd() + curPath;
      if (shouldStubbify(curPath, file, depList)) { // don't even try to stub externs
        if (noCG || [...listedFiles].indexOf(curPath) > -1) { // file is reachable, so only stubify functions
          console.log("FUNCTION CASE: " + curPath);
          try {
            removedFunctionCount += stubFunction(
              curPath,
              __dirname,
              new Map(),
              functions,
              removeFuns,
              uncoveredMode,
              safeEvalMode,
              testingMode,
              false,
              false,
              cur_dir.split('/')[cur_dir.split('/').length-1]
            );
  
          }
          catch (e) {
            console.log("ERROR: cannot stubbify function in: " + curPath);
            console.log(e);
          }
        }
        else {
          console.log("FILE CASE: " + curPath);
          try {
            // console.log(file);
            removedFunctionCount += fileFunctionCount(curPath,process.argv[3],process.argv[2])
            stubFile(curPath, safeEvalMode, testingMode, false, process.argv[3]);

          }
          catch (e) {
            console.log("ERROR: cannot stubbify file: " + curPath);
            console.log(e);
          }
        }


      }
    });
    const endTime = new Date().getTime();
    const resultRoot = process.env.STUBBIFIER_RESULT_ROOT || path.join(__dirname, 'Data');
    fs.mkdirSync(resultRoot, { recursive: true });
    if (process.argv[2] == 'hybrid') {
      fs.appendFileSync(path.join(resultRoot, 'hybird_removed_func.txt'),
       JSON.stringify({ name: cur_dir, func: removedFunctionCount,time:endTime-startTime }) + '\n');
    } else if (process.argv[2] == 'sdcg') {
      fs.appendFileSync(path.join(resultRoot, 'sdcg_removed_func.txt'), 
      JSON.stringify({ name: cur_dir, func: removedFunctionCount,time:endTime-startTime  }) + '\n');
    } else if (process.argv[2] == 'sscg') {
      fs.appendFileSync(path.join(resultRoot, 'sscg_removed_func.txt'),
       JSON.stringify({ name: cur_dir, func: removedFunctionCount,time:endTime-startTime }) + '\n');
    }else if (process.argv[2] == 'static') {
      fs.appendFileSync(path.join(resultRoot, 'static_removed_func.txt'),
       JSON.stringify({ name: cur_dir, func: removedFunctionCount,time:endTime-startTime }) + '\n');
    }
  
    // execSync(`node evalatePackageSize.js ${process.argv[2]}`, { stdio: 'inherit' });
  }
  else {
    console.log("Error: input to transformer must be a directory");
  }
}
