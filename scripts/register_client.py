"""Register a freshly built client tree as an admissable candidate.

Adding a client touches two frozen files (the machine configuration and the
candidate manifest). Doing that by hand is how a tree ends up bound to the wrong
package or listed without the manifest hash the admission gate re-checks. This
script writes both from the tree itself, so the recorded hash is the hash of the
bytes that will run.

Provenance is written into both files: whether the client is a replica of the
published table's roster or a substitute for a candidate that cannot run here.
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
    ap.add_argument("--root", required=True)
    ap.add_argument("--version", required=True, help="client package version")
    ap.add_argument("--commit", required=True)
    ap.add_argument("--test-command", required=True)
    ap.add_argument("--declared-field", default="dependencies")
    ap.add_argument("--declared-range", default="")
    ap.add_argument("--installed-target-version", required=True)
    ap.add_argument("--bindings", nargs="+", required=True)
    ap.add_argument("--command", required=True, help="JSON array, e.g. '[\"npm\",\"test\"]'")
    ap.add_argument("--origin", required=True, choices=["paper-replica", "frozen-cohort", "substitute"])
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    if not root.is_dir():
        raise SystemExit("client root is not a directory: " + str(root))
    lib_version = None
    for rel in a.bindings:
        pkg = root / rel / "package.json"
        if not pkg.is_file():
            raise SystemExit("binding has no package.json (wrong path or cleared placeholder): " + rel)
        lib_version = json.loads(pkg.read_text())["version"]
    if lib_version != a.installed_target_version:
        raise SystemExit("binding version %s != declared target %s" % (lib_version, a.installed_target_version))

    frozen = snapshot(root, include_all=True)
    digest = sha_bytes(frozen)

    machine = json.loads(MACHINE.read_text())
    manifest = json.loads(CANDIDATES.read_text())
    if a.library not in machine.get("clients", {}):
        raise SystemExit("library not configured for clients: " + a.library)

    cfg = {
        "directory": a.client,
        "root": str(root),
        "command": json.loads(a.command),
        "targetBindings": a.bindings,
        "inputManifestSha256": digest,
        "inputManifestAlgorithm": "all-files-and-internal-links-v1",
        "packageVersion": a.version,
        "gitCommit": a.commit,
        "library": a.library,
        "provenance": {
            "origin": a.origin,
            "note": a.note,
            "declaredRange": a.declared_range,
            "filesHashed": len(frozen),
        },
    }
    rows = [x for x in machine["clients"][a.library] if x["directory"] != a.client]
    rows.append(cfg)
    machine["clients"][a.library] = rows

    entry = {
        "directory": a.client,
        "packageName": a.client,
        "packageVersion": a.version,
        "gitCommit": a.commit,
        "testCommand": a.test_command,
        "declaredDependency": {"field": a.declared_field, "range": a.declared_range},
        "installedTargetVersion": a.installed_target_version,
        "origin": a.origin,
        "note": a.note,
    }
    libs = [x for x in manifest["libraries"][a.library] if x["directory"] != a.client]
    libs.append(entry)
    manifest["libraries"][a.library] = libs
    manifest["totalClients"] = sum(len(v) for v in manifest["libraries"].values())

    MACHINE.write_text(json.dumps(machine, indent=2) + "\n")
    CANDIDATES.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"library": a.library, "client": a.client, "files": len(frozen),
                      "manifestSha256": digest, "targetVersion": lib_version,
                      "candidates": manifest["totalClients"]}, indent=1))


if __name__ == "__main__":
    main()
