# Measurement contract

Function identities bind source SHA-256, relative path, AST kind and Babel UTF-16 positions. The cohort contains declared CommonJS `.js` production sources and resolved production closure. Development/test drivers are excluded; short/untransformed functions stay in the denominator. Other module formats and total deployed disk size are outside this measurement.

Candidate bloat is positive: TP=predicted bloat/unobserved; FP=predicted bloat/executed; FN=retained/unobserved; TN=retained/executed. Accuracy=(TP+TN)/N, precision=TP/(TP+FP), recall=TP/(TP+FN); undefined ratios are null. Independent entry instrumentation uses the same source and complete unchanged test signatures. Unobserved is workload-relative, not semantic deadness.

Static edge truth is separate. Resolve archived locations against actual source; do not equate top-level and file/function markers without checking. Unjudged edges remain unjudged. Current sensitivity reports two callback conventions, without inter-rater reliability claims.

OS and TS sum bytes in the same library JavaScript inventory. Red = 100(OS − TS) / OS. The fresh 10×5 runner measures OSize from the original bound application before testing. It estimates ESize by adding the distinct payload bytes actually loaded during the suite to the initial transformed application’s JavaScript footprint. The runner stores both operands and computes |ESize − OSize| per client in KiB. It averages over the five clients when all five have valid measurements. Loaded code size (LCS) is recorded separately.

Slowdown = 100(ET − T) / T. Negative values are retained. The fresh runner records timings for each selected qualified workload and reports the repetition count and measurement dispersion.

Preparation includes analysis, mapping and target selection where applicable, and code transformation. The driver measures ten fresh repetitions per method and library by default. Copying, inventories and test validation are outside the measured phase totals.

The archived static adjudication extends positive labels separately by arm. Its within-arm extended recall is not comparable across arms. The manuscript reports precision and convention sensitivity, without comparing those recall values. A shared source-aligned positive reference set is required before a cross-arm extended-recall claim.
