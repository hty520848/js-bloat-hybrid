"""Map the independent function manifest onto Istanbul's ``fnMap``.

The manifest (``*-functions.json``) is produced by a Babel traversal that lists
every function node with two locations: ``loc`` (whole node) and ``bodyLoc``
(the ``{``-to-``}`` range). Istanbul's ``fnMap`` records the *body* range, so the
body anchor is the only legitimate key; a whole-node fallback is kept because it
costs nothing and documents the convention on the record.

Absence from ``fnMap`` is classified, never guessed:

``mapped``
    the body anchor resolves to an ``fnMap`` slot;
``ignored``
    the source carries an ``istanbul ignore`` hint, proved by re-instrumenting
    with the hint neutralised (see ``src/baselines/instrument_coverage.js``);
    the instrumenter therefore has no measurement for this function and SDCG
    cannot know whether it executed;
``missing``
    neither of the above. That is a real source-location loss and must fail
    qualification rather than be absorbed as a zero.

The three counts are asserted to add up to the measured universe, so a silent
reclassification is impossible.
"""
import json
from pathlib import Path


def loc_key(loc):
    return '%d:%d:%d:%d' % (loc['start']['line'], loc['start']['column'],
                            loc['end']['line'], loc['end']['column'])


def load_ignored(path):
    """Absolute file path -> {body anchor -> {key, hint}}."""
    if not path or not Path(path).is_file():
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return {name: {row['key']: row for row in rows} for name, rows in data.items()}


def classify(functions, coverage_entry, ignored=None):
    """Return the mapped / ignored / missing split for one file."""
    ignored = ignored or {}
    index = {}
    if coverage_entry:
        for slot, value in coverage_entry.get('fnMap', {}).items():
            index[loc_key(value['loc'])] = slot
    mapped, ignored_rows, missing = {}, [], []
    for function in functions:
        body = loc_key(function['bodyLoc'])
        if body in index:
            mapped[function['id']] = index[body]
            continue
        whole = loc_key(function['loc'])
        if whole in index:
            mapped[function['id']] = index[whole]
            continue
        if body in ignored:
            ignored_rows.append({'id': function['id'], 'anchor': body,
                                 'hint': ignored[body].get('hint'),
                                 'reason': 'istanbul-ignore-hint'})
            continue
        missing.append({'id': function['id'], 'anchor': body})
    return {'mapped': mapped, 'ignored': ignored_rows, 'missing': missing}


def absolute(root, name):
    import os
    return os.path.realpath(os.path.join(str(root), name))


def map_manifest(functions, coverage, root, ignored=None):
    """Group the manifest by file and classify every function.

    ``coverage`` and ``ignored`` are keyed by absolute real path, which is what
    the instrumenter writes; the manifest stores paths relative to ``root``.
    """
    ignored = ignored or {}
    by_file = {}
    for function in functions:
        by_file.setdefault(function['file'], []).append(function)
    totals = {'measured': 0, 'mapped': 0, 'ignored': 0, 'missing': 0}
    mapped, ignored_rows, missing, unrealised = {}, [], [], []
    for name in sorted(by_file):
        key = absolute(root, name)
        entry = coverage.get(key) or coverage.get(name)
        if entry is None:
            unrealised.append({'file': name, 'functions': len(by_file[name]),
                               'reason': 'file absent from the coverage report: instrumenter skipped the whole file'})
        result = classify(by_file[name], entry, ignored.get(key) or ignored.get(name) or {})
        totals['measured'] += len(by_file[name])
        mapped.update(result['mapped'])
        ignored_rows.extend(result['ignored'])
        missing.extend(result['missing'])
    totals['mapped'] = len(mapped)
    totals['ignored'] = len(ignored_rows)
    totals['missing'] = len(missing)
    assert totals['mapped'] + totals['ignored'] + totals['missing'] == totals['measured'], \
        'Function classification must partition the measured universe'
    return {'totals': totals, 'mapped': mapped, 'ignored': ignored_rows,
            'missing': missing, 'filesAbsentFromCoverage': unrealised}
