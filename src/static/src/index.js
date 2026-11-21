// import { Command } from 'commander';
const { Command } = require('commander');
const program = new Command();
const { checkDirectoryValidate, getAllFiles, getAllFilesRaw } = require('./utils/file')
const astVisitor = require('./graph/astVisitor')
const binding = require('./graph/binding')
const pessimistic = require('./graph/pessimistic')
const fs = require('fs')
const path = require('path')
const JSONStream = require('JSONStream');
//
const options = {
  // analysisDir: 'src/test/Data/doctrine/lib',
  // analysisDir: 'src/test/Data/express/lib',
  // analysisDir: 'src/test/Data/passport/lib',
  // analysisDir: 'src/test/Data/request/lib',
  // analysisDir: 'src/test/Data/jshint/src',
  analysisDir: 'mcg/src/jieguo/Data/css-loader',
  // analysisDir: 'mcg/src/test/Data/body-parser',
  // analysisDir: 'mcg/src/test/Data/body-parser/node_modules/debug',
  // analysisDir: 'src/test/Data/debug/src',
  // analysisDir: 'src/result/memfs/src',
  // analysisDir: 'mcg/src/test/exper/mime-types',
  // analysisDir: 'mcg/src/test/Data/body-parser/node_modules/qs',
  // analysisDir: 'mcg/src/test/Data/compression',
  // analysisDir: 'mcg/src/test/Data/compression/node_modules/accepts',
  // analysisDir: 'mcg/src/test/Data/body-parser/analysis_dir/static/debug',
  output: ['mcg/src/test/nodes/donctrine/static.log', 'b.json'],
  style: 'v8',
  time: true,
  od: 'src/result',
  v8: true,
  count: true,
};
program
  .name('Full-Js-CallGraph')
  .version('0.0.1')
  .description('javascript callgraph')
  .option("-d, --analysisDir directory <directory>", "base directory for files to analyse")
  .option("-o, --output result <xxx.json>", "output of analyse result")
  .option("-s, --output style", "output of V8 style column numbers")
  // .option("-t, --time <millisecond>", "analysis time")
  .action(main)
  .parse();
function addNode(edge, v) {
  if (v.type === 'NativeCalleeVertex') {

    let nd = v.call
    edge.label = 'NativeCallee(' + v.name + ')';
    edge.file = nd.mes.split('<')[0];
    edge.start = { row: v.loc.start.line, column: v.loc.start.column };
    edge.end = { row: v.loc.end.line, column: v.loc.end.column };
    edge.range = { start: nd.call.range[0], end: nd.call.range[1] };
    return edge;
  }
  if (v.type === 'CalleeVertex') {
    let nd = v.call;

    edge.label = astVisitor.encFuncName(nd.attr.enclosingFunction);
    edge.file = nd.attr.enclosingFile;
    edge.path = nd.attr.path;
    edge.start = { row: nd.loc.start.line, column: nd.loc.start.column };
    edge.end = { row: nd.loc.end.line, column: nd.loc.end.column };
    edge.range = { start: nd.range[0], end: nd.range[1] };
    return edge;
  }
  if (v.type === 'FuncVertex') {
    edge.label = astVisitor.funcname(v.func);
    edge.file = v.func.attr.enclosingFile;
    edge.path = v.func.attr.path;
    edge.start = { row: v.func.loc.start.line, column: v.func.loc.start.column };
    edge.end = { row: v.func.loc.end.line, column: v.func.loc.end.column };
    edge.range = { start: v.func.range[0], end: v.func.range[1] };
    return edge;
  }
  if (v.type === 'NativeVertex') {
    //'Math_log' (Native)
    edge.label = v.name;
    edge.file = "Native";
    edge.start.row = v.loc.start.row;
    edge.end.row = v.loc.end.column;
    edge.start.column = v.loc.start.column;
    edge.end.column = v.loc.end.column;
    edge.range = { start: null, end: null };
    return edge;
  }
  throw new Error("strange vertex: " + v);
};

function buildBinding(call, fn) {
  let edge = {
    source: {
      label: null,
      file: null,
      start: { row: null, column: null },
      end: { row: null, column: null },
      range: { start: null, end: null }
    },
    target: {
      label: null,
      file: null,
      start: { row: null, column: null },
      end: { row: null, column: null },
      range: { start: null, end: null }
    }
  };
  addNode(edge.source, call);
  addNode(edge.target, fn);
  return edge;
};

function pp(v, baseDirToCut, v8Style) {

  if (v.fake) return v.func.attr.enclosingFile.replace(/\\/g, "/") + ':<' + v.func.loc.start.line + ',' + v.func.loc.start.column + '>--<' + v.func.loc.end.line + ',' + v.func.loc.end.column + '>'
  if (v.type === 'CalleeVertex')
    return astVisitor.ppPos2(v.call, baseDirToCut, v8Style);
  if (v.type === 'FuncVertex')
    return astVisitor.ppPos2(v.func, baseDirToCut, v8Style);
  if (v.type === 'NativeVertex')
    return astVisitor.ppPos2(v, baseDirToCut, v8Style, 'nativeFunc');
  // return v.name + '<' + v.loc.start.line + ':' + v.loc.start.column + ',' + v.loc.end.line + ':' + v.loc.end.column + '>';
  if (v.type === 'NativeCalleeVertex')
    return astVisitor.ppPos2(v, baseDirToCut, v8Style, 'nativeCallee');
  throw new Error("strange vertex: " + v);
}

function main() {
  for (const opt of Object.getOwnPropertyNames(program.opts())) {
    options[opt] = program.opts()[opt]
  }
  options.analysisDir = process.argv[2]  // 分析目录
  options.output = [].concat(process.argv[3]) // 输出地址

  if (!options.analysisDir) {
    throw Error('you should input analysis directory or file')
  }

  if (!checkDirectoryValidate(options.analysisDir)) {
    throw Error('handling analysis directory error,please check the input directory and try again')
  }
  console.time(`********static analysis********`);
  // Reviewer-2.2.1: a switch that is never reached and a switch that is
  // reached but never decisive produce the same graph. Record which one it was.
  if (process.env.MCG_ABLATION_STATS) {
    global.__MCG_ABLATION = {
      indexDisabled: process.env.MCG_DISABLE_INDEX,
      moduleFilterDisabled: process.env.MCG_DISABLE_MODULE_FILTER,
      scopeRestricted: Boolean(process.env.SQJ_SCOPE_FILES),
      parseExtraDirs: process.env.MCG_PARSE_EXTRA_DIRS || '',
    };
  }
  let styleResult = new Set()
  let entry_file, packageJson
  try {
    packageJson = JSON.parse(fs.readFileSync(path.join(options.analysisDir, 'package.json'), 'utf8'));
    if (packageJson.main) {
      entry_file = packageJson.main;
    } else {
      entry_file = 'index.js'
    }

  } catch {
    entry_file = 'index.js'
  }
  let mian_files, modules_main_files = new Map()
  const production = require('./utils/dependencies').productionPackages(options.analysisDir);
  let allAnalyseFiles = getAllFiles(options.analysisDir, true, []);
  mian_files = allAnalyseFiles;
  // Reviewer-2.2.1 ablation hook. When the analysis directory is itself scope
  // restricted (SQJ_SCOPE_FILES), every parsed file is inside the scope and the
  // module-scope switch cannot change anything. Parsing extra roots that are
  // deliberately outside the scope makes call sites in tests and sibling
  // modules exist in the graph, while main_files stays the scoped set. The only
  // variable that changes between arms is then still MCG_DISABLE_MODULE_FILTER.
  if (process.env.MCG_PARSE_EXTRA_DIRS) {
    for (const dir of JSON.parse(process.env.MCG_PARSE_EXTRA_DIRS)) {
      allAnalyseFiles = allAnalyseFiles.concat(getAllFilesRaw(dir, true, []));
    }
  }
  const dep_list = Object.keys(packageJson.dependencies || {});
  for (const [dir] of production) {
    const files = getAllFiles(dir, true, []);
    modules_main_files.set(dir, files);
    allAnalyseFiles = allAnalyseFiles.concat(files);
  }
  allAnalyseFiles = [...new Set(allAnalyseFiles)];

  var ast = astVisitor.astFromFiles(allAnalyseFiles);
  if (ast.programs.size !== allAnalyseFiles.length) {
    throw new Error('Incomplete parsing of the frozen source cohort: ' + ast.programs.size + '/' + allAnalyseFiles.length);
  }
  for (let fileAst of ast.programs.values()) {
    binding.addBindings(fileAst);
  }
try {
  var forest = astVisitor.mergeAst(ast, options.analysisDir, entry_file, dep_list)
} catch (error) {
  throw error;
}
 

  let cgs = []
  for (let tree of forest) {
    cgs.push(pessimistic.buildCallGraph(tree, mian_files, dep_list))
  }

  for (let i = 0; i < cgs.length; i++) {
    cgs[i].edges.iter(function (call, fn) {
      let start = pp(call, options.analysisDir, options.v8)
      let end = pp(fn, options.analysisDir, options.v8)
      if (start.split(':<')[1] != end.split(':<')[1])
        if (end.includes('Native') && start.includes('1:0,1:0') || !end.includes('Native'))
          styleResult.add(start + " -> " + end)
    });
  }
  // 对依赖的包进行调用图分析

  for (const [module_path, module_package] of production) {
    const module_files = modules_main_files.get(module_path) || [];
    let module_entry = module_package.main, module_dep = []
    if (module_package.dependencies) {
      module_dep = Object.keys(module_package.dependencies)
    }

    if (!module_package.main) {
      module_entry = 'index.js'
    }

    if (!module_entry.includes('.js')) {
      module_entry = module_entry + '.js'
    }
    let tree = astVisitor.mergeAst(ast, module_path, module_entry, module_dep)
    if(tree.length!=0){
      let modlue_cg = pessimistic.buildCallGraph(tree[0], module_files)
      modlue_cg.edges.iter(function (call, fn) {
        let start = pp(call, options.analysisDir, options.v8)
        let end = pp(fn, options.analysisDir, options.v8)
        if (start.split(':<')[1] != end.split(':<')[1])
          if (end.includes('Native') && start.includes('1:0,1:0') || !end.includes('Native'))
            styleResult.add(start + " -> " + end)
      });
    } 
   
  }

  console.timeEnd(`********static analysis********`);

  // let result = [];


   if (options.output !== null) {
    let filename = options.output[0];
    fs.writeFile(filename, JSON.stringify([...styleResult], null, 2), function (err) {
      if (err) {
        /*
        When happened something wrong (usually out of memory when we want print
        the result into a file), then we try to file with JSONStream.
         */
        let transformStream = JSONStream.stringify();
        let outputStream = fs.createWriteStream(filename);
        transformStream.pipe(outputStream);
        styleResult.forEach(transformStream.write);
        transformStream.end();
      }
    });

  }

  if (process.env.MCG_ABLATION_STATS) {
    global.__MCG_ABLATION.analysedFiles = allAnalyseFiles.length;
    global.__MCG_ABLATION.forestTrees = forest.length;
    global.__MCG_ABLATION.emittedEdges = styleResult.size;
    fs.writeFileSync(process.env.MCG_ABLATION_STATS, JSON.stringify(global.__MCG_ABLATION, null, 1));
  }

}
