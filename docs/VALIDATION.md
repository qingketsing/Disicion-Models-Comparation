# 验证记录

## 2026-10-13：Windows 本地实验工具验证

Python 3.12.12，项目虚拟环境 `.venv/`。本次建立新的本地环境，锁定依赖见 `requirements-experiments.lock.txt`；历史 Controller 锁文件保留。

| 验证项 | 结果 |
| --- | --- |
| pytest | 42 项通过；1 条上游 Starlette/TestClient 的 httpx 弃用提示 |
| Ruff | 检查通过，格式检查通过 |
| Compose | 所有 profiles 配置校验通过；未启动容器、未验证 GPU |
| 实验计划 | 默认 50 个 run，Jev 请求预算公式通过合成规划测试 |
| 候选规模 | 同 seed 下固定样本、嵌套目录、跨规模保留真值和共同标签顺序 |
| 说明消融 | 不同说明 mapping 的类别顺序对齐测试通过 |
| 请求控制 | 预览不调用 Harness；预算不足、计划预算篡改、API 配额超限均在请求前拒绝 |
| 可复现与续跑 | 配置/输入/源码冻结、完成日志哈希、中断记录、显式失败重试检查通过 |
| 离线分析 | 独立 Accuracy/F1 复算、真值一致性、配对差与区间、CSV/PNG 生成通过 |
| 真实价格入口 | 批量成本重算、cost.json 优先汇总、月度场景测试通过；仅使用测试价格 |
| Token 长度工具 | 复用实际 prompt、关闭 thinking、加输出预算的逻辑测试通过；尚未用真实 tokenizer 和目录检查 |
| 完整本地流程 | `python -m scripts.smoke_suite --name local-smoke-v1` 完成 14 个 Mock run，40 条正式请求与 28 条预热；14 个日志独立复算通过 |
| 上传工具 | 白名单打包测试通过，排除 `.env`、`.venv`、结果和权重 |

本地流程输出位于 `experiments/local-smoke-v1/`、`reports/local-smoke-v1/` 和 `results/`，均被 Git 忽略。模型 ID 虽使用 qwen/jev 便于验证配对分析，但两个 Adapter **均为 Mock**，全部 `synthetic=true`。这些结果只证明软件链路，不证明真实模型性能。

未下载 MASSIVE、未人工审阅正式类别目录、未下载模型权重、未调用 Jev、未连接或上传远程服务器、未产生 GPU/API 费用。服务器镜像、真实接口、真实 tokenizer 长度、稳态容量和实际账单仍待验证。

## 历史记录：2026-10-10

本轮在 2026-10-10（Asia/Shanghai）的本机验证，Python 3.12.13。

| 验证项 | 结果 |
| --- | --- |
| pytest | 29 项通过；有一条上游 TestClient 使用 httpx 的弃用提示，不影响本轮测试 |
| Ruff | 检查通过，代码已格式化 |
| Compose | 全部 profiles 配置校验通过；未启动容器或拉取 GPU 镜像 |
| Mock quality | 6 个请求完整记录，全部合法返回；另存 2 条预热日志 |
| Mock load | 2 秒、20 RPS、40 个计划请求完整记录 |
| Mock overload | 1 秒、100 RPS、并发上限 1；100 个请求完整记录，90 个 client_overload，10 个成功；SLO 50ms 下 Goodput 为 0 |
| Mock dynamic | 2 秒内切换两个目录版本，20 个请求完整记录 |
| Classic HTTP | 实际训练 TF-IDF/SVM，通过 localhost FastAPI → HTTPX → Harness 完成 6 条 fixture 请求；合法成功 6/6 |
| 成本工具 | 演示实例价格的离线成本重算、峰值容量/月度 TCO 命令执行通过 |
| 结果汇总 | JSONL / Manifest / Summary / CSV 已生成；预热不混入正式统计 |
| 数据转换 | MASSIVE 原始分区、BANKING77 训练内验证集划分、固定种子的类别分层抽样通过小样本测试 |

本机虚拟环境 `.venv/` 可直接使用。已生成结果位于 `results/`，这些文件和本机 classic 模型默认被 Git 忽略。`requirements-controller.lock.txt` 记录已验证依赖版本。

所有本轮实验均使用人工小型 fixture；`synthetic=true` 同时覆盖 Mock Adapter 与 fixture 数据。Classic 的 HTTP 实测只验证链路，不代表真实数据集精度或服务容量。Manifest 另存 `mock_adapter` 与 `fixture_dataset`，区分模型和数据来源。

真实 Jev API、4090 vLLM、BERT 训练/推理、Docker 镜像构建和真实账单尚未验证。本机合成日志与小型 TF-IDF/SVM fixture 不能作为模型性能结论。
