#!/usr/bin/env python3
"""Build the client roster: paper slot -> the client actually measured.

The paper's Table 4.5 fixes a roster, but a roster entry can only be measured
here if its whole test suite completes on this image. That forces three
outcomes per slot, and the difference between them has to be visible in the
artefact rather than buried in a run log:

  paper-replica   the paper's own client, measured as published
  substitute      a different client stands in for a slot that cannot run here
  frozen-cohort   a client measured in addition to the published roster

Evidence is harvested from every qualification run in `runs/`. The verdict that
is reported is the latest one measured on the bytes configured right now, so a
repaired tree is not hidden by an older failed attempt and a client that passed
once is not reported as passing while it fails today. When the same bytes carry
both an older success and a newer failure the row keeps the success as
`priorQualifiedRun`: identical inputs with different verdicts means the
environment moved, not the client.
"""
import argparse, glob, json
from pathlib import Path

R = Path(__file__).resolve().parents[1]

# Paper Table 4.5, as published. Names on the left are the table's spelling;
# the value is the directory this repository uses for the same package.
PAPER = {
    "prop-types": [("react-date", "react-dates"), ("react-loadable", "react-loadable"),
                   ("react-redux", "react-redux"), ("redux-form", "redux-form"),
                   ("react-dropzone", "react-dropzone")],
    "redux": [("Choices", "Choices"), ("griddle", "Griddle"),
              ("reactBeautifulDnd", "react-beautiful-dnd"), ("found", "found"),
              ("redux-ignore", "redux-ignore")],
    "send": [("connectGzipStatic", "connect-gzip-static"), ("gulp-connect", "gulp-connect"),
             ("express", "express"), ("harp", "harp"), ("serve-static", "serve-static")],
}
# Libraries outside Table 4.5 were never given a published roster here; their
# clients are recorded as a frozen cohort instead of pretending to a slot.

# A paper slot that cannot be measured here keeps its row (so the loss is
# visible) and carries the diagnosis that was established for it. Without this
# the table would show the slot as merely "not-measured" and a reader could not
# tell an environment limit from an unfixed defect.
SLOT_NOTES = {
    ("prop-types", "react-dates"):
        "archive defect, not a replication defect: DateRangePickerInputController_spec.jsx:780 "
        "asserts a moment() built from the wall clock against null, so the suite fails on any "
        "date after 2026-03-11; it fails identically on the pre-repair work tree and under both "
        "fixedDateMs values that were tried, and the archived evidence run recorded 1050 passing "
        "when the clock was still in range",
    ("send", "harp"):
        "environment limit: `harp init` materialises its project from a GitHub template via "
        "download-github-repo over HTTP, which this offline image cannot reach; the suite never "
        "starts, so there is nothing to measure",
}


# A client that qualified once on the same bytes and fails now is evidence
# about the image, not about the client. The generic control-failed reason says
# nothing about why, so the diagnosis that was established for each one travels
# with the row instead of staying buried in a run log.
DRIFT_NOTES = {
    ("serve-static", "node-soap"):
        "校园网关现在对 WSDL 里的服务地址 http://www.example.com/v1 返回「Authentication is required」"
        "页面，而不是用例断言的跳转 HTML，于是请求路径报错、raw 为 undefined；单客户端重跑仍复现 "
        "13 passing / 1 failing，输入字节未变",
    ("css-loader", "PowerBI-visuals-tools"):
        "`pbiviz new` 会在生成的 visual 目录里自己跑 npm install，而本镜像出站 HTTPS 到任何 registry "
        "都被阻断，安装反复重试直到 1200s 客户端预算耗尽（exit 124）；同一命令对上缓存树约 4s 完成",
    ("morgan", "json-server"):
        "原始套件要连一个外部主机的 TCP 端口，连接失败；与 node-soap、npm 安装同属本次网络变化",
}


def best_evidence():
    best = {}
    for path in sorted(glob.glob(str(R / "runs" / "*" / "client-qualification.json")),
                       key=lambda p: Path(p).parent.name):
        run_id = Path(path).parent.name
        try:
            rows = json.loads(Path(path).read_text())
        except Exception:
            continue
        for row in rows:
            key = (row.get("library"), row.get("client"))
            cand = {"eligible": bool(row.get("qualified")), "run": run_id,
                    "status": row.get("status"),
                    "own": row.get("ownFunctionsExercised"),
                    "production": row.get("productionFunctionsExercised"),
                    "manifest": row.get("inputManifestSha256"),
                    "reason": row.get("reason")}
            best.setdefault(key, []).append(cand)
    return best


def pick(candidates, current):
    """Report the latest verdict on the bytes configured right now.

    A repaired tree has a new manifest hash; an older success on the previous
    bytes must not be credited to it, so observations that predate the current
    tree are dropped. Among the survivors the *latest* run decides the status:
    preferring an older success would let a client that passed once and fails
    now be reported as eligible, which is exactly the misreading this roster
    exists to prevent.

    The earlier success is still worth keeping. When the bytes are identical
    and only the verdict changed, the difference is the environment rather than
    the client, and that distinction belongs in the table instead of in a log.
    """
    current_hits = [c for c in candidates if c.get("manifest") == current]
    if not current_hits:
        return {"status": "stale-evidence"}, False
    current_hits.sort(key=lambda c: c["run"])
    latest = current_hits[-1]
    prior = [c for c in current_hits if c["eligible"] and c["run"] != latest["run"]]
    if prior and not latest["eligible"]:
        latest = dict(latest, priorQualifiedRun=prior[-1]["run"],
                      priorQualifiedOwn=prior[-1]["own"])
    return latest, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(R / "datasets/manifests/client-roster.json"))
    a = ap.parse_args()

    machine = json.loads((R / "config/machine.local.json").read_text())
    evidence = best_evidence()
    configured = machine.get("clients", {})

    rows, summary = [], {}
    for lib in sorted(configured):
        paper = PAPER.get(lib, [])
        paper_dirs = [d for _, d in paper]
        for entry in configured[lib]:
            name = entry["directory"]
            prov = entry.get("provenance") or {}
            if name in paper_dirs:
                slot = next(p for p, d in paper if d == name)
                # A paper slot whose directory differs from the table spelling is
                # still the same package; record the spelling that was measured.
                kind = "paper-replica"
            elif prov.get("origin") == "substitute":
                # A substitute stands in for something published that cannot be
                # measured here. Membership in a paper library is not enough:
                # a client added on top of a full roster (downshift, lasso,
                # node-restify, gitbook) fills no slot and must not be reported
                # as if it did, or the table would claim substitutions that were
                # never made.
                slot, kind = None, "substitute"
            else:
                slot, kind = None, "frozen-cohort"
            current = entry.get("inputManifestSha256")
            candidates = evidence.get((lib, name), [])
            ev = pick(candidates, current)[0] if candidates else {}
            rows.append({"library": lib, "paperSlot": slot, "directory": name,
                         "role": kind,
                         "origin": prov.get("origin"),
                         "packageVersion": entry.get("packageVersion"),
                         "declaredRange": prov.get("declaredRange"),
                         "targetBindings": entry.get("targetBindings"),
                         "testCommand": entry.get("command"),
                         "eligible": bool(ev.get("eligible")),
                         "status": ev.get("status", "no-evidence"),
                         "reason": ev.get("reason"),
                         "slotNote": SLOT_NOTES.get((lib, name), "") if not ev.get("eligible") else "",
                         "priorQualifiedRun": ev.get("priorQualifiedRun"),
                         "priorQualifiedOwn": ev.get("priorQualifiedOwn"),
                         "driftNote": DRIFT_NOTES.get((lib, name), "") if ev.get("priorQualifiedRun") else "",
                         "ownFunctionsExercised": ev.get("own"),
                         "productionFunctionsExercised": ev.get("production"),
                         "evidenceRun": ev.get("run"),
                         "inputManifestSha256": current,
                         "note": prov.get("note", "")})
        slot_state = {}
        for slot, directory in paper:
            hit = next((r for r in rows if r["library"] == lib and r["directory"] == directory), None)
            slot_state[slot] = "measured" if hit and hit["eligible"] else "not-measured"
        summary[lib] = {"paperSlots": len(paper),
                        "paperMeasured": sum(1 for v in slot_state.values() if v == "measured"),
                        "eligibleConfigured": sum(1 for r in rows if r["library"] == lib and r["eligible"]),
                        "configured": sum(1 for r in rows if r["library"] == lib),
                        "slots": slot_state}

    # Role and origin are counted over the whole roster, not just the paper
    # libraries: a reader checking "was anything substituted?" should not have to
    # add up ten libraries by hand.
    roles, origins = {}, {}
    for r in rows:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
        key = r["origin"] or "unmarked"
        origins[key] = origins.get(key, 0) + 1

    doc = {"schemaVersion": 1,
           "paperRosterSource": "论文表 4.5（3 库 × 5 客户端）",
           "rule": "以每 (库,客户端) 在当前输入字节上的最新判定为准；同字节上的更早合格记为 priorQualifiedRun（说明差异来自环境而非客户端）",
           "roles": roles, "origins": origins,
           "summary": summary, "clients": rows}
    Path(a.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for lib in sorted(summary):
        s = summary[lib]
        print("%-13s paper %d/%d  eligible %d/%d" % (lib, s["paperMeasured"], s["paperSlots"],
                                                     s["eligibleConfigured"], s["configured"]))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
