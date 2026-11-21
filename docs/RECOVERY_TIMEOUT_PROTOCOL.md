# Recovery measurement and client deadline repair

The repair entry is `scripts/resume_ordered_recovery.py`. It preserves the
completed RQ1 matrix and original failed run. It executes RQ2, then RQ3, then
RQ4, stopping and recording an error if a required control fails.

## Controlled client deadline

The frozen style-loader 1.3.0 workload passes on the original distribution but
the SDCG recovery-instrumented distribution reproducibly exceeds Jest's default
5-second asynchronous-test deadline. The late callback then interferes with
subsequent DOM snapshots. In a separate diagnostic, both original and SDCG pass
the complete unchanged suite when the deadline is 20 seconds. That diagnostic
is not substituted for the original failure or treated as a runtime benchmark.

The formal repair applies a 20-second deadline to the original, independently
instrumented truth, SSCG, SDCG and Hybrid workloads. The adapter runs the original
pretest/lint recipe, followed by the complete coverage test recipe with the
explicit Jest timeout. It verifies the pinned package and scripts; it does not
edit package sources, assertions, snapshots or test discovery. Other clients
retain their frozen commands.

Qualification requires identical complete test/snapshot signatures, and the
fresh independently observed function-ID set must equal the prior set. All
three transformed controls must pass the same command before the certificate
is marked qualified. RQ3 accepts only this completed certificate and applies
the same command to both sides of each pair. RQ3 measures uninstrumented
reduction artifacts and does not infer overhead from the repair diagnostics.

Passing at 20 seconds does not establish compatibility with the original
5-second deadline or imply negligible execution overhead.

## Physical recovery byte accounting

Some legacy file-level events embed the original source-file size, which can
differ from the serialized `.BIGG` implementation actually expanded. The reader
therefore retains `rawPayloadEvents`, verifies each operand lies inside the
certified cold artifact, and records its physical byte size and SHA-256 in the
derived `payloadEvents`. `reportedBytes` retains the producer's original value.
Deduplication remains by `(kind, path)`, and bytes are converted using 1024 bytes
per KiB. Missing operands are errors, never zero-byte observations.

Completed RQ2 blocks are reused only after verifying source, transformer,
analysis-function code, original signatures, client identity/bindings, saved
logs, and byte-identical payload inventories between the cold artifact and
measured client copy. Reconciliation creates new derived rows; old events and
results are not overwritten. The affected CSS-loader block is newly qualified
with matched controls. Its earlier failures and successful observations remain
available in the original run.

## Reproducible continuation

From the server package root, using unused run IDs:

```sh
python3 scripts/resume_ordered_recovery.py \
  --batch 20261105-006 \
  --runtime-admission runs/qual-complete-20261105-005/runtime-admission.json \
  --completed-rq1 runs/ordered-rq1-20261105-005 \
  --source-rq2 runs/ordered-rq2-20261105-005
```

The current continuation uses batch `20261105-006`; do not rerun that command
with the same ID. Records are under `provenance/ordered-<batch>/controller.json`
and `runs/ordered-rq2-<batch>/`. The matched-client certificate is
`repair/client-deadline-certificate.json`. Stage-specific effective protocols
are saved separately from the initialization protocol snapshot. Manuscript
tables are never filled automatically.

## Reporting a remaining failure

If a corrected matched control still fails, retain its complete log and mark
that method/client cell unqualified, with a diagnosed or unresolved cause.
Report coverage and failed counts, use an explicitly shared valid cohort for
method aggregates, and state which generalizations remain unsupported. Do not
drop an unfavorable valid result, update expected snapshots, count a failure
as zero recovery, or describe a partial matrix as complete. The original
deadline failures and the final common protocol should remain inspectable in
the replication package even if the revised control passes.
