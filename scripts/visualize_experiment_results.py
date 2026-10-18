"""Render report figures from sealed CSVs without changing experiment outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/experiment-results-20261015/visualizations"
SOURCES = {
    "qwen": "reports/qwen-v4-final-20261014/runs.csv",
    "jev": "reports/jev-v4-final-20261015/runs.csv",
    "paired": "reports/qwen-jev-main-paired-20261015/paired-comparisons.csv",
    "qw": "reports/qwen-v4-final-20261014/steady-60s-windows.csv",
    "jw": "reports/jev-v4-final-20261015/steady-60s-windows.csv",
}
BLUE, TEAL, RED, AMBER = "#3268ae", "#008779", "#bb4052", "#bd741f"
INK, MUTED = "#192b40", "#59697b"
GREEN_BG, RED_BG, AMBER_BG = "#deeee8", "#f6dde0", "#faead2"
INPUTS: dict[str, str] = {}
OUTPUTS: dict[str, str] = {}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(key):
    path = ROOT / SOURCES[key]
    INPUTS[SOURCES[key]] = digest(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 11,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#d5dce3",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "path",
    })


def heading(fig, title, subtitle, footer):
    fig.text(.065, .965, title, fontsize=22, weight="bold", va="top")
    fig.text(.065, .91, subtitle, fontsize=11, color=MUTED, va="top")
    fig.text(.065, .025, footer, fontsize=9, color=MUTED, va="bottom")


def save(fig, name):
    for suffix in ["png", "svg"]:
        path = OUT / f"{name}.{suffix}"
        fig.savefig(path, dpi=180)
        if suffix == "svg":
            svg = path.read_text(encoding="utf-8")
            path.write_text(
                "\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
                encoding="utf-8", newline="\n",
            )
        OUTPUTS[path.relative_to(ROOT).as_posix()] = digest(path)
    plt.close(fig)


def quality(models, paired):
    fig, (ax, gap) = plt.subplots(1, 2, figsize=(14, 6.4), gridspec_kw={"width_ratios": [1, 1.25]})
    fig.subplots_adjust(left=.09, right=.96, bottom=.2, top=.76, wspace=.42)
    heading(fig, "01  分类质量：Jev 平均高出 40.19 个百分点",
            "同一组 2974 个唯一样本、同一有序目录；每模型重复三轮，不把 3N 当独立样本。",
            "左：条形为三轮平均，圆点为各轮。右：每轮 N=2974 的配对 bootstrap 95% 区间，2000 次 / seed42。")
    for i, (key, color) in enumerate([("qwen", BLUE), ("jev", TEAL)]):
        vals = [100 * float(r["accuracy"]) for r in models[key] if r["block"] == "main"]
        avg = statistics.mean(vals)
        ax.barh(i, avg, color=color, height=.45, alpha=.9)
        ax.scatter(vals, [i - .05, i, i + .05], s=30, color=INK, zorder=3)
        ax.text(avg + 1.8, i, f"{avg:.2f}%", va="center", weight="bold", fontsize=15)
    ax.set(yticks=[0, 1], yticklabels=["Qwen", "Jev"], xlim=(0, 104), xlabel="Accuracy（%）")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    ax.set_title("完整 test 的准确率", loc="left", fontsize=13, pad=22)
    gap.axvline(0, color="#a1adba", lw=1)
    for i, row in enumerate(paired):
        val, low, high = [100 * float(row[k]) for k in ["accuracy_jev_minus_qwen", "ci95_low", "ci95_high"]]
        gap.errorbar(val, i, xerr=[[val - low], [high - val]], fmt="o", color=TEAL, capsize=6, lw=3)
        gap.text(high + .4, i, f"+{val:.2f}\n[{low:.2f}, {high:.2f}]", va="center", fontsize=11)
    gap.set(yticks=range(3), yticklabels=["第 1 轮", "第 2 轮", "第 3 轮"], xlim=(0, 48),
            ylim=(2.6, -.6), xlabel="Jev − Qwen（百分点）")
    gap.grid(axis="x", alpha=.18)
    gap.set_title("三轮配对差值均为正", loc="left", fontsize=13, pad=22)
    save(fig, "01-quality-paired")


def scale(models):
    fig, ax = plt.subplots(figsize=(12, 6.8))
    fig.subplots_adjust(left=.1, right=.93, bottom=.24, top=.77)
    heading(fig, "02  目录扩大时，两模型准确率均下降",
            "固定 anchor 子集；每个种子 200 条、仅 10 个真值类，10/30/60 类目录嵌套增加干扰类。",
            "大点和连线：三种子均值；小点：每个种子的实测准确率（轻微横向错位以便阅读）。\n这不是完整 test 的准确率，也不将同样本的目录重复测量当作新增样本。")
    for key, color, shift in [("qwen", BLUE, -.035), ("jev", TEAL, .035)]:
        means = []
        for i, k in enumerate([10, 30, 60]):
            vals = [100 * float(r["accuracy"]) for r in models[key] if r["block"] == "scale" and r["variant"] == f"k{k}"]
            means.append(statistics.mean(vals))
            ax.scatter([i + shift + d for d in [-.018, 0, .018]], vals, color=color, alpha=.55, s=28)
        ax.plot(range(3), means, "o-", color=color, lw=3, ms=9, label=key.capitalize() if key == "qwen" else "Jev")
        for i, v in enumerate(means):
            ax.annotate(f"{v:.2f}%", (i, v), xytext=(0, 13 if key == "jev" else -24),
                        textcoords="offset points", ha="center", color=color, weight="bold", fontsize=13)
        drop = means[0] - means[-1]
        ax.text(2.16, means[-1], f"下降 {drop:.2f}\n个百分点", color=color, va="center")
    ax.set(xticks=range(3), xticklabels=["10 类", "30 类", "60 类"], ylim=(0, 108),
           xlim=(-.2, 2.58), ylabel="Accuracy（%）", xlabel="候选目录规模")
    ax.grid(axis="y", alpha=.2)
    ax.legend(loc="lower left", frameon=False)
    save(fig, "02-catalog-scale")


def formal_rows(models):
    return [r for key, rate in [("qwen", "rps32"), ("qwen", "rps64"), ("jev", "rps1")]
            for r in sorted(models[key], key=lambda x: int(x["seed"]))
            if r["block"] == "load" and r["duration_s"] == "300" and r["variant"] == rate]


def formal(models):
    rows = formal_rows(models)
    fig, axes = plt.subplots(1, 3, figsize=(15, 8), sharey=True)
    fig.subplots_adjust(left=.18, right=.97, bottom=.2, top=.77, wspace=.33)
    heading(fig, "03  为什么没通过：逐项看门槛，不能只看最终成功率",
            "正式确认均为 300 秒 × 三轮；红色数值表示该项超限。端到端延迟含重试与退避。",
            "判据：p95 ≤500 ms，最大调度迟滞 ≤20 ms，最终成功率 ≥99%；整轮与每个 60 秒窗口均需通过。\nQwen 32 RPS 全部通过；64 RPS 两轮调度超限。Jev 1 RPS 最终全成功，但延迟与调度均超限。成功率轴局部放大；不同部署不可解释为纯模型速度倍数。")
    labels = [f"{'Jev' if r['job'].endswith('jev') else 'Qwen'}  {r['offered_rps']} RPS · 第{r['repeat']}轮" for r in rows]
    ys = np.arange(len(rows))
    specs = [("p95_ms", 500, "p95 端到端延迟（ms）", 4500),
             ("max_scheduler_lag_ms", 20, "最大调度迟滞（ms）", 43),
             ("success_rate", 99, "最终成功率（%）", 100.35)]
    for ax, (key, limit, title, xmax) in zip(axes, specs):
        for i, r in enumerate(rows):
            val = float(r[key]) * (100 if key == "success_rate" else 1)
            passed = val >= limit if key == "success_rate" else val <= limit
            color = TEAL if passed else RED
            ax.barh(i, val, height=.53, color=color, alpha=.85)
            ax.text(val + (.2 if key == "success_rate" else xmax * .018), i,
                    f"{val:.3f}" if key == "success_rate" else f"{val:.1f}",
                    va="center", color=color, fontsize=10, ha="left")
        ax.axvline(limit, color=INK, ls="--", lw=1.3)
        ax.set_xlim(98.5 if key == "success_rate" else 0, xmax if key != "success_rate" else 101.2)
        ax.set_title(title, fontsize=12, pad=20)
        ax.text(limit, 1.03, f"门槛 {limit:g}", transform=ax.get_xaxis_transform(), ha="center", fontsize=9)
        ax.grid(axis="x", alpha=.16)
        ax.set_axisbelow(True)
        for boundary in [2.5, 5.5]:
            ax.axhline(boundary, color="#cdd6df", lw=1)
    axes[0].set(yticks=ys, yticklabels=labels, ylim=(8.7, -.7))
    axes[2].set_xticks([99, 100])
    save(fig, "03-formal-thresholds")


def pilot_matrix(models):
    fig, axes = plt.subplots(1, 2, figsize=(14, 9), gridspec_kw={"width_ratios": [1.08, 1]})
    fig.subplots_adjust(left=.15, right=.96, bottom=.2, top=.78, wspace=.3)
    heading(fig, "04  相同初测负载：Jev 每轮调度均超限",
            "120 秒初测；逐格展示实测值，不用均值掩盖异常轮次。绿色达标、红色超限。",
            "单元格依次显示 p95 ms / 最大调度迟滞 ms / 最终成功率；色块仅表示对应单项，不代表整轮容量结论。\n3 条 Jev client_overload 均在 8 RPS 第1轮，未送入适配器。Jev 2 RPS 第2轮 p95=10740.2 ms，未截断该异常。")
    for ax, key, title in zip(axes, ["qwen", "jev"], ["Qwen · 远程 GPU / Controller", "Jev · Windows / 代理 / API"]):
        for y, (rate, seed) in enumerate((rate, seed) for rate in [1, 2, 4, 8] for seed in [42, 43, 44]):
            row = next(r for r in models[key] if r["block"] == "load" and r["duration_s"] == "120"
                       and r["variant"] == f"rps{rate}" and int(r["seed"]) == seed)
            for x, field in enumerate(["p95_ms", "max_scheduler_lag_ms", "success_rate"]):
                val = float(row[field])
                passed = val >= .99 if x == 2 else val <= (500 if x == 0 else 20)
                ax.add_patch(plt.Rectangle((x - .49, y - .46), .98, .92,
                                          color=GREEN_BG if passed else RED_BG, ec="white"))
                text = f"{val * 100:.3f}%" if x == 2 else f"{val:.1f}"
                ax.text(x, y, text, ha="center", va="center", color=TEAL if passed else RED, fontsize=12)
        ax.set(xlim=(-.5, 2.5), ylim=(11.5, -.5), xticks=range(3),
               xticklabels=["p95\n≤500 ms", "调度迟滞\n≤20 ms", "最终成功率\n≥99%"])
        ax.set_yticks(range(12), [f"{rate} RPS · 第{seed-41}轮" for rate in [1, 2, 4, 8] for seed in [42, 43, 44]])
        ax.xaxis.tick_top()
        ax.tick_params(length=0, axis="both", pad=9)
        ax.set_title(title, fontsize=13, pad=48)
        for spine in ax.spines.values():
            spine.set_visible(False)
    save(fig, "04-pilot-status-matrix")


def windows(models, window_data):
    rows = formal_rows(models)
    fig, ax = plt.subplots(figsize=(14, 7.8))
    fig.subplots_adjust(left=.23, right=.95, bottom=.22, top=.77)
    heading(fig, "05  按分钟检查：请求最终成功，不代表稳态达标",
            "正式 300 秒每轮拆为五个 60 秒到达窗口；格内标出不通过的指标，不将失败归因于未经证实的具体组件。",
            "Jev 正式 1 RPS：0/15 窗口通过；Qwen 正式 32 RPS：15/15；64 RPS：11/15，但三轮中两轮未全通过。\n迟滞是 Controller 相对计划发送时刻的滞后；端到端延迟包含网络、服务、重试及等待，不能据此单独定位根因。")
    labels = []
    colors = {"通过": GREEN_BG, "调度": AMBER_BG, "延迟": RED_BG, "延迟＋调度": "#e9b9c3"}
    for y, row in enumerate(rows):
        key = "jev" if row["job"].endswith("jev") else "qwen"
        labels.append(f"{'Jev' if key == 'jev' else 'Qwen'}  {row['offered_rps']} RPS · 第{row['repeat']}轮")
        ws = sorted([w for w in window_data[key] if w["job"] == row["job"] and w["duration_s"] == "300"],
                    key=lambda w: int(w["start_s"]))
        assert len(ws) == 5
        for x, w in enumerate(ws):
            latency = float(w["p95_ms"]) > 500
            lag = float(w["max_scheduler_lag_ms"]) > 20
            assert float(w["success_rate"]) >= .99
            label = "延迟＋调度" if latency and lag else "延迟" if latency else "调度" if lag else "通过"
            assert (label == "通过") == (w["passed"] == "True")
            ax.add_patch(plt.Rectangle((x - .48, y - .44), .96, .88, color=colors[label]))
            ax.text(x, y, label, ha="center", va="center", fontsize=11, color=INK)
    ax.set(xlim=(-.5, 4.5), ylim=(8.6, -.6), xticks=range(5),
           xticklabels=["0–60 秒", "60–120 秒", "120–180 秒", "180–240 秒", "240–300 秒"],
           yticks=range(9), yticklabels=labels)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, pad=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.legend(handles=[Patch(color=c, label=k) for k, c in colors.items()],
               loc="lower center", bbox_to_anchor=(.55, .105), ncol=4, frameon=False)
    save(fig, "05-formal-minute-windows")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    style()
    models = {key: load(key) for key in ["qwen", "jev"]}
    paired = load("paired")
    wd = {"qwen": load("qw"), "jev": load("jw")}
    quality(models, paired)
    scale(models)
    formal(models)
    pilot_matrix(models)
    windows(models, wd)
    for name, expected in INPUTS.items():
        assert digest(ROOT / name) == expected, f"Source changed: {name}"
    manifest = {"scope": "Read-only visualization of sealed CSV values; no experiment requests or source mutations.",
                "source_sha256": INPUTS, "figure_sha256": OUTPUTS,
                "script_sha256": digest(Path(__file__)),
                "semantics": {"quality_bar": "mean of three repeats; points are repeats, not independent N",
                              "paired_ci": "precomputed per-repeat paired bootstrap95; no pooled 3N",
                              "status_cells": "fixed 500ms/.99/20ms predicates; no threshold changes"}}
    (OUT / "visualization-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(OUTPUTS)} PNG/SVG artifacts from {len(INPUTS)} unchanged CSV sources.")


if __name__ == "__main__":
    main()
