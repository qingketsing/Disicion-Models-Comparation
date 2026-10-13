# Research Output Manifest

> Tracks experiment planning and implementation artifacts. All real server experiments remain pending.

| Timestamp | Skill | File | Stage | Description |
|-----------|-------|------|-------|-------------|
| 2026-10-13 12:42:51 | /experiment-plan | refine-logs/EXPERIMENT_PLAN_20261013_124251.md | implementation | 五项实验的协议、预算、执行顺序和待确认参数 |
| 2026-10-13 12:42:51 | /experiment-plan | refine-logs/EXPERIMENT_PLAN.md | implementation | latest copy |
| 2026-10-13 12:42:51 | /experiment-plan | refine-logs/EXPERIMENT_TRACKER_20261013_124251.md | implementation | 未执行真实实验的里程碑清单 |
| 2026-10-13 12:42:51 | /experiment-plan | refine-logs/EXPERIMENT_TRACKER.md | implementation | latest copy |
| 2026-10-13 12:53 | /experiment-plan | docs/REMOTE_EXPERIMENTS.md | implementation | 服务器部署、运行、重试、复算与上传说明 |
| 2026-10-13 12:53 | /experiment-plan | configs/experiment-suite.yaml | implementation | 默认两模型实验矩阵，待填环境 |
| 2026-10-13 12:53 | /experiment-plan | configs/pricing-real.template.json | implementation | 真实价格待填写，null 无法直接执行 |
| 2026-10-13 12:53 | /experiment-plan | configs/tco-scenarios.json | implementation | 待确认的月度流量场景 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/suite.py | implementation | 冻结、预览、预算、执行、续跑 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/variants.py | implementation | 相同 anchor 样本上的嵌套类别目录 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/analysis.py | implementation | 指标复算、配对区间、错误案例与图表 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/cost_analysis.py | implementation | 批量离线价格与月度场景对照 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/adapters.py | implementation | 共享 Qwen prompt 构造供输入长度检查 |
| 2026-10-13 12:53 | /experiment-plan | decisionbench/cli.py | implementation | 运行创建回调与 UTF-8 成本文件读取 |
| 2026-10-13 12:53 | /experiment-plan | scripts/check_qwen_context.py | implementation | 同 revision tokenizer 输入窗口检查 |
| 2026-10-13 12:53 | /experiment-plan | scripts/collect_environment.py | implementation | 只读硬件与依赖快照 |
| 2026-10-13 12:53 | /experiment-plan | scripts/package_experiments.py | implementation | 白名单上传包 |
| 2026-10-13 12:53 | /experiment-plan | scripts/smoke_suite.py | implementation | 完全本地 Mock 演练 |
| 2026-10-13 12:53 | /experiment-plan | scripts/aggregate.py | implementation | 优先读取离线重算 cost.json |
| 2026-10-13 12:53 | /experiment-plan | scripts/prepare_datasets.py | implementation | UTF-8 类别说明读取 |
| 2026-10-13 12:53 | /experiment-plan | tests/test_experiments.py | implementation | 新实验流程的 13 项测试 |
| 2026-10-13 12:53 | /experiment-plan | requirements-experiments.lock.txt | implementation | 本地 Python 3.12 实验工具依赖 |
| 2026-10-13 12:53 | /experiment-plan | pyproject.toml | implementation | 实验绘图和 tokenizer 可选依赖 |
| 2026-10-13 12:53 | /experiment-plan | docker-compose.yaml | implementation | 显式精度、上下文和 prefix cache 设置 |
| 2026-10-13 12:53 | /experiment-plan | .env.example | implementation | Worker 参数示例，不含密钥 |
| 2026-10-13 12:53 | /experiment-plan | .gitignore | implementation | 排除冻结实验、报告和上传产物 |
| 2026-10-13 12:53 | /experiment-plan | README.md | implementation | 实验入口与 Windows 环境说明 |
| 2026-10-13 12:53 | /experiment-plan | docs/IMPLEMENTATION_BACKLOG.md | implementation | 工具完成、真实实验待执行的状态 |
| 2026-10-13 12:53 | /experiment-plan | docs/VALIDATION.md | implementation | 42 测试与 14 个 Mock run 验证记录 |
| 2026-10-13 12:53 | /experiment-plan | reports/local-smoke-v1/ | implementation | 14 个合成运行的复算示例，不能用于模型结论 |
| 2026-10-13 12:53 | /experiment-plan | dist/decisionbench-server-v1.zip | implementation | 本地代码上传包，尚未上传 |
