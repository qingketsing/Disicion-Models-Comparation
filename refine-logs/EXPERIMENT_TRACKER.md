# 实验执行追踪 v1

更新：2026-10-14（Asia/Shanghai）。当前暂停：远程 SSH 认证阶段反复断开。此表用于里程碑；逐 run 的执行状态由 results/suites/<plan哈希>/index.json 记录。

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| LOCAL | M0 | 验证新增工具 | Mock + fixture | 人工样例 | 日志、预算、续跑、复算 | MUST | 本地验证 | 不属于真实模型结果 |
| DATA | M0 | 冻结数据与说明 | MASSIVE en-US | train/dev/test | 哈希、类别支持、来源 | MUST | DONE | 60 类 AI 审阅，明确非人工；massive-ai-v1 已冻结 |
| ENV | M0 | 服务器与上下文验证 | Qwen + tokenizer | 全部启用输入 | 显存、revision、输入长度 | MUST | DONE | RTX 5090 32GB；11 组上下文检查通过 |
| CP-Q | M1 | Qwen checkpoint | 0.6B / 完整目录 | dev 300 | 合法输出、Accuracy、F1 | MUST | DONE-v3 | 300 条；Accuracy 53.33%；合法 100%；50 条预热 |
| CP-J | M1 | Jev checkpoint | 固定 API 版本 | dev 300 | 同上、usage | MUST | DONE-v3 | 300 条；Accuracy 87.67%；合法 100%；5 条预热 |
| MAIN | M2 | 主质量与错误分析 | 两模型各 3 轮 | 完整 test | Accuracy、F1、配对差异 | MUST | INTERRUPTED | Qwen 未启动；Jev 首轮部分 2933/2974，不能作完整结果 |
| LOAD-P | M3 | 负载初测 | 两模型 × 4 RPS × 3 轮 | test 抽样 | p95、Goodput、调度、失败 | MUST | TODO | 120s；24 个 run |
| LOAD-F | M3 | 正式容量复测 | 关键负载点 ≥3轮 | test 抽样 | 稳态、可持续容量 | MUST | TODO | 新版本，≥300s |
| SCALE | M4 | 候选规模 | 两模型 × 10/30/60 × 3种子 | 固定 anchor test 子集 | 质量、延迟、Token | MUST | TODO | 18 个 run，每次 200 条 |
| COST | M4 | 实际费用与 TCO | 真实价格、业务场景 | 已完成日志 | Cost/1M、月度费用 | MUST | TODO | 不发送请求 |
| DESC | M5 | 类别说明消融 | brief/detailed/boundary | 完整 test | 质量收益与 Token 增长 | OPTIONAL | DISABLED | 默认不执行 |
| REPORT | M5 | 汇总报告 | 两模型 | 已完成实验 | 主表、曲线、限制 | MUST | TODO | 不使用合成验证数据作结论 |
