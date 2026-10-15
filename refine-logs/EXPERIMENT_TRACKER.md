# 实验执行追踪 v1

更新：2026-10-15（Asia/Shanghai）。当前：Qwen v4 全部40个独立运行完成，最终离线审计通过，报告和备份完成；用户授权网络错误追加3次请求重试，Jev v4三轮main与九组scale已完成，load进行中；resume1 HTTP499历史保留；旧v3 checkpoint为历史预检。固定 guidance 后端仅用于Qwen。此表用于里程碑；逐 run 的执行状态由 results/suites/<plan哈希>/index.json 记录。

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| LOCAL | M0 | 验证新增工具 | Mock + fixture | 人工样例 | 日志、预算、续跑、复算 | MUST | 本地验证 | 不属于真实模型结果 |
| DATA | M0 | 冻结数据与说明 | MASSIVE en-US | train/dev/test | 哈希、类别支持、来源 | MUST | DONE | 60 类 AI 审阅，明确非人工；massive-ai-v1 已冻结 |
| ENV | M0 | 服务器与上下文验证 | Qwen + tokenizer | 全部启用输入 | 显存、revision、输入长度 | MUST | DONE | RTX 5090 32GB；11 组上下文检查通过 |
| CP-Q | M1 | Qwen checkpoint | 0.6B / 完整目录 | dev 300 | 合法输出、Accuracy、F1 | MUST | DONE-v4 | 300 条；Accuracy 53.33%；合法 100%；固定 guidance；50 条预热 |
| CP-J | M1 | Jev checkpoint | 固定 API 版本 | dev 300 | 同上、usage | MUST | DONE-local-v3 | 300条全部ok；Accuracy87.6667%；5预热ok；v1/v2历史保留，非完整test |
| MAIN | M2 | 主质量与错误分析 | 两模型各 3 轮 | 完整 test | Accuracy、F1、配对差异 | MUST | QWEN DONE / JEV MAIN DONE | v4 main三轮各2974条逻辑ok，Accuracy86.05%/86.15%/86.18%，均值86.12%；三轮2974唯一样本；旧中断/重试记录保留 |
| LOAD-P | M3 | 负载初测 | 两模型 × 4 RPS × 3 轮 | test 抽样 | p95、Goodput、调度、失败 | MUST | QWEN DONE / JEV RUNNING-v4 | Qwen基础套件通过；Jev load运行中，首个4RPS延迟/调度超限、2RPS调度超限；保持原阈值，尚无完整三轮结论 |
| LOAD-F | M3 | 正式容量复测 | 关键负载点 ≥3轮 | test 抽样 | 稳态、可持续容量 | MUST | QWEN DONE / JEV WAITING-PILOT | 32/64RPS各300s三轮；32及15个60s窗口通过，64两轮调度迟滞超限 |
| SCALE | M4 | 候选规模 | 两模型 × 10/30/60 × 3种子 | 固定 anchor test 子集 | 质量、延迟、Token | MUST | QWEN DONE / JEV DONE-v4 | 各9 run；Jev10/30/60均值97.17%/94%/90.5%，每次200条；种子内样本配对 |
| COST | M4 | 实际费用与 TCO | 真实价格、业务场景 | 已完成日志 | Cost/1M、月度费用 | MUST | QWEN DONE / JEV PAUSED | 2.78CNY/h；测量费用4.209604CNY，非账单；32RPS约24.13CNY/百万合法成功 |
| DESC | M5 | 类别说明消融 | brief/detailed/boundary | 完整 test | 质量收益与 Token 增长 | OPTIONAL | DISABLED | 默认不执行 |
| REPORT | M5 | 汇总报告 | Qwen-only | 已完成实验 | 主表、曲线、限制 | MUST | QWEN DONE / JEV PAUSED | docs/QWEN_EXPERIMENT_REPORT_20261014.md；40独立run去重审计与SHA256备份 |

2026-10-15 04:58UTC：Jev容量等待控制器114740（launcher96784）已启动，仅等待pilot88332完成；三轮main复用，未发送新容量请求。正式300秒三轮及每60秒窗口维持500ms/.99/20ms；无通过点时以1RPS确认。重试四倍实际尝试/Token预算先筛查，16RPS按实测最大2563Token/attempt计算超公布Token配额而不直接扩展；该筛查非突发限速保证。工具45项测试/Ruff通过，冻结v4源码校验通过。
