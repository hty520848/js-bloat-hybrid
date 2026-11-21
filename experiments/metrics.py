"""Unique recovered-payload measurements shared by RQ2 and its supplements.

Historical paper MECS operands ESize/OSize remain unauthenticated. The legacy
MECS/meanMECS schema names in saved reconstruction records denote payload KiB
and are retained for compatibility; they do not authenticate historical MECS.
Zero is an observed lack of expansion, distinct from an absent measurement.
See docs/METRICS.md for the reporting boundary.
"""

import os
from pathlib import Path

EXPANDED_SIZE_BOUNDARY = (
    'Application JavaScript before the suite, including installed dependencies; '
    'the expanded size includes only payloads loaded during that suite.'
)


def application_js_bytes(root):
    """Count physical JavaScript files once, before the workload writes outputs."""
    total = 0
    for directory, folders, files in os.walk(str(root), followlinks=False):
        folders[:] = [name for name in folders if name not in {'.git', 'coverage', '.nyc_output'}]
        for name in files:
            path = Path(directory) / name
            if path.suffix in {'.js', '.cjs', '.mjs'} and not path.is_symlink() and path.is_file():
                total += path.stat().st_size
    return total


def expanded_size(original_bytes, transformed_bytes, recovered_bytes):
    """Single-workload operand of the paper's mean absolute size difference."""
    expanded_bytes = transformed_bytes + recovered_bytes
    difference = abs(expanded_bytes - original_bytes)
    return {
        'OSizeBytes': original_bytes,
        'initialApplicationBytes': transformed_bytes,
        'ESizeBytes': expanded_bytes,
        'absoluteDifferenceBytes': difference,
        'MECS': difference / 1024.0,
        'applicationSizeBoundary': EXPANDED_SIZE_BOUNDARY,
    }


def aggregate_expanded(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['library'], row['arm']), []).append(row)
    cells = []
    for (lib, arm), members in sorted(groups.items()):
        values = [row['MECS'] for row in members if row['valid']]
        complete = len(values) == len(members)
        cells.append({
            'library': lib,
            'arm': arm,
            'plannedWorkloads': len(members),
            'measuredWorkloads': len(values),
            'meanMECSKiB': _mean(values) if complete else None,
            'complete': complete,
        })
    return cells

MECS_DEFINITION = (
    'Legacy reconstruction MECS field: unique recovered payload bytes / 1024 '
    '(KiB), averaged over eligible workloads. Historical paper MECS operands '
    'ESize/OSize remain unauthenticated; these payload values are not equivalent '
    'to historical MECS. Zero is observed no expansion, not missing data.'
)



def mecs_kb(loaded_bytes):
    """Legacy API for single-workload payload KiB; absent is not zero."""
    if loaded_bytes is None:
        return None
    return round(loaded_bytes / 1024.0, 4)


def loaded_bytes(payload_events):
    """Unique recovery bytes expanded at run time.

    Payload events are de-duplicated by (kind, path) so that repeated loads of
    the same sidecar do not inflate the figure; this mirrors the producer
    contract in ``rq2/run.py`` and ``scripts/qualify_stubbifier_rq2.py``.
    """
    unique = {}
    for event in payload_events:
        unique[str(event.get('kind')) + ':' + str(event.get('path'))] = event
    return sum(int(event.get('bytes') or 0) for event in unique.values())


def _mean(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / float(len(values))


def aggregate(rows, group_keys=('library', 'arm'), workload_key='workload'):
    """Aggregate per-workload rows into one MECS cell per (library, arm).

    Rows must already carry ``eligible`` (whether the workload may enter a
    comparison) and ``MECS``. Ineligible workloads are reported but excluded
    from the mean, exactly as the primary RQ2 table excludes them.
    """
    cells = {}
    for row in rows:
        key = tuple(row.get(k) for k in group_keys)
        cells.setdefault(key, []).append(row)
    out = []
    for key, members in sorted(cells.items(), key=lambda kv: str(kv[0])):
        eligible = [m for m in members if m.get('eligible', True)]
        values = [m.get('MECS') for m in eligible if m.get('MECS') is not None]
        record = dict(zip(group_keys, key))
        record.update({
            'workloads': len(members),
            'eligibleWorkloads': len(eligible),
            'workloadsWithMECS': len(values),
            'meanMECS': round(_mean(values), 4) if values else None,
            'minMECS': min(values) if values else None,
            'maxMECS': max(values) if values else None,
            'zeroExpansionWorkloads': len([v for v in values if v == 0]),
            'MECSSpread': round(max(values) - min(values), 4) if values else None,
            'MECSDefinition': MECS_DEFINITION,
            'metricName': 'uniqueRecoveredPayloadKiB',
            'meanRecoveredPayloadKiB': round(_mean(values), 4) if values else None,
            'historicalMECSEquivalent': False,
        })
        if workload_key:
            record[workload_key + 's'] = [
                {workload_key: m.get(workload_key), 'eligible': m.get('eligible', True),
                 'MECS': m.get('MECS'), 'status': m.get('status')}
                for m in members
            ]
        out.append(record)
    return out
