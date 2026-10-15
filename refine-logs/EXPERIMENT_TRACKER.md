# 实验执行追踪 v1

更新：2026-10-15（Asia/Shanghai）。当前：Qwen v4 全部40个独立运行完成且封存；Jev v4 pilot24run和正式1RPS300秒三轮已全部完成，去重27run，无已确认容量。费用账与最终离线报告已执行，完整性审阅及最终归档见下方收尾记录；resume1 HTTP499和旧预检独立保留。固定 guidance 后端仅用于Qwen。逐 run 状态由 results/suites/<plan哈希>/index.json 记录。

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| LOCAL | M0 | 验证新增工具 | Mock + fixture | 人工样例 | 日志、预算、续跑、复算 | MUST | 本地验证 | 不属于真实模型结果 |
| DATA | M0 | 冻结数据与说明 | MASSIVE en-US | train/dev/test | 哈希、类别支持、来源 | MUST | DONE | 60 类 AI 审阅，明确非人工；massive-ai-v1 已冻结 |
| ENV | M0 | 服务器与上下文验证 | Qwen + tokenizer | 全部启用输入 | 显存、revision、输入长度 | MUST | DONE | RTX 5090 32GB；11 组上下文检查通过 |
| CP-Q | M1 | Qwen checkpoint | 0.6B / 完整目录 | dev 300 | 合法输出、Accuracy、F1 | MUST | DONE-v4 | 300 条；Accuracy 53.33%；合法 100%；固定 guidance；50 条预热 |
| CP-J | M1 | Jev checkpoint | 固定 API 版本 | dev 300 | 同上、usage | MUST | DONE-local-v3 | 300条全部ok；Accuracy87.6667%；5预热ok；v1/v2历史保留，非完整test |
| MAIN | M2 | 主质量与错误分析 | 两模型各 3 轮 | 完整 test | Accuracy、F1、配对差异 | MUST | QWEN DONE / JEV MAIN DONE | v4 main三轮各2974条逻辑ok，Accuracy86.05%/86.15%/86.18%，均值86.12%；三轮2974唯一样本；旧中断/重试记录保留 |
| LOAD-P | M3 | 负载初测 | 两模型 × 4 RPS × 3 轮 | test 抽样 | p95、Goodput、调度、失败 | MUST | QWEN DONE / JEV DONE-v4 | Jev12组全部未通过，3client_overload；87追加恢复71条；不等同API硬容量 |
| LOAD-F | M3 | 正式容量复测 | 关键负载点 ≥3轮 | test 抽样 | 稳态、可持续容量 | MUST | QWEN DONE / JEV DONE-v4 | Qwen32RPS通过；Jev1RPS300s三轮900ok但时延/调度均未通过，confirmed_capacity_rps=null，全部15窗口未通过 |
| SCALE | M4 | 候选规模 | 两模型 × 10/30/60 × 3种子 | 固定 anchor test 子集 | 质量、延迟、Token | MUST | QWEN DONE / JEV DONE-v4 | 各9 run；Jev10/30/60均值97.17%/94%/90.5%，每次200条；种子内样本配对 |
| COST | M4 | 实际日志费用核算 | 配置价格与记录usage/时间 | 已完成日志 | 费用、Cost/1M | MUST | QWEN DONE / JEV DONE-v4 | Qwen测量4.209604CNY；Jev完成v4含预热1.337850696USD、全部日志含历史探针2.049680304USD下界；非账单，无汇率排名；缺少业务场景参数，月度TCO未评估 |
| DESC | M5 | 类别说明消融 | brief/detailed/boundary | 完整 test | 质量收益与 Token 增长 | OPTIONAL | DISABLED | 默认不执行 |
| REPORT | M5 | 汇总报告 | Qwen / Jev / 配对 | 已完成实验 | 主表、曲线、限制 | MUST | QWEN DONE / JEV DONE-v4 | docs/JEV_EXPERIMENT_REPORT_20261014.md、QWEN_JEV_COMPARISON_20261015.md；最终归档与审阅见收尾记录 |

2026-10-15 04:58UTC：Jev容量等待控制器114740（launcher96784）已启动，仅等待pilot88332完成；三轮main复用，未发送新容量请求。正式300秒三轮及每60秒窗口维持500ms/.99/20ms；无通过点时以1RPS确认。重试四倍实际尝试/Token预算先筛查，16RPS按实测最大2563Token/attempt计算超公布Token配额而不直接扩展；该筛查非突发限速保证。工具45项测试/Ruff通过，冻结v4源码校验通过。

2026-10-15：双方三轮main配对离线完成（每轮N2974），Jev准确率高约40.11–40.25个百分点；完整60类/supported59 F1和部署/网络限制见docs/QWEN_JEV_COMPARISON_20261015.md，容量/总费用尚未定稿。Jev40错误AI审阅非人工见docs/JEV_ERROR_REVIEW_20261014.md。90项测试/Ruff及冻结v4验证通过。正式300s阶段暂停计算密集型本地分析，pilot同机工具工作潜在干扰与全部失败调度点保留。


2026-10-15 最终：Jev27个去重完成run，17022测量/135预热；正式1RPS三轮0/3整轮、0/15窗口通过，confirmed_capacity_rps=null。全部39窗口不通过。report/ledger已实际执行，详见reports/jev-v4-final-20261015及docs/JEV_EXPERIMENT_REPORT_20261014.md。原始/历史/冻结证据2141成员已归档逐SHA256校验，dist/jev-v4-final-evidence-snapshot.tar.gz SHA256 511a7401a752ea06483997c9efad93e0b36adf684a86a26c46f9c9443f5bb91d。Qwen仍封存，不重启。最终语义审阅根目录EXPERIMENT_AUDIT.md/json；最终文档/分析/轨迹归档的SHA256以独立receipt为准。


收尾审阅：来源原包已补回精确匹配并原生分区重建通过；费用核算完成、月度业务TCO未评估。experiment-audit复查A/B/D/E/F PASS、C在打包前截止WARN；实验结果无完整性FAIL，语义审阅same-family/provisional。最终交付物生成及归档流校验以results/execution-20261014/jev-v4-final-completion.json为准；条件满足后jev自动化暂停。
