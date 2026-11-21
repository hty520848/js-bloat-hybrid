
const parser = require('@babel/parser');
const babel = require('@babel/core');
const fs = require('fs');
const path = require('path')
const readlines = require('n-readlines');
const traverse = require('@babel/traverse').default
const { trimHashbangPrep, ts2js } = require('../utils/tool')
const { errorLog } = require('../utils/log');

/** gnerate AST from files */
function astFromFiles(files) {
  const ast = {
    type: 'ProgramCollection',
    programs: new Map(),
    attr: {}
  }

  for (let file of files) {
    // if(file.indexOf('test')!=-1)continue;
    try {
      let src = fs.readFileSync(file, 'utf-8');
      // console.log();
      ast.programs.set(file, buildProgram(file, src))
      // ast.programs.push(buildProgram(file, src));

    } catch (error) {
      errorLog(error, 'file:' + file + ' load error for:')
    }

  }
try {
  for (let [fileName, fileAst] of ast.programs.entries()) {
    init(fileName, fileAst);
  }
} catch (error) {
  console.log(error);
}
  
  // nodePath2nodeMap(ast)
  return ast;
}


/* Set up `attr` field that can be used to attach attributes to
 * nodes, and fill in `enclosingFunction` and `enclosingFile`
 * attributes. */
function init(fname, root) {
  let enclosingFunction = null, enclosingFile = null;

  // global collections containing all functions and all call sites
  root['attr'] = {}
  root.attr.functions = new Map()
  root.attr.children = []
  root.attr.calls = [];
  root.merged = false
  visitWithPath(root, function (nd, doVisit, parent, childProp) {
    if (nd.type && !nd.attr)
      nd['attr'] = {};

    if (enclosingFunction)
      nd.attr.enclosingFunction = enclosingFunction;
    if (enclosingFile) {
      nd.attr.enclosingFile = enclosingFile;
    }
    nd.attr.parent = parent
    let path = ''
    if (nd.type === 'Program') {
      path = 'global'
      enclosingFile = fname;

    } else {
      // 收集文件依赖
      /**
       * import {a} from './a'
       * import a from './a'
       * import * as a from './a'
       * 
       */

      if (nd.type === 'ImportDeclaration') {
        if (nd.source.value.indexOf('./') != -1 || nd.source.value.indexOf('../') != -1) {
          root.attr.children.push(nd.source.value)
        }

      }
      else if (nd.type === 'CallExpression') {
 
          if ((nd.callee.type === 'Identifier' && nd.callee.name === 'require') ||
          nd.callee.type === 'MemberExpression' &&
          nd.callee.object.type === 'Identifier' && nd.callee.object.name === 'require' &&
          nd.callee.property.type === 'Identifier' && nd.callee.property.name === 'resolve'
        ) {
          // if ((nd.arguments[0].type === 'Literal' && nd.arguments[0].value.indexOf('./') != -1)
          //   || (nd.arguments[0].type === 'Literal' && nd.arguments[0].value.indexOf('../') != -1)) {
          root.attr.children.push(nd.arguments[0].value || nd.arguments[0].name)
          // }

        }
       
     
      }
      if (nd.type === 'Property' || nd.type === 'MethodDefinition') {
        path = parent.attr.path + (nd.key && nd.key.name ? ' ' + nd.key.name : ' ' + nd.key.value)
      } else {
        // 处理对象属性的赋值是具名函数的情况:obj:{a:function aa(){}}
        if (nd.type === 'FunctionExpression' && (childProp === 'value' || childProp === 'init')) {
          path = parent.attr.path
        } else {
          try {
            path = parent.attr.path + (nd.id && nd.id.name ? ' ' + nd.id.name : '')
          } catch (error) {
            console.log(error);
          }



        }


      }

      if (nd.type === 'CallExpression' || nd.type === 'NewExpression') {
        switch (nd.callee.type) {
          // 
          case 'Identifier':
            // if(nd.parent.type==='')
            path = nd.callee.name
            break;
          case 'MemberExpression':
            path = handleRecusiveFindPath(nd.callee, nd.callee.property.name)
            break;
          // 匿名函数调用
          case 'ParenthesizedExpression':
          case 'FunctionExpression':
            nd.attr.callee = nd.callee.expression.id
            path = parent.attr.path
            break
        }
        nd.attr.parent = parent
      }
    }
    nd.attr['path'] = path
    if (nd.type === 'FunctionExpression' && parent !== undefined && parent.type === 'Property') {
      if (!parent.computed) {
        if (parent.key.type === 'Identifier') {
          nd.id = parent.key;
        }
        else if (parent.key.type === 'Literal') {
          // create a new `Identifier` AST node and set it to `FunctionExpression`'s id
          nd.id = {
            type: 'Identifier',
            name: parent.key.value,
            range: parent.key.range,
            loc: parent.key.loc
          };
        }
        else {
          console.log("WARNING: unexpected key type of 'Property'.");
        }
      }
      else
        console.log("WARNING: Computed property for method definition, not yet supported.");
    }

    if (nd.type === 'ClassDeclaration') {
      // root.attr.global.set(nd.id.name, new Map())
      if (nd.superClass) {
        let index = nd.attr.path.lastIndexOf(nd.id.name)
        nd.attr['path'] = nd.attr.path.slice(0, index) + nd.superClass.name + ' ' + nd.attr.path.slice(index)

      }
    }

    if (nd.type === 'MethodDefinition') {
      if (!nd.computed) {
        if (nd.key.type === 'Identifier' || nd.key.type === 'PrivateName') {
          nd.value.id = nd.key;
          if (nd.static) {
            nd.value['static'] = true
          }

        }
        else if (nd.key.type === 'Literal') {
          // this case is covered by test case: tests/unexpected/stringiterator.truth
          console.log("WARNING: invalid syntax, method name is of type Literal instead of Identifier.");
        }
        else {
          console.log("WARNING: unexpected key type of 'MethodDefinition'.");
        }
      }
      else {
        console.log("WARNING: Computed property for method definition, not yet supported.");
      }
    }

    if (nd.type === 'FunctionDeclaration' ||
      nd.type === 'FunctionExpression' ||
      nd.type === 'ArrowFunctionExpression') {

      if (nd.id && nd.id.name) {
        if (nd['static']) { // 类中静态方法不加入子级类中
          root.attr.functions.set('static ' + nd.id.name, nd);
        } else {
          root.attr.functions.set(nd.id.name, nd);
        }

      } else {
        root.attr.functions.set(path.split(' ').pop(), nd);
      }
      // The index of a function passed as an argument is its position in the
      // callee's argument list, and position 0 is index 0, not "no index".
      // Testing the raw value for truthiness silently dropped every first
      // argument, i.e. the most common callback position (`arr.map(cb)`), which
      // made the index tier of the hybrid matcher look inert.
      if (nd.keyName === 'arguments' && childProp !== undefined && childProp !== null && !isNaN(childProp)) {
        nd.attr.funParamsIndex = childProp
      }
      nd.attr.parent = parent;
      // nd.attr.originCode = print(nd)
      nd.attr.childProp = childProp;
      let old_enclosingFunction = enclosingFunction;
      enclosingFunction = nd;

      doVisit(nd.id, nd, 'id');
      doVisit(nd.params, nd, 'params');
      doVisit(nd.body, nd, 'body');
      enclosingFunction = old_enclosingFunction;
      return false;
    }

    if (nd.type === 'CallExpression' || nd.type === 'NewExpression') {

      if (nd.type === 'NewExpression') {
        if (nd.callee.type === 'Identifier') {

          [...root.attr.functions.values()].forEach(func => {
            let paths = func.attr.path.split(' ')
            let pathIndex = paths.indexOf(nd.callee.name)
            if (pathIndex != -1 && !func.static) {
              paths.splice(pathIndex + 1, 0, parent?.id?.name || '')
              func.attr.path = paths.join(' ')
            }

          })
        }


      }
      root.attr.calls.push(nd);
    }
  });
}
/**
 * 
 * @param {node} node  CallExpression  callee
 * @returns 
 */

function handleRecusiveFindPath(node, path) {
  if (!node) return path
  if (node.object) {
    if (node.object.type === 'CallExpression') {
      return handleRecusiveFindPath(node.object.callee, node.property.name)
    } else if (node.object.type === 'MemberExpression') {
      // console.log(node.object);
      if (node.object.object.type === 'CallExpression') {
        return handleRecusiveFindPath(node.object, node.object.property.name) + ' ' + path + node.object.property.name
      } else {
        return node.object.object.name + ' ' + (node.object.property.name ? node.object.property.name + ' ' : '') + path
      }

    }
    else {
      return node.object.name + ' ' + path
    }
  }
  // return path
  // if(node.type==='Identifier'){
  //   console.log(node);
  // }
  // if (node.object && node.object.type !== 'Identifier') {
  //   return handleRecusiveFindPath(node.object.callee, path)
  // } else {
  //   if (node.object) {
  //     return node.object.name + ' ' + path
  //   } else {
  //     return (node.name || '') + path
  //   }

  // }
  return node.name || ''


}
/**
 * 把收集到的函数声明路径转化为哈希链表 global a c -> global:map(a:map(c:node))
 * @param {*} ast 
 */
function nodePath2nodeMap(ast) {
  let nodeMap = new Map()
  let nodePath = ast.attr.nodePath
  nodePath.forEach(node => {
    if (nodeMap.has(node.file)) {
      nodeMap.set(node.file, nodeMap.get(node.file).concat(node))
    } else {
      nodeMap.set(node.file, [].concat(node))
    }
  })
  for (const [key, value] of nodeMap.entries()) {
    let fileMap = new Map(), pathMap = new Map()
    for (let i = 1; i < value.length; i++) {
      let curPath = value[i].path.split(' ').filter(item => item !== undefined && item != '')
      if (curPath[0] != 'global') curPath.unshift('global')
      for (let j = 0; j < curPath.length; j++) {
        // 跳过全局节点
        if (curPath[j] === 'global') continue
        if (j === 1) {
          if (fileMap.has(curPath[j])) {
          } else {
            fileMap.set(curPath[j], new Map())

          }
          pathMap = fileMap.get(curPath[j])
        }
        else if (j != curPath.length - 1) {
          if (!pathMap.has(curPath[j])) {
            pathMap.set(curPath[j], new Map())
          }
          pathMap = pathMap.get(curPath[j])
        }
        else {
          pathMap.set(curPath[j], value[i])
        }

      }

    }
    nodeMap.set(key, fileMap)
    ast.attr.modeMap = nodeMap
    delete ast.attr.nodePath
  }
}

function mergeAst(ast, dir, entry) {
  let main = path.join(dir, entry)
  let visited_trees = new Set()
  let forest = []
  let s_ast = {}
  s_ast.programs = []
  s_ast.functions = []
  s_ast.calls = []
  s_ast.name = main
  if (ast.programs.has(main)) {
    let sub_ast = ast.programs.get(main)

    s_ast.name = main
    visited_trees.add(main)
    if (sub_ast.attr.children.length > 0) {
      find_modules_ast(s_ast, sub_ast, sub_ast.attr.children, main)
    }
    sub_ast.attr.calls.forEach(item => {
      item.attr['reachable_file'] = sub_ast.attr.reachable_file ?? []
      item.attr.reachable_file.push(main)
    })
    s_ast.programs.push(sub_ast)
    s_ast.calls = s_ast.calls.concat(sub_ast.attr.calls)
    s_ast.functions = s_ast.functions.concat([...sub_ast.attr.functions.values()])


    forest.push(s_ast)

  }

  function find_modules_ast(root, parent_ast, children, f_path, level = 0) {
    try {
      children.forEach(item => {
        let p_entry
        if (!item) {
          item = 'index.js'
        }
        let fname
        if (item.includes('./')||item.includes('../') ) {
          if(!item.includes('.json')){
            fname = path.join(path.dirname(f_path), item)
            find_modules_file_ast(root, parent_ast, fname, level)
          }
          
        } else {
          if (level > 0) return
          if(!item.includes('.json')){
            // Match Node's owner-relative lookup rather than assuming hoisting.
            try {
              p_entry = require.resolve(item, { paths: [path.dirname(f_path)] });
            } catch (error) {
              throw new Error('Cannot resolve import ' + item + ' from ' + f_path + ': ' + error.message);
            }
            if (ast.programs.has(p_entry)) {
              if (!parent_ast.attr.reachable_file) {
                parent_ast.attr.reachable_file = []
              }
              parent_ast.attr.reachable_file.push(p_entry)
  
              if (!visited_trees.has(p_entry)) {
                let s_ast = ast.programs.get(p_entry)
                visited_trees.add(p_entry)
                if (s_ast.attr.children.length > 0) {
                  find_modules_ast(root, s_ast, s_ast.attr.children, p_entry, level + 1)
                  parent_ast.attr.reachable_file = parent_ast.attr.reachable_file.concat(s_ast.attr.reachable_file ?? [])
                }
                s_ast.attr.calls.forEach(item => {
                  item.attr['reachable_file'] = s_ast.attr.reachable_file ?? []
                  item.attr.reachable_file.push(p_entry)
                })
                root.programs.push(s_ast)
                root.calls = root.calls.concat(s_ast.attr.calls)
                root.functions = root.functions.concat([...s_ast.attr.functions.values()])
              }
  
            }
          } 
    
        }


      })
    } catch (error) {
      console.log(error);
    }


  }

  function find_modules_file_ast(root, parent_ast, fname, level) {
    if (!fname.includes('.js')) {
      fname = fname + '.js'
    }
    if (!fs.existsSync(fname)) {
      fname = fname.split('.js')[0]
    }
    if(fs.existsSync(fname)){
      if (fs.lstatSync(fname).isDirectory()) {
        try {
          const files = fs.readdirSync(fname);
          if (files.includes('index.js')) {
            fname = path.join(fname, 'index.js')
          } else {
            fname = path.join(fname, fname.match(/node_modules\\([^\\]+)/)[1] + '.js')
          }
        } catch (err) {
          console.error(err);
        }
      }
  
      if (ast.programs.has(fname)) {
        if (!parent_ast.attr.reachable_file) {
          parent_ast.attr.reachable_file = []
        }
        parent_ast.attr.reachable_file.push(fname)
        if (!visited_trees.has(fname)) {
          visited_trees.add(fname)
          let s_ast = ast.programs.get(fname)
          if (s_ast.attr.children.length > 0) {
            find_modules_ast(root, s_ast, s_ast.attr.children, fname, level)
            parent_ast.attr.reachable_file = parent_ast.attr.reachable_file.concat(s_ast.attr.reachable_file ?? [])
          }
          s_ast.attr.calls.forEach(item => {
            item.attr['reachable_file'] = s_ast.attr.reachable_file ?? []
            item.attr.reachable_file.push(fname)
          })
          root.programs.push(s_ast)
          root.calls = root.calls.concat(s_ast.attr.calls)
          root.functions = root.functions.concat([...s_ast.attr.functions.values()])
  
        }
  
      }
  
    }
   
  }


  return forest
}

/* AST visitor */
function visitWithPath(root, visitor) {
  function doVisit(nd, parent, childProp) {
    if (!nd || typeof nd !== 'object')
      return;

    if (Array.isArray(nd) || childProp === 'body' ||
      childProp === 'declarations' ||
      childProp === 'properties' ||
      childProp === 'decorators' ||
      childProp === 'elements' ||
      childProp === 'specifiers' ||
      childProp === 'expressions' ||
      childProp === 'quasis' ||
      childProp === 'cases' ||
      childProp === 'consequent' ||
      childProp === 'params') {
      nd['attr'] = {}
      nd.attr['path'] = parent.attr.path
    }

    if (childProp === 'arguments') {
      nd['attr'] = {}
      // if(parent.callee.type==='Identifier' || parent.callee.type ==='FunctionExpression' || parent.callee.type ==='MemberExpression'){
      //   nd.attr['path'] =parent.callee.attr.path
      // }else{
      //   nd.attr['path'] = parent.callee.expression.attr.path
      // }

      if (parent.callee.type === 'ParenthesizedExpression') {
        nd.attr['path'] = parent.callee.expression.attr.path
      } else {
        nd.attr['path'] = parent.callee.attr.path
      }

    }

    if (nd.type && nd.type !== 'ProgramCollection') {
      let res = visitor(nd, doVisit, parent, childProp);
      if (res === false)
        return;
    }

    for (let p in nd) {
      if (!nd.hasOwnProperty(p) || p.match(/^(range|loc|attr|comments|raw|path|type|start|end|sourceType|interpreter)$/))
        continue;
      doVisit(nd[p], nd, p);
    }
  }

  doVisit(root);
}
function visit(root, visitor) {
  function doVisit(nd, parent, childProp) {
    if (!nd || typeof nd !== 'object')
      return;

    if (nd.type) {
      let res = visitor(nd, doVisit, parent, childProp);
      if (res === false)
        return;
    }

    for (let p in nd) {
      // skip over magic properties
      if (!nd.hasOwnProperty(p) || p.match(/^(range|loc|attr|comments|raw|path|type|start|end|sourceType|interpreter)$/))
        continue;
      doVisit(nd[p], nd, p);
    }
  }

  doVisit(root);
}

/* AST visitor with state */
function visitWithState(root, visitor) {
  const state = {
    'withinDeclarator': false,
    'withinParams': false
  };

  function doVisit(nd, parent, childProp) {
    if (!nd || typeof nd !== 'object')
      return;

    if (nd.type) {
      let res = visitor(nd, doVisit, state, parent, childProp);
      if (res === false)
        return;
    }

    for (let p in nd) {
      // skip over magic properties
      if (!nd.hasOwnProperty(p) || p.match(/^(range|loc|attr|comments|raw|path|type|start|end|sourceType|interpreter)$/))
        continue;
      doVisit(nd[p], nd, p);
    }
  }

  doVisit(root);

}

/* Simple version of UNIX basename. */
function basename(filename) {
  if (!filename)
    return "<???>";
  let idx = filename.lastIndexOf('/');
  if (idx === -1)
    idx = filename.lastIndexOf('\\');
  return filename.substring(idx + 1);
}

function isAnon(funcName) {
  return funcName === "anon";
}

// func must be function node in ast
function funcname(func) {
  if (func === undefined)
    console.log('WARNING: func undefined in astutil/funcname.');
  else if (func.id === null)
    return "anon";
  else if (!func.id.name) {
    return func.id?.id?.name || 'anon'
  }
  else

    return func.id.name;
}

// encFunc can be undefined
function encFuncName(encFunc) {
  if (encFunc === undefined) {
    return "global";
  } else if (encFunc.id === null)
    return "anon";
  // privateMethod
  else if (!encFunc.id.name)
    return encFunc.id.id ? encFunc.id.id.name : 'anon'
  return encFunc.id.name
}

/* Pretty-print position. */
function ppPos(nd) {

  return nd.attr.enclosingFile + "@" + nd.loc.start.line + ":" + nd.range[0] + "-" + nd.range[1];
  // return nd.attr.enclosingFile + ":" + nd.loc.start.line + ":" + Number(Number(nd.loc.start.column) + 1);
}
function ppPos2(nd, bdir, v8, flag) {
  let basePath, newCol
  if (flag) {
    if (flag == 'nativeFunc') {
      basePath = nd.attr.enclosingFile.replace(bdir, "").replace(/\\/g, "/") + '(Native)';
      newCol = colNum2V8(Number(nd.loc.start.line),
        Number(nd.loc.start.column),
        nd.attr.enclosingFile, 'not-function');
    } else if (flag == 'nativeCallee') {
      basePath = nd.call.call.attr.enclosingFile.replace(bdir, "").replace(/\\/g, "/") + '(Native)';
      if (!nd.call.call.attr.enclosingFunction) {
        return basePath + ":<1,0>--<1,0>"
      }
      newCol = colNum2V8(
        Number(nd.call.call.attr.enclosingFunction.loc.start.line),
        Number(nd.call.call.attr.enclosingFunction.loc.start.column),
        nd.call.call.attr.enclosingFile, 'function');
    }
    if (basePath.startsWith("/")) {
      basePath = basePath.substring(1);
    }
    if (flag == 'nativeFunc')
      return basePath
    else {
      return basePath + ":<" + nd.call.call.attr.enclosingFunction.loc.start.line + "," + newCol + '>--<' + nd.call.call.attr.enclosingFunction.loc.end.line + "," + nd.call.call.attr.enclosingFunction.loc.end.column + '>'
    }
  } else {
    basePath = nd.attr.enclosingFile.replace(bdir, "").replace(/\\/g, "/");
    if (nd.type === 'FunctionDeclaration' ||
      nd.type === 'FunctionExpression' ||
      nd.type === 'ArrowFunctionExpression') {
      newCol = v8 ? colNum2V8(Number(nd.loc.start.line),
        Number(nd.loc.start.column),
        nd.attr.enclosingFile,
        'function') : Number(Number(nd.loc.start.column) + 1);
    } else {
      newCol = colNum2V8(Number(nd.loc.start.line),
        Number(nd.loc.start.column),
        nd.attr.enclosingFile,
        'function')
      if (basePath.startsWith("/")) {
        basePath = basePath.substring(1);
      }

    }
    if (basePath.startsWith("/")) {
      basePath = basePath.substring(1);
    }

    return basePath + ":<" + nd.loc.start.line + "," + newCol + '>--<' + nd.loc.end.line + "," + nd.loc.end.column + '>'
    // return basePath + "<" + nd.loc.start.line + ":" + nd.loc.start.column + "," + nd.loc.end.line + ":" + nd.loc.end.column+'>';
  }



}

const positionSourceLines = new Map();
function colNum2V8(ln, col, bdir, type) {
  let endTag = {
    "function": "{",
    "not-function": "("
  }
  if (basename(bdir) === "entry") {
    return col + 1;
  }

  if (!positionSourceLines.has(bdir)) {
    const liner = new readlines(bdir);
    const lines = [];
    let next;
    while ((next = liner.next()) !== false) lines.push(next.toString('utf-8'));
    positionSourceLines.set(bdir, lines);
  }
  let newCol = col;
  const line = positionSourceLines.get(bdir)[ln - 1];
  if (line !== undefined) {
      if (!line.substring(col).includes("=>")) {
        while (line.charAt(newCol) !== endTag[type]) {
          newCol++;
          if (newCol > line.length) {
            newCol = 0;
            break;
          }
        }
      }
  }
  return type === 'function' ? newCol : (newCol + 1);

}
/* Parse a single source file and return its ast
Args:
    fname - A string, the name of the source file
      src - A string, the source code
 
Return:
    If succeeded, return an ast node of type 'Program'.
    If failed, return null.
*/
function buildProgram(fname, src) {
  // trim hashbang
  src = trimHashbangPrep(src);
  if (fname.endsWith('ts')) {
    try {

      src = ts2js(fname, src);
    } catch (error) {
      errorLog(error, `failed to transform ${fname} into javascript`)
      return null
    }
  }

  // parse javascript
  let prog;
  try {
    prog = parse(src, fname);
  }
  catch (error) {
    errorLog(error, `fialed to parse ${fname} into AST`);
    return null;
  }
  prog.attr = { filename: fname };
  return prog;
}

/* Build an AST from file name and source code
Args:
    fname - A string, the name of the source file
      src - A string, the source code
 
Return:
    If succeeded, return an ast node of type 'ProgramCollection'.
    If failed, return null.
*/
function astFromSrc(fname, src) {
  const prog = buildProgram(fname, src);
  if (prog === null)
    return null;
  const ast = {
    'type': 'ProgramCollection',
    'programs': [prog],
    'attr': {},
    'code': src
  }
  init(ast);
  return ast;
}


function preProcess(ast, fname) {


  // // 对于匿名函数其处理方案为：<filename,anonymousFun_id,loc>
  // if (nd.type === 'FunctionExpression'  && !nd.id && (parent.type === 'ParenthesizedExpression' || parent.type === 'CallExpression')) {
  //   nd.id = {
  //     name: nd.attr.enclosingFile + ' anonymousFunction_' + anonymousID++ + ':<' + nd.loc.start.line + ',' + nd.loc.start.column + '>'
  //   }
  // }
  let anonymousID = 0
  traverse(ast, {

    enter(path) {
      try {
        if (path.node.type === 'MethodDefinition' && path.node.key.type == 'PrivateName') {
          path.node.key['name'] = path.node.key.id.name
        }
        if ((path.type === 'FunctionExpression' ||
          path.type === 'ArrowFunctionExpression') && !path.node.id) {
  
          if (path.key === 'right') {
            path.node.id = {
              type: 'Identifier',
              name:  fname + '-anonymous' + anonymousID++ + '-<' + path.node.loc.start.line + ',' + path.node.loc.start.column + '>',
              range: path.node.range,
              loc: path.node.loc,
              functionType: path.type
            };
          }
          else if (path.parentKey !== 'init') { // 忽略函数赋值和对象属性的值为函数表达式的情况，因为这两类函数都是有名字的函数
            if (path.parentKey !== 'arguments') {
              path.node.id = {
                type: 'Identifier',
                name: fname + '-anonymous' + anonymousID++ + '-<' + path.node.loc.start.line + ',' + path.node.loc.start.column + '>',
                range: path.node.range,
                loc: path.node.loc,
                functionType: path.type
              };
            } else {
              path.node.id = {
                type: 'Identifier',
                name: fname + '-anonymous' + anonymousID++ + '-argumentKey' + path.key + '-<' + path.node.loc.start.line + ',' + path.node.loc.start.column + '>',
                range: path.node.range,
                loc: path.node.loc,
                functionType: path.type
              };
            }
          }
        }
        path.node.keyName = path.listKey
      } catch (error) {
        console.log(error);
      }
     
    },
  });
}
/* 将文件转成ast
*/
function parse(src, fname) {
  const ast = parser.parse(src, {
    allowImportExportEverywhere: true,
    allowAwaitOutsideFunction: true,
    allowReturnOutsideFunction: true,
    allowSuperOutsideMethod: true,
    allowUndeclaredExports: true,
    errorRecovery: true,
    attachComment: false,
    createParenthesizedExpressions: true,
    sourceType: "unambiguous",
    ranges: true,
    jsx: true,
    plugins: [
      "estree",
      "flow",
      "jsx",
      "decoratorAutoAccessors",
      "doExpressions",
      "exportDefaultFrom",
      "functionBind",
      "importAssertions",
      "regexUnicodeSets",
      ["decorators", { decoratorsBeforeExport: false }]
    ]
  })
  preProcess(ast, fname)
  return ast.program;
}



// cf is used by getFunctions
const cf = funcObj => {
  return funcObj.file + ':' +
    funcObj.name + ':' +
    funcObj.range[0] + ':' +
    funcObj.range[1] + ':' +
    (funcObj.charRange[1] - funcObj.charRange[0]);
};

/* Return a list of objects storing function info in root
 
Args:
    root - An ast node of type 'ProgramCollection',
         - the output of astFromSrc function,
         - thus, root.programs.length is equal to 1
    src  - A string, the corresponding source code of `root`
 
Returns:
    A list of objects, each with the following properties
    {
        'name': a valid function name | 'anon' | 'global',
        'file': a valid file name,
        'range': a list of two integers,
        'code': code of the function | null (for global context),
        'encFuncName': a valid function name | 'anon' | 'global' | null (for global context),
        'cf': a string representing the colon format id
    }
*/
function getFunctions(root, src) {
  const funcs = [];
  const funcNodes = root.attr.functions;

  for (let i = 0; i < funcNodes.length; ++i) {
    const fn = funcNodes[i];

    // funcName
    let funcName = funcname(fn);

    // startLine && endLine
    let startLine = fn.loc.start['line'];
    let endLine = fn.loc.end['line'];

    // name, file and range are for colon format id
    // code and encFuncName are added for trackFunctions
    funcs.push({
      'name': funcName,
      'file': fn.attr.enclosingFile,
      'range': [startLine, endLine],
      'charRange': fn.range,
      'code': src.substring(fn.range[0], fn.range[1]),
      'encFuncName': encFuncName(fn.attr.enclosingFunction)
    });
  }

  // Add 'cf' property
  funcs.forEach(funcObj => {
    funcObj['cf'] = cf(funcObj);
  });

  // Create a fake function object for global context
  let prog = root.programs[0];
  funcs.push({
    'name': 'global',
    'file': prog.attr.filename,
    'range': [prog.loc.start['line'], prog.loc.end['line']],
    'charRange': null,
    'code': null,
    'encFuncName': null,
    'cf': prog.attr.filename + ':global'
  });

  return funcs;
}

/* Check if nd is an assignment to module.exports
 
Args:
    nd - an ast node
 
Returns:
    true if nd represents an assignment to module.exports, false otherwise
 
Relevant docs:
 
    interface MemberExpression {
        type: 'MemberExpression';
        computed: boolean;
        object: Expression;
        property: Expression;
    }
*/
function isModuleExports(nd) {
  if (nd.type !== 'AssignmentExpression')
    return false;

  let left = nd.left;

  if (left.type !== 'MemberExpression')
    return false;

  let object = left.object;
  let property = left.property;

  if (object.type !== 'Identifier' || property.type !== 'Identifier')
    return false;

  return object.name === 'module' && property.name === 'exports';
}

/*
Args:
       nd - an ast node
  fn_name - a function name to compare to
 
Returns: true if nd represents a call to fn_name, false otherwise
 
Relevant docs:
 
    interface CallExpression {
        type: 'CallExpression';
        callee: Expression;
        arguments: ArgumentListElement[];
    }
*/
function isCallTo(nd, fn_name) {
  if (nd.type !== 'CallExpression')
    return false;

  let callee = nd.callee;

  if (callee.type !== 'Identifier')
    return false;

  return callee.name === fn_name
}


/*
Args:
    nd - An ast node
 
Returns:
    A boolean, true if nd is a function declaration
    or function expression or arrow function expression,
    false otherwise.
*/
function isFunction(nd) {
  return nd.type === 'FunctionDeclaration' ||
    nd.type === 'FunctionExpression' ||
    nd.type === 'ArrowFunctionExpression'
}

module.exports.visit = visit;
module.exports.visitWithState = visitWithState;
module.exports.init = init;
module.exports.mergeAst = mergeAst;
module.exports.ppPos = ppPos;
module.exports.ppPos2 = ppPos2;
module.exports.funcname = funcname;
module.exports.encFuncName = encFuncName;
module.exports.astFromFiles = astFromFiles;
module.exports.astFromSrc = astFromSrc;
module.exports.parse = parse;
module.exports.getFunctions = getFunctions;
module.exports.isAnon = isAnon;
module.exports.isModuleExports = isModuleExports;
module.exports.isCallTo = isCallTo;
module.exports.isFunction = isFunction;
module.exports.cf = cf;
