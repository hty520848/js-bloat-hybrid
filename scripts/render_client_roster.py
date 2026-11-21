#!/usr/bin/env python3
"""Render the client roster as a readable table.

`client-roster.json` is the machine record; this turns it into the document a
person checks when asking "which client stood in for the published one, and on
what evidence". Every number comes from the JSON, so the prose can never drift
from the measurement.

Usage: python scripts/render_client_roster.py [--roster ...] [--out ...]
"""
import argparse, json
from pathlib import Path

R = Path(__file__).resolve().parents[1]

STATUS = {
    "qualified": "已准入：对照臂零失败、插桩臂签名一致、命中目标自身函数",
    "target-not-exercised": "测试跑通但未触达目标库，不计入",
    "original-control-failed": "未插桩对照臂即失败，无法归因于本方法",
    "truth-or-integrity-failed": "插桩臂失败或与对照臂签名不一致",
    "stale-evidence": "现有证据描述的字节与当前配置不符",
    "no-evidence": "尚无运行证据",
}
LIB_CN = {
    "body-parser": "body-parser", "compression": "compression", "css-loader": "css-loader",
    "memfs": "memfs", "memory-fs": "memory-fs", "morgan": "morgan",
    "prop-types": "prop-types", "redux": "redux", "send": "send", "serve-static": "serve-static",
}


def cell(v):
    if v is None or v == "":
        return "—"
    return str(v).replace("|", "\\|")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default=str(R / "datasets/manifests/client-roster.json"))
    ap.add_argument("--out", default=str(R / "docs/客户端名册与正标.md"))
    a = ap.parse_args()
    doc = json.loads(Path(a.roster).read_text(encoding="utf-8"))
    rows, summary = doc["clients"], doc["summary"]
    by = lambda lib: [r for r in rows if r["library"] == lib]

    L = []
    w = L.append
    w("# 客户端名册与替代标注（正标）")
    w("")
    w("论文表 4.5 固定了一份客户端名册，但一个客户端只有在整份测试套件于本镜像上跑完，")
    w("它的测量才有意义。凡是跑不通的槽位，本表既不删除也不静默补一个同名同版本的假条目，")
    w("而是保留该槽位并标注为「未测量」，另取替代客户端并标注来源（`origin=substitute`）。")
    w("表中每个数字都可回溯到一次具体运行（见「证据 run」列）。")
    w("")
    w("口径：`qualified` 需同时满足三条——未插桩对照臂退出码为 0 且失败签名为空；")
    w("插桩臂与对照臂签名一致；插桩臂确实执行到目标库自身函数。")
    w("")

    paper = doc["summary"]
    total_slots = sum(v["paperSlots"] for v in paper.values())
    total_measured = sum(v["paperMeasured"] for v in paper.values())
    total_eligible = sum(v["eligibleConfigured"] for v in paper.values() if v["paperSlots"])
    total_conf = sum(v["configured"] for v in paper.values() if v["paperSlots"])
    roles = doc.get("roles", {})
    w("## 1. 总览")
    w("")
    w("| 指标 | 数值 |")
    w("| --- | --- |")
    w("| 论文表 4.5 槽位 | %d 个（3 库 × 5 客户端） |" % total_slots)
    w("| 槽位实测通过 | %d / %d |" % (total_measured, total_slots))
    w("| 论文库可用客户端 | %d / %d |" % (total_eligible, total_conf))
    w("| 全库客户端 | %d 个，其中 `paper-replica` %d、`substitute` %d、`frozen-cohort` %d |"
      % (len(rows), roles.get("paper-replica", 0), roles.get("substitute", 0),
         roles.get("frozen-cohort", 0)))
    w("| 十库可用客户端（准入线 ≥3） | %d / %d |"
      % (sum(v["eligibleConfigured"] for v in summary.values()),
         sum(v["configured"] for v in summary.values())))
    w("")

    w("## 2. 十个库的准入情况")
    w("")
    w("| 库 | 论文槽位 | 可用 / 配置 | 是否满足 quorum=3 |")
    w("| --- | --- | --- | --- |")
    for lib in sorted(summary):
        s = summary[lib]
        slot = "%d / %d" % (s["paperMeasured"], s["paperSlots"]) if s["paperSlots"] else "表 4.5 未给出"
        ok = "是" if s["eligibleConfigured"] >= 3 else "**否**"
        w("| %s | %s | %d / %d | %s |" % (LIB_CN.get(lib, lib), slot,
                                           s["eligibleConfigured"], s["configured"], ok))
    w("")
    gaps = [lib for lib in sorted(summary) if summary[lib]["eligibleConfigured"] < 3]
    if gaps:
        w("**闸门结论**：%s 的可用客户端数低于 quorum=3，`formalReady` 为 False，"
          "六个实验（E0–E6）不能启动。" % "、".join(
              "`%s`(%d)" % (g, summary[g]["eligibleConfigured"]) for g in gaps))
    else:
        w("**闸门结论**：十库均满足 quorum=3。")
    w("")

    w("## 3. 论文表 4.5 逐槽位对账")
    for lib in ("prop-types", "redux", "send"):
        w("")
        w("### %s" % LIB_CN.get(lib, lib))
        w("")
        w("| 论文槽位（原拼写） | 实际客户端 | 角色 | 绑定版本 | 自身函数 | 生产函数 | 准入状态 | 证据 run |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- |")
        slots = [r for r in by(lib) if r["paperSlot"]]
        order = {name: i for i, name in enumerate(summary[lib]["slots"])}
        slots.sort(key=lambda r: order.get(r["paperSlot"], 99))
        for r in slots:
            w("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                cell(r["paperSlot"]), cell(r["directory"]), cell(r["role"]),
                cell(r["packageVersion"]), cell(r["ownFunctionsExercised"]),
                cell(r["productionFunctionsExercised"]), cell(r["status"]),
                cell(r["evidenceRun"])))
        notes = [r for r in slots if r.get("slotNote")]
        if notes:
            w("")
            for r in notes:
                w("- **%s 未测量**：%s" % (r["paperSlot"], r["slotNote"]))
        extra = [r for r in by(lib) if not r["paperSlot"]]
        if extra:
            w("")
            w("该库另有 %d 个非槽位客户端（角色 `%s`）：%s。" % (
                len(extra),
                "/".join(sorted({r["role"] for r in extra})),
                "、".join("`%s`(%s)" % (r["directory"], r["status"]) for r in extra)))
    w("")

    w("## 4. 替代客户端（正标清单）")
    w("")
    subs = [r for r in rows if r["role"] == "substitute"]
    if not subs:
        w("无。")
    else:
        w("| 库 | 替代客户端 | 绑定版本 | 依赖声明范围 | 理由 | 自身函数 | 准入状态 | 证据 run |")
        w("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in subs:
            w("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                cell(r["library"]), cell(r["directory"]), cell(r["packageVersion"]),
                cell(r["declaredRange"]), cell(r["note"]),
                cell(r["ownFunctionsExercised"]), cell(r["status"]), cell(r["evidenceRun"])))
        w("")
        w("替代的两条共同理由：其一，该库在原名册里没有一个客户端能在这台机器上跑到终点")
        w("（各客户端的失败原因见第 2 章的状态码）；其二，客户端对目标库的依赖声明范围")
        w("（如 `^4.3.0`、`^0.4.1`）在离线镜像里装不出来，只能钉到镜像里实际存在的版本，")
        w("钉版事实已写入 `provenance.declaredRange` 与 `packageVersion` 两列，可核对。")
    w("")

    w("## 5. 环境漂移：同一份字节上曾合格、现失败")
    w("")
    drift = [r for r in rows if r.get("priorQualifiedRun")]
    if not drift:
        w("无。")
    else:
        w("下列客户端的输入字节与上次合格时完全一致（`inputManifestSha256` 未变），")
        w("差别只在运行环境，因此不能记为复刻缺陷；它们在本表里仍按失败计入，")
        w("不因「曾经通过」而被算作可用。")
        w("")
        w("| 库 | 客户端 | 现状态 | 上次合格自身函数 | 上次合格 run | 本次证据 run |")
        w("| --- | --- | --- | --- | --- | --- |")
        for r in drift:
            w("| %s | %s | %s | %s | %s | %s |" % (
                cell(r["library"]), cell(r["directory"]), cell(r["status"]),
                cell(r["priorQualifiedOwn"]), cell(r["priorQualifiedRun"]),
                cell(r["evidenceRun"])))
        w("")
        for r in drift:
            note = r.get("driftNote") or r.get("reason")
            if note:
                w("- **%s / %s**：%s" % (r["library"], r["directory"], note))
        w("")

    w("## 6. 状态码含义")
    w("")
    w("| 状态 | 含义 |")
    w("| --- | --- |")
    for k in ("qualified", "target-not-exercised", "original-control-failed",
              "truth-or-integrity-failed", "stale-evidence", "no-evidence"):
        w("| `%s` | %s |" % (k, STATUS[k]))
    w("")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", out, "(%d lines)" % (len(L) + 1))


if __name__ == "__main__":
    main()
