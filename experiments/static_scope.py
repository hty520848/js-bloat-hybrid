"""Scope partition used by the reviewer-2.2.1 static ablation.

Kept separate from the script so the partition can be tested without a server:
the point of the ablation is that *caller* scope and *callee* scope are two
different questions, and mixing them up would silently turn a real effect into
a zero.

  * The module-scope switch filters on the **call site file**: calls made from
    outside the production scope are dropped.
  * Whether the **callee** is production code decides whether an edge is an
    out-of-scope target, which is a different (and also useful) count.

Edge endpoints are printed relative to the analysis directory, so a caller of
``index.js`` and a caller of ``node_modules/basic-auth/index.js`` are both
library-relative-looking strings. Resolving them against the analysis root is
therefore mandatory; without it every call site looks out of scope and every
arm looks identical, which is exactly the failure mode this supplement exists
to avoid.
"""
import os

def node_file(node):
    for mark in (':<', ':'):
        if mark in node:
            return node.split(mark)[0]
    return node


def normalize(path):
    if not path:
        return None
    text = path.replace('\\', '/')
    return text[2:] if text.startswith('./') else text


def library_relative(path, lib, root=''):
    """Library-relative path when the file is inside the library, else None."""
    text = normalize(path)
    if not text:
        return None
    base = normalize(str(root)).rstrip('/') if root else ''
    if base and text.startswith('/'):
        if text == base:
            return ''
        if text.startswith(base + '/'):
            return text[len(base) + 1:]
        return None
    if base:
        # normpath is used only to collapse '..'; its separators are host
        # specific, so the result is normalised back to '/' before comparing.
        resolved = os.path.normpath(base + '/' + text).replace('\\', '/')
        if resolved == base:
            return ''
        if resolved.startswith(base + '/'):
            return resolved[len(base) + 1:]
        return None            # ../ escaped the library root
    token = '/' + lib + '/'
    probe = '/' + text
    if token in probe:
        return probe.split(token, 1)[1]
    if text.startswith(lib + '/'):
        return text[len(lib) + 1:]
    return None


def _tail(path, depth=3):
    parts = [p for p in (normalize(path) or 'unknown').split('/') if p]
    return '/'.join(parts[-depth:]) if parts else 'unknown'


def classify(edges, scope_files, lib, root=''):
    in_scope_caller = in_scope_callee = 0
    caller_out, callee_out = {}, {}
    callees = set()
    for edge in edges:
        if ' -> ' not in edge:
            continue
        caller, callee = edge.split(' -> ', 1)
        caller_path, callee_path = node_file(caller), node_file(callee)
        crel = library_relative(caller_path, lib, root)
        trel = library_relative(callee_path, lib, root)
        if crel is not None and crel in scope_files:
            in_scope_caller += 1
        else:
            key = _tail(caller_path)
            caller_out[key] = caller_out.get(key, 0) + 1
        if trel is not None and trel in scope_files:
            in_scope_callee += 1
            callees.add(trel)
        else:
            key = _tail(callee_path)
            callee_out[key] = callee_out.get(key, 0) + 1
    top = lambda d: dict(sorted(d.items(), key=lambda kv: -kv[1])[:10])
    return {'totalEdges': len(edges), 'inScopeCallerEdges': in_scope_caller,
            'outOfScopeCallerEdges': len(edges) - in_scope_caller,
            'inScopeCalleeEdges': in_scope_callee, 'outOfScopeCalleeEdges': len(edges) - in_scope_callee,
            'inScopeCallees': len(callees),
            'outOfScopeCallerPrefixes': top(caller_out), 'outOfScopeCalleePrefixes': top(callee_out)}
