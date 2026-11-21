#!/usr/bin/env python3
"""Build the provisioned npm cache that client suites install their fixtures from.

One client workload (PowerBI-visuals-tools) creates a visual package and runs
`npm install` inside it as part of its own test suite. This image has no route to
a registry, and an online `npm install` does not fail fast: it retries until the
per-client budget expires, which is indistinguishable from a broken client. The
fix is a cache, not a patched test.

The cache is copied from a run that completed, so its bytes are already the ones
this image resolved once. Every entry key carries the registry it was fetched
from, and npm only reuses an entry when the configured registry produces the same
key, so the namespace is read back out of the cache instead of being remembered
by hand. PROVISION.json records where the cache came from; `Context.seed_npm_cache`
then copies the directory into each run and switches npm to offline mode.

Usage:
  python3 scripts/build_offline_npm_cache.py --source runs/<id>/npm-cache [--force]
"""
import argparse, collections, json, re, shutil, subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[1]
KEY = re.compile(r'"key":"pacote:(?:range-manifest|manifest):([a-z]+://[^/]+)/')


def registry_of(cache):
    """The registry namespace the cache entries were fetched under.

    Read from the index rather than passed in: a cache populated against one
    registry is unusable against another, so the value has to be a property of
    the bytes, not a note about them.
    """
    seen = collections.Counter()
    for path in (cache / "_cacache/index-v5").rglob("*"):
        if not path.is_file():
            continue
        for match in KEY.finditer(path.read_text(errors="replace")):
            seen[match.group(1)] += 1
    if not seen:
        raise SystemExit("no pacote keys in %s; not an npm cache" % cache)
    return seen.most_common(1)[0][0], dict(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="a completed run's npm-cache directory")
    ap.add_argument("--force", action="store_true", help="replace an existing provisioned cache")
    a = ap.parse_args()
    source = Path(a.source) if Path(a.source).is_absolute() else R / a.source
    harness = json.loads((R / "config/machine.local.json").read_text())["harnessRoot"]
    dest = Path(harness) / "environment/client-cache" / "npm-cache"
    if not (source / "_cacache").is_dir():
        raise SystemExit("%s has no _cacache; not an npm cache" % source)
    registry, namespaces = registry_of(source)
    if dest.exists() and not a.force:
        raise SystemExit("%s already provisioned; pass --force to replace" % dest)
    if dest.exists():
        shutil.rmtree(str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "--reflink=auto", "-a", str(source), str(dest)], check=True)
    entries = sum(1 for p in (dest / "_cacache/index-v5").rglob("*") if p.is_file())
    try:
        shown = str(source.relative_to(R))
    except ValueError:
        shown = str(source)
    provision = {"registry": registry,
                 "registryNamespaces": namespaces,
                 "source": shown,
                 "indexEntries": entries,
                 "reason": "client suites that create a fixture project and run npm install inside it "
                           "(PowerBI-visuals-tools runs `pbiviz new`, which installs its template "
                           "dependencies) need the packages to be reachable; this image has no route to a "
                           "registry and an online install retries until the client timeout instead of "
                           "failing fast"}
    (dest / "PROVISION.json").write_text(json.dumps(provision, indent=2) + "\n", encoding="utf-8")
    print("provisioned", dest)
    print("  registry", registry)
    print("  entries", entries)


if __name__ == "__main__":
    main()
