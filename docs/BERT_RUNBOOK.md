# BERT 节点执行手册

实现已合入 `main`，提交 `820625e53d082219f571dee64bd12a46c478f24c`，基于 PR #2。按用户要求保留 MASSIVE 原生 train/dev/test（11,514 / 2,033 / 2,974），不去重；文本重叠只警告并写入训练产物。模型、输入、配置、训练源代码和环境均留证。

本地已验证 Python 3.12 + CPU 的小型 BERT 训练、最佳 checkpoint 导出、续训、真实 HTTP、quality/load 与离线分析链路。2026-10-18/19 已在 RTX 5090 / Python 3.12.3 / PyTorch 2.9.1+cu128 上完成实际 CUDA 前向、反向与优化器更新、端到端 smoke、42 项测试，以及三种子 BERT-base 训练和九轮完整质量评测。独立 Windows Controller 经 SSH 的 32 RPS 初测通过、64 RPS 失败，正式容量尚未确认；容器构建未在本轮验证。详见[节点报告](../reports/bert-5090-20261019/REPORT.md)与[复现说明](../reports/bert-5090-20261019/REPRODUCE.md)。其他节点仍需执行下述环境自检。

## 1. 上传与安装

可直接传输 `scripts.package_bert_worker` 生成的 ZIP，解压进入项目根目录。包内含源文件及逐文件 SHA256 清单，不含环境、数据原包或模型权重；未提交改动也包含在包内，以清单为准。

节点提供 Python 3.12；若已有 uv，可用 `uv python install 3.12` 安装到用户目录。下面使用 Linux 命令：

```bash
python3.12 scripts/bootstrap_bert.py --device cuda --cuda-wheel cu128
source .venv-bert/bin/activate
export CUDA_VISIBLE_DEVICES=0
python -m scripts.smoke_bert --device cuda --out results/node-smoke-001
python -m pytest -q
```

只有 CPU 的 Controller 可用 `--device cpu`。Windows 使用 `py -3.12 scripts/bootstrap_bert.py --device cpu`，随后执行 `.venv-bert/Scripts/python.exe`。脚本只修改所选虚拟环境，不安装或变更宿主机驱动。

固定主依赖为 PyTorch 2.9.1、Transformers 4.57.1、datasets 4.3.0、accelerate 1.11.0；`requirements-bert.lock.txt` 固定本地验证的共享依赖，CUDA 相关依赖来自指定官方 wheel，节点安装后另存完整 `pip freeze --all`。CUDA wheel 的可选值为 cu126/cu128/cu130，默认 cu128；根据节点驱动与实际前向/反向 smoke 结果选择，不能只凭 `nvidia-smi` 显示 CUDA 字样认定可用。

安装回执在 `results/bert-setup-*/`。`check_bert_environment` 会实际执行小 BERT 的 forward、backward 和 optimizer step；`smoke_bert` 再完整测试训练、服务、压测与分析，全部标记 synthetic，不作为论文跑分。若失败，先查对应日志，不继续正式任务。依据：[PyTorch 官方历史版本](https://pytorch.org/get-started/previous-versions/)。

## 2. 冻结正式计划

先按节点显存确定 `configs/bert-experiment.yaml` 中的 batch、梯度累积和 device；默认 batch=16、FP32、长度128、五个 epoch、seed 42/43/44。默认优化器 AdamW，学习率 2e-5、weight decay 0.01、warmup ratio 0.1。若需要调整，复制为新的配置文件，避免改写已冻结实验。

```bash
python -m scripts.bert_experiment prepare \
  --config configs/bert-experiment.yaml \
  --out experiments/bert-native-v1/plan.json
```

这个命令自动下载约40 MB的发布方 MASSIVE 1.1 原包并核验 PR #2 中的 SHA256，保留原生分区，使用 PR 的 AI 审阅类别说明。它创建明确的新 BERT 目录版本，不声称恢复了历史目录字节。模型 `main` 只在此时解析一次为不可变 commit；训练阶段只使用该 commit。

可通过 `--source /path/to/amazon-massive-dataset-1.1.tar.gz` 复用同一原包。模型权重由 Hugging Face 下载并缓存；有镜像需求时应保持仓库 ID 和 commit 一致。网络认证按节点环境配置，凭据不写进计划。

计划和 `.sha256.json` 必须一起保存。数据文件 SHA256 按原字节校验；源码 SHA256 统一 LF 以适应 Windows/Linux。后续输入或源码变化会阻止运行，需要新版本计划。已有数据输出目录不会被覆盖；为新计划设置新的 `name`、`data_dir` 和 `model_dir`。

## 3. 三种子训练与恢复

```bash
python -m scripts.bert_experiment train --plan experiments/bert-native-v1/plan.json
```

三个 seed 顺序训练，日志位于 `models/bert-native-v1/logs/`，产物位于 `models/bert-native-v1/seed-42/` 等目录。只依照 validation full60 Macro-F1 选最佳 checkpoint；同分保留较早 checkpoint，不查看 test。整个部署模型再按 dev F1、dev Accuracy、较小 seed 选择，写入 `selection.json`。

每份产物包含权重、tokenizer、目录、训练配置、重叠计数、token 截断统计、学习曲线、训练耗时、环境、源码快照和文件哈希。服务只依赖最终权重与证据，不依赖 optimizer checkpoints。文本重叠允许继续；重复 sample_id、非法标签、改变过的输入仍会阻止运行。

已成功的 seed 会经哈希及配置核验后跳过。失败任务保留日志和 `training-state.json`，不会把部分产物当成功。存在完整 checkpoint 时显式续训：

```bash
python -m scripts.bert_experiment train \
  --plan experiments/bert-native-v1/plan.json --seed 42 \
  --resume models/bert-native-v1/seed-42/checkpoints/checkpoint-720
```

`checkpoint-720` 只是路径示例，使用实际 checkpoint。参数、输入、训练源码或记录的运行环境不同会拒绝续训。首次 checkpoint 前中断时，用新的输出/计划版本重新开始。

## 4. 启动服务与质量评测

在 Worker 前台启动指定训练 seed 的服务：

```bash
python -m scripts.bert_experiment serve \
  --plan experiments/bert-native-v1/plan.json --seed 42 --device cuda
```

依次对 42/43/44 执行质量评测；切换时等待当前服务退出，再启动下一个。启动后通过 `/health` 和 `/metadata` 核对模型版本及训练 seed 与目标一致，不能仅检查 `ready`，以免误认尚未退出的旧服务。省略 `--seed` 会按 dev 指标选部署模型，需要全部训练 seed 已完成。CPU 对照只将 `--device` 改为 `cpu`，默认4线程，使用同一权重。服务启动核验文件哈希和类别顺序，默认单进程、FP32、batch=1、串行推理。

独立 Controller 使用同版本源代码、计划/回执和冻结的数据目录，无需拷贝模型权重。通过 SSH 隧道访问 Worker 的回环服务：

```bash
ssh -N -L 8001:127.0.0.1:8001 USER@WORKER
```

Controller 执行：

```bash
python -m scripts.bert_experiment evaluate \
  --plan experiments/bert-native-v1/plan.json \
  --stage quality --base-url http://127.0.0.1:8001 \
  --network-note "independent-controller-to-worker-over-SSH"
```

每个模型顺序测完整2974条 test 三轮，逐轮核验服务模型、训练数据和目录；健康信息和完整模型元数据进入 run manifest。训练种子与推理轮次分别记录，不合并为独立3N或9N样本。synthetic smoke 服务不能进入正式套件。`configs/bert-quality.yaml` 也已改为完整 test，但直接 harness 模板不会自动做套件级服务身份检查，因此正式运行优先使用上面的命令。

## 5. 负载与离线分析

选择部署模型后，在同一服务下执行：

```bash
python -m scripts.bert_experiment evaluate \
  --plan experiments/bert-native-v1/plan.json --stage pilot \
  --network-note "independent-controller-to-worker-over-SSH"

# 16、32 仅是命令示例；根据本次 pilot 选择候选档位和相邻更高档位。
python -m scripts.bert_experiment evaluate \
  --plan experiments/bert-native-v1/plan.json --stage formal --rps 16 32 \
  --network-note "independent-controller-to-worker-over-SSH"
```

pilot 默认1/2/4/8/16/32/64 RPS，各120s × 3；formal 为指定档位各300s × 3。阶段间默认冷却30s。每个套件写 `index.json`，记录完成的 run 和失败/中断状态。一次失败不会自动重跑以替换原记录；重测新建套件目录。

CPU/GPU 分开测，不与其它模型共享繁忙 GPU。Controller 不与训练/压缩任务同时运行；默认并发上限128，正式前可在新计划中调整并做调度预检。p95 ≤500ms、合法率≥99%、最大调度迟滞≤20ms三项同时达标，且正式三轮及全部60秒窗口通过，才确认该档位的技术容量。质量达标与否另行解释。

使用实际 index 路径分析，可重复传多个 `--index`：

```bash
python -m scripts.analyze_bert \
  --index results/ACTUAL-QUALITY-SUITE/index.json \
  --index results/ACTUAL-FORMAL-SUITE/index.json \
  --baseline reports/qwen-jev-main-paired-20261015/paired-sample-outcomes.csv \
  --out reports/bert-analysis-001
```

输出 `runs.csv`、`steady-60s-windows.csv`、`paired-comparisons.csv`、逐run复算JSON及 `audit.json`。窗口按计划到达时间归属，跨窗口慢请求仍留在原窗口；费用不重复累计窗口排空时间。配对比较核对完整文本和真值，按每个模型版本、每轮、每个历史对手轮次独立bootstrap；不把重复调用拼成独立样本。

`--pricing actual-pricing.json` 可离线复算测量与排空成本，格式沿用项目 instance/API 定价协议，不能使用 demo 价格作实测价格。结果包含每百万正确请求、每百万SLO内正确请求的成本。训练和空闲费用另计：训练产物保存 `training_wall_s`，真实训练小时价乘以秒数/3600；同一产物跨CPU/GPU或重复调用时训练费只计一次。月度摊销沿用 `scripts/monthly_tco.py`，传入实际训练/维护费用。

## 6. Docker 与交付

原生虚拟环境是首选执行路径；Docker 路径已提供，需在节点实际构建验证：

```bash
export BERT_MODEL_PATH=./models/bert-native-v1/seed-42
export BERT_TORCH_FLAVOR=cu128
docker compose --profile bert-gpu up --build -d bert-gpu
# 切换 CPU 前先停止 GPU 服务，避免8001端口冲突。
docker compose stop bert-gpu
docker compose --profile bert-cpu up --build -d bert-cpu
```

Dockerfile 使用相同主依赖和共享约束；构建完保存 image digest，GPU运行还依赖节点的 NVIDIA Container Toolkit。不会将本机环境验证表述为已验证远端容器。

生成可上传代码包：

```bash
python -m scripts.package_bert_worker --out dist/bert-worker-001.zip
```

保留 plan/data、模型产物/训练日志和 results；分析可在另一台机器离线完成。节点访问方式、磁盘、GPU、驱动和资源预算确定后，再冻结正式配置并执行上述流程。
