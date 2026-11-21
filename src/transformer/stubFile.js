const fs = require('fs')
const parser = require('@babel/parser')
const generate = require('@babel/generator').default;

const { transformFromAstSync } = require('@babel/core');
const babel = require('@babel/types');
const traverse = require('@babel/traverse').default;
const zlib = require('zlib')
const path = require('path')
const { Readable } = require('stream')

const MIN_FILE_STUB_LENGTH = 5; // only stub files that are > 5 lines


function processAST(ast, importStmts, exportStmts, filename, safeEvalMode = false) {
  // console.log(code);
  var output = transformFromAstSync(ast, null, {
    ast: true, plugins: [function processPlugin() {
      return {
        visitor: {
          // CallExpression(path) {
          //   if (safeEvalMode && !path.node.isNewCallExp && !(path.node.callee.type == "Super")) {
          //     //var enclosingStmtNode = path.findParent((path) => path.isStatement());
          //     //enclosingStmtNode.insertBefore(buildEvalCheck(path.node));
          //     var inAsyncFunction = path.findParent((path) => path.isFunction() && path.node.async);
          //     var newWrapperCall = buildEvalCheck(path.node, inAsyncFunction, filename);
          //     newWrapperCall.isNewCallExp = true;
          //     path.replaceWith(newWrapperCall);
          //   }
          // },

          /*
            Deal with imports.
            Imports *always* stay in the original file, and they never modify anything.
          */
          ImportDeclaration(path) {
            importStmts.push(path.node); // put node into stmt move list
            path.remove(); // yeet the node into the void
            path.skip();
          },
          /*
            Deal with exports.
            There are multiple different kinds of exports, and in some cases we need to leave
            part of the export to ensure that e.g. certain variables remain in scope.
      
            e.g.
            export const exportFoo = foo;
      
            Here, we need to leave `const exportFoo = foo`, as the assignment makes `exportFoo`
            available in the subsequent scope.
          */
          ExportDefaultDeclaration(path) {
            // Check if export has a declaration.
            if (path.node.declaration !== null) {
              // Construct new node based on the export.
              // Save the declaration that we're going to replace.
              var savedDeclaration = path.node.declaration; // the actual type here is a giant union type (88 members, don't feel like typing it)
              exportStmts["default"].push(path.node);
              // Remove the declaration.
              // path.node.declaration = null;
              // previous line of code not required: we always replace the declaration with something else
              // and, babel will not allow the ExportDefaultDeclaration to have a null declaration
              // Modify path.node to have the appropriate exports, based on the type of export it is.
              switch (savedDeclaration.type) {
                case "ClassDeclaration":
                  // TODO: Doing the same thing twice for local and exported. Ensure that this is what we want.
                  path.node.declaration = savedDeclaration.id;
                  path.replaceWith(savedDeclaration);
                  break;
                case "FunctionDeclaration":
                  path.node.declaration = savedDeclaration.id;
                  path.replaceWith(savedDeclaration);
                  break;
                default:
                  path.remove(); // in babel, identifiers count as declarations
                // 	path.node.declaration = savedDeclaration; // I don't think you can have a vardecl as a default export ...?
                /* TODO: more cases */
              }
            } else {
              // this might be unreachable with babel, but keep it around just in case
              exportStmts["default"].push(path.node);
              path.remove();
            }
            // return false;
            path.skip();
          },
          ExportNamedDeclaration(path) {
            // Check if export has a declaration.
            if (path.node.declaration !== null) {
              // Construct new node based on the export.
              // Save the declaration that we're going to replace.
              var savedDeclaration = path.node.declaration;
              // Remove the declaration.
              // path.node.declaration.parentPath.remove();
              path.node.declaration = null
              // Modify path.node to have the appropriate exports, based on the type of export it is.
              switch (savedDeclaration.type) {
                case "ClassDeclaration":
                  // TODO: Doing the same thing twice for local and exported. Ensure that this is what we want.
                  // need to have 2 different identifiers, to avoid shallow copy issues
                  path.node.specifiers.push(babel.exportSpecifier(babel.identifier(savedDeclaration.id.name),
                    babel.identifier(savedDeclaration.id.name)));
                  break;
                case "FunctionDeclaration":
                  path.node.specifiers.push(babel.exportSpecifier(babel.identifier(savedDeclaration.id.name),
                    babel.identifier(savedDeclaration.id.name)));
                  break;
                case "VariableDeclaration":
                  var lsd = savedDeclaration;
                  for (var v of lsd.declarations) {
                    /* There are only two cases here: VariableDeclator (which is horrible), and Identifier (cleaner). */
                    /* TODO: currently just casting the .id to an Identifier, even though it's
                      a PatternKind. 
                  	
                      Change to deal with other possible PatternKinds.
                    */
                    switch (v.id.type) {
                      case "Identifier":
                        var idAsIdentifierLocal = babel.identifier(v.id.name);
                        var idAsIdentifierExport = babel.identifier(v.id.name);
                        path.node.specifiers.push(babel.exportSpecifier(idAsIdentifierLocal, idAsIdentifierExport));
                        break;
                      case "ObjectPattern":
                        var idAsObjectPattern = v.id;
                        idAsObjectPattern.properties.map((v) => {
                          /* v has to have type Identifier as per destructured assignment specification */
                          var propertyAsExportIdentifier = v.key;
                          path.node.specifiers.push(babel.exportSpecifier(propertyAsExportIdentifier, propertyAsExportIdentifier));
                        })
                        break;
                      default:
                        console.error(`Unexpected case of VariableDeclarator: ${v.id.type}`);
                        process.exit(1);

                    }

                  }
                  break;
                /* TODO: more cases */
              }
              exportStmts["named"].push(path.node);
              // Replace it with the declaration.
              path.replaceWith(savedDeclaration);
            } else {
              exportStmts["named"].push(path.node);
              path.remove();
            }
            path.skip();
          }
        }
      }
    }]
  });
  return output.ast;
}

// TODO: stubbify, not stubify
function stubFile(filename, safeEvalMode = false, testingMode = false, zipFiles = false,analysis_dir) {
  if (require('./retentionPolicy').retain(filename)) return;
  // save the old file 
  let funcCount = 0;


  // this might get removed later, but is useful right now for debugging
  fs.copyFileSync(filename, filename + ".original");

  var code = fs.readFileSync(filename, 'utf-8');

  // check if the file is long enough to bother stubbifying
  if ((code.match(/\n/g) || []).length < MIN_FILE_STUB_LENGTH) {
    return;
  }
  var origCodeFileName = filename + ".BIGG";
  // var origCodeFileSize = fs.readFileSync()
  var origCodeFileSize = fs.statSync(filename).size
  var ast;
  var esmMode;
  try {
    ast = parser.parse(code, { sourceType: "unambiguous", plugins: ["classProperties", "typescript", "jsx"] }).program;
    esmMode = ast.sourceType == "module";
  } catch (e) {
    if (require('./importBindings').hasFlow(code)) {
      console.error('RETAINED_FLOW ' + filename);
      return;
    }
    console.error("Yikes... parsing error in " + filename + ":  " + e);
    return;
  }

  var importStmts = [];
  var exportStmts = { "default": [], "named": [] };
  var needsCommonJSWrapper = false;
  if (!esmMode) {
    traverse({ type: "File", program: ast }, {
      Program(p) {
        needsCommonJSWrapper = ['module', 'exports', 'require', '__filename', '__dirname']
          .some(name => p.scope.hasOwnBinding(name));
        p.stop();
      }
    });
  }

  // JSX requires the consumer's compilation pipeline; raw eval cannot execute
  // it. Retain these files and expose the decision in the transform log.
  if (require('./importBindings').hasJSX(ast)) {
    console.error('RETAINED_JSX ' + filename);
    return;
  }
  ast = processAST(ast, importStmts, exportStmts, filename, safeEvalMode);
  var requires = "const fs_uniqID = require('fs'); const zlib_uniqID = require('zlib');";
  if (esmMode) {
    requires = "import * as fs_uniqID from 'fs'; import * as zlib_uniqID from 'zlib';";
  }

  // TODO: kinda dumb that we unzip then reread but ok for now.
  var expansionLog = "";
  if (testingMode) {
    const loadRoot = process.env.STUBBIFIER_LOAD_ROOT || path.join(process.cwd(),'loads');
    const logPath = path.join(loadRoot, analysis_dir, "file.log");
    expansionLog = `fs_uniqID.appendFileSync(${JSON.stringify(logPath)},${JSON.stringify(origCodeFileName+':'+origCodeFileSize+'\n')});`;
    expansionLog += `if(process.env.HYBRID_PAYLOAD_OUT){fs_uniqID.mkdirSync(process.env.HYBRID_PAYLOAD_OUT,{recursive:true});fs_uniqID.appendFileSync(require('path').join(process.env.HYBRID_PAYLOAD_OUT,'payload-'+process.pid+'.jsonl'),JSON.stringify({kind:'file',path:${JSON.stringify(origCodeFileName)},bytes:${origCodeFileSize}})+'\\n');}`;
  }
  var body = `
		if (!fs_uniqID.existsSync(\"${origCodeFileName}\")) {
			var gunzip = zlib_uniqID.gunzipSync;
			var inp = fs_uniqID.createReadStream(\"${origCodeFileName}.gz\");
			var out = fs_uniqID.createWriteStream(\"${origCodeFileName}\");
			inp.pipe(gunzip).pipe(out);
		}
    ${expansionLog}
		let fileContents = fs_uniqID.readFileSync(\"${origCodeFileName}\", 'utf-8'); 
		`
  
    if (!esmMode) {
    // Execute CommonJS source with the same wrapper parameters as Node.
    // A local `var module` (e.g. iconv-lite's encoding table loop) must not
    // replace the module object whose exports the loader returns.
    if (needsCommonJSWrapper) body += `
      const factory_uniqID = eval('(function(exports, require, module, __filename, __dirname) {\\n' + fileContents + '\\n})');
      factory_uniqID.call(module.exports, module.exports, require, module, __filename, __dirname);
      let result_uniqID = module.exports;`;
    else body += "\nlet result_uniqID = eval(fileContents);\nmodule.exports = result_uniqID;";
  } else {
    // Babel rewrites import references in the loader, but cannot rewrite the
    // names hidden inside the sidecar string. Bind those names explicitly.
    const importNames = importStmts.flatMap(stmt => stmt.specifiers.map(spec => spec.local.name));
    const header = '(function(' + importNames.join(',') + ') {\n';
    body += `
      const factory_uniqID = eval(${JSON.stringify(header)} + fileContents + '\\nreturn evalRetVal;})');
      let result_uniqID = factory_uniqID(${importNames.join(',')});`;
  }

  // expansionLog already records bytes in file.log. Console diagnostics would
  // become part of production bundles and violate clients' no-console checks.

  //console.log((<babel.ExportNamedDeclaration> exportStmts.named[0]).specifiers)
  // create the exports:
  // for each named export, we need to create a variable declaration of the NE.specifiers[i].local.name
  // export NE.specifiers[i].local as NE.specifiers[i].exported
  var exportVars = "";
  var evalExports = "var evalRetVal = {";
  if (esmMode) {
    for (var NE of exportStmts.named) {
      for (var spec of NE.specifiers) {
        // TODO: Why is the type wrong here?
        if (spec.type == "ExportSpecifier") {
          exportVars += "var " + spec.local.name + "_uniqID = result_uniqID[\"" + spec.local.name + "\"];"
          evalExports += spec.local.name + " : " + generate(spec.local).code + ", ";
          spec.local.name += "_uniqID";
        }
      }
    }

    if (exportStmts.default.length == 1) {
      exportVars += "export default result_uniqID[\"default\"];";
      evalExports += "default : " + generate(exportStmts.default[0].declaration).code
    }
    evalExports += "}; evalRetVal;";
  }
  var outputAST = parser.parse(requires + body + exportVars, { sourceType: "unambiguous" }).program;
  if (esmMode) {
    // add import statements to the start of the stub, and exports to the end
    outputAST = transformFromAstSync(outputAST, null, {
      ast: true,
      plugins: [
        function visitAndAddImpExps() {
          return {
            visitor: {
              Program(path) {
                path.node.body = importStmts.concat(path.node.body);
                for (var [expKey, expVal] of Object.entries(exportStmts)) {
                  if (expKey != "default") {
                    path.node.body = path.node.body.concat(expVal);
                  }
                }
                path.skip()
              }
            }
          };
        }
      ]
    }).ast

    // add the evalRetVal to the end of the old code, so if it's loaded in 
    // the exports in the stub will work as expected
    ast = transformFromAstSync(ast, null, {
      ast: true,
      plugins: [
        function visitAndAddEvalExports() {
          return {
            visitor: {
              Program(path) {
                path.node.body = path.node.body.concat(parser.parse(evalExports, { sourceType: "unambiguous" }).program.body);
                path.skip();
              }
            }
          }
        }
      ]
    }).ast
  }

  // write out stub, overwriting the original file
  // Debug: adding "help"
  fs.writeFileSync(filename, generate(outputAST).code);
  // write out old code, post whatever processing is required
  var codeBodyOutput = generate(ast).code;
  if (safeEvalMode) {
    codeBodyOutput = "var dangerousFunctions = [eval]; if( process){dangerousFunctions += [process.exec]}; dangerousFunctions += [require('child_process').execSync, require('child_process').exec];" + codeBodyOutput;
  }

  if (!esmMode) {
    codeBodyOutput += "\nmodule.exports;";
  }

  // were writing out the original code as-is.
  // fs.writeFileSync(origCodeFileName, codeBodyOutput);
  // instead write out a zipped version, to conserve space.
  if (zipFiles) {
    var gzip = zlib.createGzip();
    var out = fs.createWriteStream(origCodeFileName + '.gz');
    Readable.from(codeBodyOutput).pipe(gzip).pipe(out);
  } else {
    fs.writeFileSync(origCodeFileName, codeBodyOutput);
  }
  return funcCount
}

exports.stubFile = stubFile
