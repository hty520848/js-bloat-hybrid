const graph = require('./graph');
const dftc = require('./dftc.js');
const flowgraph = require('./flowgraph');
const tool = require('../utils/tool');

// Reviewer-2.2.1 instrumentation. A switch can only be ablated if the graph
// builder says how often it was reached, so every guard below records a count.
// Absent counters and "the arm changed nothing" are not the same observation.
function count(key, n = 1) {
    const stats = global.__MCG_ABLATION;
    if (stats) stats[key] = (stats[key] || 0) + n;
}

function get_fake_root(path) {

    return {
        fake: true,
        type: 'FuncVertex',
        func:
        {
            type: 'FunctionDeclaration',
            id:
            {
                type: 'Fake',
                name: '<entry>'
            },
            attr:
            {
                enclosingFile: path
            },
            loc:
            {
                start:
                {
                    line: 1,
                    column: 0
                },
                end:
                {
                    line: 1,
                    column: 0
                }
            },
            range: [1, 1]
        },
        attr:
        {
            pp: function () { return path.replace(/\\/g, "/") + ':<1,0>--<1,0>'; },
            node_id: 0
        }
    }
}
// extract a call graph from a flow graph by collecting all function vertices that are inversely reachable from a callee vertex
function extractCG(ast, flow_graph, main_files, dept_list) {
    let edges = new graph.Graph()
    escaping = [], unknown = [];

    let reach = dftc.reachability(flow_graph);

    /* fn is a flow graph node of type 'FuncVertex' */
    function processFuncVertex(fn) {

        let r = reach.getReachable(fn)
        let nativeCalled = false
        // fnPaths = [],
        let fnIndex, propData, fnProp



        // 非原生函数匹配
        if (fn.type != 'NativeVertex') {
            fnPaths = fn.func.attr.path.split(' ')
            fnIndex = fn.func.attr?.funParamsIndex

            propData = r.find(item => item.type === 'PropertyVertex' && item.native && tool.nativeCalls().indexOf(item.name) != -1)
            // 如果函数是有property属性，并且通过property和callee建立起关系的
            if (propData) {
                nativeCalled = true
                const n = r.find(item => item.type === 'NativeArgumentVertex')
                if (n && n.mes) {
                    fnProp = n.mes
                }
            }

            for (let i = 0; i < r.length; i++) {

                if (r[i].type === 'UnknownVertex') {
                }
                // && r[i].call.attr.reachable_file.includes(fn.func.attr.enclosingFile)
                else if (r[i].type === 'CalleeVertex') {
                    // The two guards are counted separately because they are
                    // not the same predicate: `inFiles` is entailed by file
                    // selection, while `reachable_file` is a module-graph
                    // guard. Collapsing them into one condition is what made
                    // the historical 2x2 unidentifiable.
                    const inFiles = main_files.some(item => r[i].call.attr.enclosingFile.startsWith(item))
                    if (!inFiles) { count('rejectedOutsideAnalysedFiles'); continue }
                    if (process.env.MCG_DISABLE_MODULE_FILTER !== '1' && !r[i].call.attr.reachable_file.includes(fn.func.attr.enclosingFile)) { count('rejectedByModuleScope'); continue }
                    let callPath = r[i].call.attr.path.split(' ')
                    addEdgeFlag = true
                    count('candidateCallEvents')

                    /**
                     * 
                     * 如果函数调用中有paramIndex，
                     * 如果有，表示改函数调用结果来自于参数，进一步查看函数中是否有这个函数声明的索引
                     *      如果没有，则说明这俩匹配不上，直接跳过
                     *      如果有，则需要进一步查看函数声明中的索引和函数调用中的paramIndex是否匹配
                     *          如果相等，则说明改函数与函数调用匹配
                     *          如果不相等，则说明该函数与函数调用不匹配
                     * 
                     * 如果没有，则表示改函数调用并不是来自于函数传参，判断函数中是否有函数声明的索引
                     *  如果有，则不匹配
                     *  如果没有，匹配
                     *  */

                    if (r[i].paramIndex !== undefined || fnIndex !== undefined) count('indexBearingCallEvents');
                    if (process.env.MCG_DISABLE_INDEX === '1' && (r[i].paramIndex !== undefined || fnIndex !== undefined)) { count('rejectedByIndexSwitch'); continue }
                    if (r[i].paramIndex != undefined) {
                        count('indexBranchTaken');
                        if (fnIndex == undefined) {
                            continue
                        } else {
                            if (fnIndex == r[i].paramIndex) {
                                if (r[i].call.attr.enclosingFunction === undefined) {
                                    if (r[i].call.type === 'CallExpression')
                                        edges.addEdge(get_fake_root(r[i].call.attr.enclosingFile), fn);
                                    // edges.addEdge(fake_root, fn);
                                } else {
                                    edges.addEdge(r[i].call.attr.enclosingFunction.attr.func_vertex, fn);
                                    r[i].visited = true
                                }

                            } else {
                                continue
                            }
                        }
                    } else {
                        count('nameBranchTaken');
                        if (fnIndex != undefined) {
                            if (tool.nativeCalls().indexOf(callPath[callPath.length - 1]) != -1 && fnProp && fnProp === r[i].mes) {
                                edges.addEdge(nativeCalleeVertex(r[i]), fn);
                            }
                            continue
                        } else {

                            if (nativeCalled) {
                                if (r[i].mes && fnProp === r[i].mes) {
                                    edges.addEdge(nativeCalleeVertex(r[i]), fn);
                                    continue
                                }

                            } else {
                                if (r[i].call.attr.enclosingFunction === undefined) {
                                    if (r[i].call.type === 'CallExpression')
                                        edges.addEdge(get_fake_root(r[i].call.attr.enclosingFile), fn);
                                    // edges.addEdge(fake_root, fn);
                                } else {
                                    if (!r[i].mes) {
                                        edges.addEdge(r[i].call.attr.enclosingFunction.attr.func_vertex, fn);
                                        r[i].visited = true
                                    }
                                }
                            }

                        }
                    }


                }
            }
        }
        // 原生函数匹配 
        else {
            for (let i = 0; i < r.length; i++) {
                if (r[i].type === 'UnknownVertex')
                    escaping[escaping.length] = fn;
                else if (r[i].type === 'CalleeVertex') {
                    fn['loc'] = r[i].call.loc
                    fn['attr'] = r[i].call.attr
                    if (r[i].call.attr.enclosingFunction === undefined) {
                        if (r[i].call.type === 'CallExpression')
                            edges.addEdge(get_fake_root(r[i].call.attr.enclosingFile), fn);
                        // edges.addEdge(fake_root, fn);
                    } else {
                        edges.addEdge(r[i].call.attr.enclosingFunction.attr.func_vertex, fn);
                        r[i].visited = true
                    }


                    // edges.addEdge(r[i], fn);
                }
            }
        }


    }


    // 原生函数内部执行的函数调用
    function nativeCalleeVertex(nd) {

        let resultVertex = {
            type: 'NativeCalleeVertex',
            call: nd,
            attr: {
                pp: function () {
                    return `Callee(nativeCall)<${nd.call.attr.enclosingFile}@${nd.call.range[0]}:${nd.call.range[1]}>`;
                }
            },
            loc: nd.call.loc,
            name: tool.getNativeName(nd.call.attr.path),
            visited: false
        };

        return resultVertex
    }

    flow_graph.iterNodes(function (nd) {
        if (nd.type === 'FuncVertex') {
            // 处理调用链的访问，如果该函数有在调用链的路径上被声明，
            // 则从调用链上直接取值，并且跳过对原生的函数节点处理
            // if(main_files.includes(nd.func.attr.enclosingFile) ){
            processFuncVertex(nd);
            // }

        }
    });

    // console.log(flowgraph);
    // if (addNativeEdgeFlag) {
    flowgraph.getNativeVertices().forEach(processFuncVertex);
    // }


    let unknown_r = reach.getReachable(flowgraph.unknownVertex());
    unknown_r.forEach(function (nd) {
        if (nd.type === 'CalleeVertex')
            unknown[unknown.length] = nd;
    });

    return {
        edges: edges,
        escaping: escaping,
        unknown: unknown,
        fg: flow_graph
    };
}

exports.extractCG = extractCG;

