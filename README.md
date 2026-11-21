# JavaScript debloating replication package

Companion artifact for *A Hybrid Method for Detecting and Eliminating Bloated Code in Server-Side JavaScript Applications*.

## Inputs and environment

The frozen cohort contains ten npm libraries and five Stubbifier workloads for each library. The library versions, client revisions and individual suite commands are listed in `datasets/manifests/`. The frozen source trees, dependency trees, Linux runtimes and static benchmark inputs are distributed as separate archives. `manifest/inputs.json` gives the byte size and SHA-256 of each archive.

Use Linux x86-64 with Python 3.6 or later, Git, GNU tar, GNU coreutils and `unzip`. The Linux validation used Python 3.6.9. The shared software configuration for RQ1–RQ4 is recorded in `provenance/frozen-toolchain.json`. Keep the checkout on a filesystem that supports symbolic links and executable modes. Allow at least 35 GB of free disk space for import and validation runs. Full runs create additional private copies of the workloads.

## Download and import the inputs

Download the data and runtime assets from this repository's GitHub Release into
`.release-inputs/`. Keep all numbered parts of the main archive in the same directory as the other
assets. A full archive with the same SHA-256 can be supplied in place of its parts.
Download the [static edge labels](https://www.inf.u-szeged.hu/~ferenc/papers/StaticJSCallGraphs/StaticJSCallGraphs.zip)
from the benchmark authors and save the file as `StaticJSCallGraphs.zip` in the same directory.
The release omits nested Git metadata and historical server-specific configuration
records. Client revisions and test commands are recorded in the dataset manifests.

Download CodeQL CLI 2.3.4 for Linux x64 from the [official release](https://github.com/github/codeql-cli-binaries/releases/tag/v2.3.4)
after reviewing its [terms](https://github.com/github/codeql-cli-binaries/blob/v2.3.4/LICENSE.md).
Save the official asset `codeql-linux64.zip` in `.release-inputs/`. The staging script
verifies its checksum and places it under the filename used by the import manifest.

```sh
python3 scripts/stage_release_inputs.py --assets-dir .release-inputs \
  --codeql .release-inputs/codeql-linux64.zip
python3 scripts/import_inputs.py --manifest manifest/inputs.json
python3 scripts/audit_package.py --output provenance/package-audit.json
```

The import verifies the archived inputs, extracts them under `artifacts/`, and
generates `config/machine.frozen.json`. For a second independent import, pass another
`--name` and `--config`. Run `python3 scripts/audit_package.py --source-only` to check
a source checkout before obtaining the archives.

## Run a small validation

```sh
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id static-one --static-benchmark --program crypto-aes.js
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id static-debug --static-multifile --library debug
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id hybrid-smoke --smoke --library body-parser --client express --methods hybrid
```

The Hybrid check runs the complete suites of one library and one client, then records one RQ3 pair and one fresh RQ4 repetition. Check `runs/<run-id>/status.json` and the per-RQ outputs. Validation evidence is in `provenance/minimal-run.json`.

## Run the experiments

```sh
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id static-programs --static-benchmark
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id static-libraries --static-multifile
python3 scripts/reproduce.py --config config/machine.frozen.json \
  --run-id paper-workloads --components
```

The first command runs MCG on the archived SunSpider collection against its reference edge labels. The second analyzes six archived multi-file subjects and writes the full and module-filter-disabled call graphs. The third does fresh analysis and compares SSCG, SDCG and Hybrid on the frozen 10×5 roster. `--components` adds the static-only and dynamic-only branches of RQ1. Use `--library`, `--client`, or `--methods` to select a smaller run. The standard RQ3 protocol uses two warmups and ten measured pairs. RQ4 uses ten fresh analysis-and-transformation repetitions per method and library. Preparation records the original controls and the workloads that qualify for measurements.

| Output under `runs/<run-id>/` | Contents |
| --- | --- |
| `rq1/sizes.json`, `rq1/clients.json` | Initial library sizes and downstream classification |
| `rq2/loading.json`, `rq2/loading-cells.json` | Per-workload measurements and group summaries |
| `rq3/runtime.json` | Whole-suite timing pairs and summary |
| `rq4/preparation-cost.json` | Fresh analysis, rewrite and total preparation timing |

## Manuscript results

`results/paper/index.json` lists the eight tables and the accuracy figure used in the manuscript, along with the 300 timing observations underlying the RQ4 table. Each item includes a SHA-256 hash and a source reference. New run outputs are written to `runs/`.

The input manifests pin the library releases listed in Table 1. See `THIRD_PARTY_NOTICES.md` for source and licensing information.
