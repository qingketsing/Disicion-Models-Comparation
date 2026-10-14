# DecisionBench

Jev / Qwen / BERT 共用数据、测量和成本口径的实验框架。Controller 在本机或独立 CPU 主机产生请求，GPU Worker 按模型轮流运行。

当前为新实现的 v0.1。用户提供的方案已保存在 `docs/ORIGINAL_PLAN.txt`，附件中没有 Starter ZIP。本项目不包含真实 Jev、Qwen 或 BERT 跑分。

## Qwen 与 Jev 远程实验

2026-10-14 新服务器上传、环境和模型准备记录见 [westd 准备记录](docs/WESTD_PREPARATION_20261014.md)，原生启动配置为 `configs/qwen-native-westd.json`。

已新增可执行实验套件：质量评测、开放环负载、嵌套候选类别规模、可选类别说明消融、配对分析和实际价格重算。实验入口默认只预览；`--execute` 才发送请求，Jev 执行还需要显式请求预算。

- [详细实验方案](refine-logs/EXPERIMENT_PLAN.md) 与 [实验追踪](refine-logs/EXPERIMENT_TRACKER.md)
- [服务器操作手册](docs/REMOTE_EXPERIMENTS.md)
- [实验参数模板](configs/experiment-suite.yaml) 与 [真实价格模板](configs/pricing-real.template.json)

```bash
# 软件验证：fixture + Mock，完全不调用 Qwen/Jev。
python -m scripts.smoke_suite --name local-smoke-v1
# 真实数据和人工审阅说明准备好后，冻结可上传的实验套件。
python -m decisionbench.suite prepare -c configs/experiment-suite.yaml --out experiments/massive-v1
# 预览请求数量，不构造 Adapter、不发送 HTTP 请求。
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block checkpoint
# 完成真实实验后离线复算并生成 CSV/PNG。
python -m decisionbench.analysis --plan experiments/massive-v1/plan.json --out reports/massive-v1 --plots
```

## 本机开始

Windows 副本已在 2026-10-13 创建 Python 3.12 虚拟环境。PowerShell 进入项目目录后：

```powershell
.venv\Scripts\Activate.ps1
python -m pytest -q
```

Linux/macOS 安装环境后激活并运行基础自测：

```bash
source .venv/bin/activate
pytest -q
python -m decisionbench.cli run -c configs/smoke-quality.yaml
python -m decisionbench.cli run -c configs/smoke-load.yaml
python -m decisionbench.cli run -c configs/smoke-overload.yaml
python -m decisionbench.cli run -c configs/smoke-dynamic.yaml
python scripts/aggregate.py
```

新机器安装：

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-controller.lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
```

也可以用 `pip install -e '.[dev,serve,classic]'` 按依赖范围安装。锁文件记录本轮 Controller 已验证版本；GPU Worker 需要单独冻结 Torch、CUDA、驱动和容器版本。

## 已实现

| 部分 | 行为 |
| --- | --- |
| 统一协议 | 输入与真值隔离；目录冻结；请求 ID 与样本 ID 独立；概率和置信度分别保存 |
| quality | 顺序评测，Accuracy、Macro-F1、混淆矩阵、拒识率；错误保留在分母 |
| load | 固定速率开放环；并发满显式拒绝；E2E deadline、调度延迟、p50/p95/p99、Goodput |
| dynamic | 按预定时间切换目录的初步回放；记录每阶段结果 |
| cost | 离线重算实例/API 成本；成功与 SLO 有效请求分别核算；月度容量/TCO |
| 接入 | Jev Choice、Qwen/vLLM、BERT/classic HTTP；HTTP 模拟契约测试 |
| Serving | TF-IDF/SVM、BERT 训练入口与 FastAPI 服务；目录不匹配返回 409；Prometheus 指标 |
| 可复现 | 配置/数据/目录哈希，源码快照，Controller 依赖版本，Worker 环境填写项 |

动态模式暂不包含重训自动化、恢复时间和旧类退化研究。BGE、INT8、校准拒识、Grafana 仪表盘在后续开发清单中。

## 真实数据与 Checkpoint 1

第一轮目标：MASSIVE 同一批 300 条验证样本，冻结等价类别说明，依次测 Jev / Qwen3-0.6B / BERT。

```bash
# 下载发布方 MASSIVE 1.1 原始压缩包（包含所有语言，体积较大）。
python scripts/prepare_datasets.py --name massive --download --out data/normalized/massive

# 或使用已有 en-US 原始文件，避免重复下载。
python scripts/prepare_datasets.py --name massive --source /path/to/en-US.jsonl --out data/normalized/massive

# BANKING77 使用固定发布方 Git commit，训练集内按类别划出 10% 验证集。
python scripts/prepare_datasets.py --name banking77 --download --out data/normalized/banking77
```

输出 `train.jsonl`、`validation.jsonl`、`test.jsonl`、`checkpoint-300.jsonl`、`catalog.json`、`provenance.json`。默认类别说明由标签名生成，必须人工审阅后才能验收正式基线。推荐通过 `--descriptions reviewed-descriptions.json` 输出一个新的冻结目录；三个模型使用同一份目录。训练只读训练集，Checkpoint 取验证集，最终报告使用完整测试集。

## 模型启动与接入

`models/classic` 默认被 Git 忽略，不随仓库提供。首次使用先训练；`--out` 不能覆盖已有模型目录。小型 fixture 用于验证真实 HTTP 链路：

```bash
# 若已训练并保留 models/classic，可以跳过这条命令。
python -m services.train_classic --train data/fixtures/train.jsonl --catalog data/fixtures/catalog.json --out models/classic
MODEL_PATH=models/classic uvicorn services.classic_server:app --host 127.0.0.1 --port 8002
# 另一个终端激活同一虚拟环境后：
python -m decisionbench.cli run -c configs/classic-quality.yaml
```

GPU Worker（Linux + NVIDIA Container Toolkit）运行：

```bash
cp .env.example .env
# 正式实验前在 .env 固定 QWEN_REVISION 为模型 commit，并记录 VLLM_IMAGE digest。
docker compose --profile qwen up -d qwen
curl http://127.0.0.1:8000/v1/models
```

示例 vLLM tag 是初始部署候选，尚未实机验证。请求中禁用 Qwen3 thinking，温度为 0，限定输出 JSON 标签。所有模型共用同一份类别说明。输出截断或标签非法时记为失败，并保留接口返回的 Token 用量。

若 Worker 在远端，服务端口通过 SSH 隧道供 Controller 使用：

```bash
ssh -N -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 user@gpu-worker
python -m decisionbench.cli run -c configs/qwen-quality.yaml
```

BERT 在 Worker 单独训练并运行：

```bash
pip install -e '.[bert,serve]'
python -m services.train_bert --train data/normalized/massive/train.jsonl --validation data/normalized/massive/validation.jsonl --catalog data/normalized/massive/catalog.json --out models/bert --revision MODEL_COMMIT

docker compose stop qwen
docker compose --profile bert-gpu up -d bert-gpu
# 测 CPU 前：docker compose stop bert-gpu
# docker compose --profile bert-cpu up -d bert-cpu
python -m decisionbench.cli run -c configs/bert-quality.yaml
```

Qwen 与 BERT GPU 必须分开测。Compose profiles 不构成互斥锁，启动前用 `docker compose ps` / `nvidia-smi` 检查。Worker 配置中的 `environment` 项需要填上真实硬件、模型 revision、容器 digest、线程数和网络条件。

Jev 通过环境变量读取密钥：

```bash
# 在自己的终端设置 TYPESAFE_API_KEY；CLI 不自动读取 .env。
python -m decisionbench.cli run -c configs/jev-quality.yaml
```

缺少密钥、数据或服务时会报错。项目没有调用任何付费 API 或租用 GPU。

## 结果、成本与后续实验

每次实验生成独立目录：

```text
results/<UTC时间>-<实验名>-<随机ID>/
  manifest.json          # 完成状态、版本/哈希和环境
  inputs/                # 冻结配置、完整样本和目录
  source/                # 执行源码快照
  warmup_requests.jsonl  # 预热日志；不进入正式统计
  requests.jsonl         # 逐请求状态、预测、耗时、用量
  summary.json           # 指标与已配置成本
```

```bash
# 用实际账单创建 pricing.json，结构参考 pricing-demo.json（演示价格不可用于报告）。
python -m decisionbench.cli cost results/RUN_DIRECTORY --pricing pricing.json
python scripts/monthly_tco.py --monthly-requests 1000000 --peak-rps 5 --max-slo-qps 20 --instance-price-per-hour 5 --currency CNY
# 可选导出：pip install -e '.[analysis]'
python scripts/export_parquet.py results/RUN_DIRECTORY
# 同一 Compose 网络可采集服务内部指标：
docker compose --profile observability up -d prometheus
```

Goodput = 合法成功且 E2E ≤ SLO 的请求数 / 发送窗口及排空时间。另存 Correct Goodput，同时要求语义正确。最大容量需要独立质量基线、足够成功率、p95 SLO 和有效的客户端调度共同支撑；单行 `slo_capacity_candidate` 仅表示本次负载结果可作为候选。正式测试重复 3–5 轮并做稳态分析。

API 超时可能已被服务端计费；没有 usage 时成本标注为下界。按测量时长算实例成本不覆盖空闲、预热或训练；这些应进入月度 TCO。不同币种需要使用同一个汇率时间点换算。

开发与验收见 [实验协议](docs/EXPERIMENT_PROTOCOL.md)、[开发清单](docs/IMPLEMENTATION_BACKLOG.md)、[Checkpoint 1](docs/CHECKPOINT_1.md) 和 [当前验证记录](docs/VALIDATION.md)。

接入依据：[Jev API](https://docs.typesafe.ai/api)、[Qwen3 vLLM 部署](https://github.com/QwenLM/Qwen3/blob/main/docs/source/deployment/vllm.md)、[MASSIVE 发布方](https://github.com/alexa/massive)、[BANKING77 发布方](https://github.com/PolyAI-LDN/task-specific-datasets)。
