#!/usr/bin/env python3
"""Recompute the recorded input manifest hash of an already-registered client.

Repairing a client tree in place (re-pointing a harness hook at this repository,
restoring a dependency that a previous materialisation step cleared) changes the
bytes the admission gate hashes. Without this step the gate silently reports
"Client input manifest mismatch" and the client looks unqualified even though
nothing about its test workload changed. Only the hash is rewritten; the rest of
the entry is left untouched so provenance cannot drift silently.
"""
import argparse, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from experiments.common import snapshot          # noqa: E402
from experiments.prepare import sha_bytes        # noqa: E402

MACHINE = R / "config/machine.local.json"
CANDIDATES = R / "datasets/manifests/clients.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    machine = json.loads(MACHINE.read_text())
    entries = machine.get("clients", {}).get(a.library, [])
    entry = next((e for e in entries if e["directory"] == a.client), None)
    if entry is None:
        raise SystemExit("client not registered: %s/%s" % (a.library, a.client))

    root = Path(entry["root"])
    if not root.is_dir():
        raise SystemExit("client root missing: " + str(root))
    frozen = snapshot(root, include_all=True)
    digest = sha_bytes(frozen)
    before = entry.get("inputManifestSha256")
    print("root   :", root)
    print("before :", before)
    print("after  :", digest)
    print("entries:", len(frozen))
    if a.dry_run or digest == before:
        return
    entry["inputManifestSha256"] = digest

    manifest = json.loads(CANDIDATES.read_text())
    for item in manifest.get("libraries", {}).get(a.library, []):
        if item.get("directory") == a.client:
            item["inputManifestSha256"] = digest
            break
    MACHINE.write_text(json.dumps(machine, indent=2) + "\n")
    CANDIDATES.write_text(json.dumps(manifest, indent=2) + "\n")
    print("rewritten")


if __name__ == "__main__":
    main()
