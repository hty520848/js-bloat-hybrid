#!/usr/bin/env python3
"""Pre-build the dtslint TypeScript install cache so `dtslint types` can run offline.

`@definitelytyped/utils` installs typescript on demand into
`$HOME/.dts/typescript-installs/<version>` and skips the install only when that
directory already exists. The 161 server has no outbound network, so a client
whose `npm test` includes `dtslint types` fails for environmental reasons even
though its own code is fine. This script builds those directories on a machine
with registry access, so the cache can be shipped once and seeded per run.

The generated package.json mirrors dtslint's own installer byte for byte, so the
cached tree is indistinguishable from one dtslint would have produced itself.
"""
import argparse, json, subprocess, sys
from pathlib import Path

SHIPPED = ["3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9"]


def package_json(version):
    return {
        "description": "Installs typescript@%s" % version,
        "repository": "N/A",
        "license": "MIT",
        "dependencies": {"typescript": version},
    }


def build(root, versions, npm="npm"):
    installs = root / ".dts" / "typescript-installs"
    for v in versions:
        d = installs / v
        if (d / "node_modules" / "typescript" / "package.json").is_file():
            print("skip %s (present)" % v, flush=True)
            continue
        d.mkdir(parents=True, exist_ok=True)
        (d / "package.json").write_text(json.dumps(package_json(v), indent=2) + "\n", encoding="utf-8")
        print("install %s" % v, flush=True)
        subprocess.run([npm, "install", "--ignore-scripts", "--no-shrinkwrap",
                        "--no-package-lock", "--no-bin-links", "--no-audit", "--no-fund"],
                       cwd=str(d), check=True, shell=(sys.platform == "win32"))
        actual = json.loads((d / "node_modules" / "typescript" / "package.json").read_text(encoding="utf-8"))["version"]
        print("  -> typescript %s" % actual, flush=True)
    return installs


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--versions", nargs="*", default=SHIPPED)
    a = p.parse_args()
    out = build(Path(a.root), a.versions)
    print("cache at", out)
