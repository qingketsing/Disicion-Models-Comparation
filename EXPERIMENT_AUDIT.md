# Experiment Audit Report — Jev v4 / Qwen 配对

日期：2026-10-15。审阅者：新鲜 gpt-6.1-sol ultra 代理；`review_independence=same-family`、`acceptance_status=provisional`。技能指定的 gpt-6-astra 在当前账户返回 404 未执行，错误与替代路由完整保留；不冒称指定模型成功或跨系列独立验收。

## 审阅结论：WARN（交付归档前的审阅截止状态）

初轮与定向复查均未发现指标伪造、模型输出构造 GT、预测统计自归一化、中断拼接或虚构容量通过。双方 67 个最终 run、2412 个 run 源快照文件、请求指标和费用账经直接核对一致。复查后 A/B/D/E/F 均 PASS；C 的 WARN 仅因当时本文件和最终交付物归档尚未生成。保留审阅原文的历史截止结论，最终文件存在性/归档完成状态单列于 `results/execution-20261014/jev-v4-final-completion.json`，不回写或美化原审阅。

确定性复算、哈希和归档流校验可单列 `deterministic/accepted`；这不提升语义审阅的 provisional 等级。

## A. Ground Truth Provenance：PASS（初轮 WARN 已闭合）

`scripts/prepare_datasets.py:46` 从 MASSIVE 原生 partition/utt/intent 构造数据，`decisionbench/datasets.py:39` 加载标签；`decisionbench/protocol.py:6` 的模型输入不含 GT。首轮原包未本地保留，后从原来源 URL 补回 40251390 字节，SHA256 与实验前 provenance 完全匹配。审阅代理独立解析原包，重建 train11514/validation2033/test2974/checkpoint300 的有序 ID/文本/intent，五项归一化哈希均一致。未改 GT、说明或冻结输入。

证据：`data/normalized/massive-ai-v1/provenance.json:5`、`reports/jev-v4-final-20261015/publisher-source-verification.json:7`；补充归档 `dist/jev-v4-source-provenance-snapshot.tar.gz`（12 成员）逐哈希通过。指标为自定义单标签评价，没有宣称官方评分器结果。

## B. Score Normalization：PASS

Accuracy 为正确逻辑请求/全部记录；F1 为标准 `2TP/(2TP+FP+FN)`，full60 与 supported59 分列，失败记录不被悄悄剔除。没有按模型自身预测的最大值或均值缩放。证据：`decisionbench/metrics.py:18`、`decisionbench/analysis.py:32`；费用取真实记录 usage/时段并保留未知 usage 下界，不将 provider confidence 当分类分数。

## C. Result Existence：数值与已有证据 PASS；审阅截止交付打包 WARN

67 个完成 run 的请求、输入、配置、源快照与独立 Accuracy/F1/p95/lag/数量/费用复算一致。Jev 去重 27 run，17022 测量=17019ok+3client_overload；17196 适配器尝试=17022−3+177。预热135条、138尝试；当前费用含预热1.337850696USD下界，历史/探针合计2.049680304USD下界。Jev39窗口0通过；Qwen正式32RPS15窗口全部通过。

证据：`reports/jev-v4-final-20261015/audit.json`、`network-retry-cost-audit.json`、`historical-cost-audit.json`；配对输入与区间见 `reports/qwen-jev-main-paired-20261015/audit.json`。原始证据2141成员和补充来源12成员的归档流/回执/当前文件三方哈希均经审阅代理复核。

审阅时最终交付物归档和根目录审计文件未存在，故保留 C WARN。生成它们后的确定性检查、Git 快照、最终归档 SHA256 和自动化暂停结果记录在独立 final-completion.json；该收尾回执独立于被校验归档，避免自引用。

## D. Executed Metrics / Dead Code：PASS（初轮 WARN 已闭合）

报告器、独立分析、配对 bootstrap、窗口、retry 和 ledger 均有实际产物，数值可复算。`decisionbench/metrics.py:189` 的月度 TCO 只是可选工具；没有执行场景输入或结果。追踪表 COST 已明确仅“实际日志费用核算”完成，月度业务 TCO 未评估，不以代码存在当结果。

## E. Scope：PASS（初轮 WARN 已闭合）

同2974样本三轮不作3N独立样本；目录规模为每种子200条/10个anchor真值类的配对子集；Jev无确认容量不等于容量为0或API硬上限。部署、网络、重试、Controller同驻分析的潜在干扰与失败usage下界均保留。封存Qwen报告未改，其旧Jev待执行文字在新比较报告中标注2026-10-14截止时点。证据：`docs/QWEN_JEV_COMPARISON_20261015.md:5`、`refine-logs/EXPERIMENT_TRACKER.md:16`及最终报告的方法/限制。

## F. Evaluation Type：PASS

- 主质量、checkpoint、anchor规模：`real_gt`，使用发布者 intent 标签。
- 负载：真实适配器执行的端到端部署测量；其中语义指标仍用 real_gt。
- mock/fixture/连通探针：合成工具检查，排除在主质量之外。
- 40例错误解释：对真实GT错误的 AI 定性审阅，非 `human_eval`，不产生新真值或人口错误比例。

## Claim Impact 与交付闭合

支持固定数据/目录/部署条件下的 Jev86.12418740%、Qwen45.93140551%及逐轮约40.11–40.25个百分点配对差值；支持现路径未确认Jev容量、Qwen最高已测正式通过点32RPS；支持原币、各自范围内的费用下界/时间估算。不能推出普遍模型优越性、硬件容量上限、统一汇率价格排名、月度业务TCO、人工评价或已校正GT。

来源、追踪范围和历史时点提示均已按原始证据闭合；最终打包提示由外部确定性 postflight 闭合。完整请求/响应轨迹（含失败路由和初轮 WARN 原文）在 `.aris/traces/experiment-audit/2026-10-15_run01/`，只随本地交付归档保留，不提交 Git。初轮 response 与复查 response 不覆盖。
