
let flowgraph = require('./flowgraph');
let nativeFlows = require('./harness').nativeFlows;

function addNativeFlowEdges(flow_graph) {
    for (let native in nativeFlows) {
        if (!nativeFlows.hasOwnProperty(native))
            continue;
        let target = nativeFlows[native];
        flow_graph.addEdge(
            flowgraph.nativeVertex(native,flow_graph),
            flowgraph.propVertex({
                type: 'Identifier',
                name: 'Native(' + target + ')',
                native: true
            })
        );
    }
    return flow_graph;
}

module.exports.addNativeFlowEdges = addNativeFlowEdges;

