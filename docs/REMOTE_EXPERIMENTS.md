# 远程服务器实验操作手册

本地已经准备代码。当前服务器为 westd:16259，项目路径 `/root/autodl-tmp/decisionbench`；最新准备与验证记录见 [2026-10-14 新服务器记录](WESTD_PREPARATION_20261014.md)。以下通用操作中的路径按实际位置替换。真实模型实验与 Jev 付费请求尚未执行。

## 1. 本地查看与上传包

本机 PowerShell，在项目根目录执行：

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check decisionbench services scripts tests
.venv\Scripts\python.exe -m scripts.smoke_suite --name local-smoke-v2
.venv\Scripts\python.exe -m scripts.package_experiments --out dist/decisionbench-server-v1.zip
```

打包只包含代码、配置、文档、测试和 fixture，排除 `.env`、虚拟环境、结果和模型权重。真实数据尚未准备时使用代码包；若本地已准备冻结套件，加 `--bundle experiments/massive-v1` 一起打包。

本地已生成 local-smoke-v1 示例；重复演练时使用新的 --name，避免覆盖冻结输入和旧结果。

上传 ZIP、解压到服务器目录即可。建议使用 ZIP 保留冻结文件字节；Git 的换行转换可能改变数据/源码哈希。把当前完整仓库或 ZIP 复制到服务器，不要只复制 configs。Linux 示例工作目录 `/workspace/decisionbench`，按实际路径替换。

## 2. Controller 环境

```bash
cd /workspace/decisionbench
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-experiments.lock.txt
python -m pip install --no-deps -e .
python -m pytest -q
python -m scripts.collect_environment --out results/environment/server-before.json
```

锁文件来自本地 Python 3.12 验证，Linux 安装仍需复验。若对应版本没有可用 wheel，可使用 `pip install -e '.[dev,serve,classic,experiments,tokenizer]'`，通过测试后另存 `pip freeze`；不要宣称与锁文件完全一致。Torch/vLLM/CUDA 使用 GPU Worker 镜像环境，不安装进 Controller 环境。

本机 Controller 用 PowerShell 激活 `.venv\Scripts\Activate.ps1`。若 Controller 和 Worker 分离，把服务端口通过 SSH 隧道转发并保持两模型从同一 Controller 调用。

## 3. 准备真实数据和类别说明

```bash
python -m scripts.prepare_datasets --name massive --download --locale en-US --out data/normalized/massive-draft
```

或者提供已有原始文件：

```bash
python -m scripts.prepare_datasets --name massive --source /path/to/en-US.jsonl --locale en-US --out data/normalized/massive-draft
```

draft 的类别说明只是标签名称转换，不能用于正式验收。创建 `data/descriptions/reviewed.json`：内容是覆盖全部标签的 JSON 映射，例如 `{"alarm_set":"Create an alarm ...", ...}`。只能使用 train/dev 审阅，避免根据 test 修改描述。

重新生成新的冻结数据目录，不能覆盖非空目录：

```bash
python -m scripts.prepare_datasets --name massive --source data/raw/amazon-massive-dataset-1.1.tar.gz --locale en-US --descriptions data/descriptions/reviewed.json --out data/normalized/massive
```

输出 train、validation、test、checkpoint-300、catalog 和 provenance。若从 JSONL 开始，最后一条命令的 source 也改为该 JSONL。

## 4. Qwen GPU Worker

要求 Linux + NVIDIA 驱动 + Docker + NVIDIA Container Toolkit。12–16GB 是 0.6B 的选型起点；实际部署和并发测试决定能否满足配置。

当前 westd 服务器没有 Docker，使用 `scripts.launch_qwen_native` 和 `configs/qwen-native-westd.json`。原生部署在 suite 中设置 `deployment: native`，填写 `worker_environment_sha256` 和 `vllm_version`，无需 container_digest。下面的 Docker 操作适用于有容器运行时的服务器。

```bash
cp .env.example .env
```

编辑 `.env`：固定 QWEN_REVISION 为模型 commit；VLLM_IMAGE 固定为实测镜像 digest；选择 QWEN_DTYPE、QWEN_MAX_MODEL_LEN 和 QWEN_GPU_MEMORY_UTILIZATION。默认 BF16/4096/0.90，主实验 prefix cache 显式关闭。

```bash
docker compose --profile qwen config --quiet
docker compose --profile qwen up -d qwen
docker compose logs --tail 100 qwen
curl -f http://127.0.0.1:8000/v1/models
nvidia-smi
docker image inspect YOUR_VLLM_IMAGE --format '{{json .RepoDigests}}'
```

Compose 的 v0.9.2 是部署候选；`--no-enable-prefix-caching` 参数已核对该 tag 的官方 argparse 源码，但镜像、GPU兼容性及服务性能仍须服务器验证。更换 vLLM 版本后检查对应 CLI 和 thinking 请求兼容性。不要与其他 GPU 工作负载共同压测。

建议同时记录 GPU 利用率、显存和功率（独立终端运行，结束实验时停止）：

```bash
nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,power.draw --format=csv -l 5 > results/gpu-monitor.csv
```

正式测试记录 Controller CPU/调度表现；同机 CPU 竞争或明显调度迟滞时迁移 Controller 后复测。Prometheus 为可选补充，Harness 客户端指标仍是主指标。

## 5. Jev 密钥与实验模板

在服务器终端设置密钥，避免输入到代码或配置：

```bash
read -rsp 'Jev API key: ' TYPESAFE_API_KEY
export TYPESAFE_API_KEY
```

CLI 不读取 `.env`。当前 Adapter 沿用 `/v1/systemone` Choice 接口；第一次 300 条 checkpoint 验证当前账户、版本、请求契约和 usage。服务版本/价格/配额必须以实际账户为准。

编辑 `configs/experiment-suite.yaml`：

- 确认数据目录、模型、blocks。
- 填 Qwen 的 worker_gpu、model_revision、container_digest、精度、窗口与 network_path。
- 填 Jev 的 network_path 和数值 api_quota_rps，另确认 Token/s 配额。
- 先 120s 初测，之后正式版改为 ≥300s；重复 3 次。
- 若不做规模实验，将 scale.enabled=false；说明消融默认关闭。

环境信息填写后再生成套件；修改冻结套件会被哈希检查拒绝。修改参数时生成新版本，不修改已有 run。

## 6. 冻结套件并检查 Qwen 上下文

```bash
python -m decisionbench.suite prepare -c configs/experiment-suite.yaml --out experiments/massive-v1
python -m scripts.check_qwen_context --plan experiments/massive-v1/plan.json --revision MODEL_COMMIT --max-model-len 4096 --out results/context-v1.json
```

tokenizer 检查复用 Adapter 的实际 prompt，关闭 thinking，并加 64 个输出 Token 预算。只下载 tokenizer 文件，不做模型推理或 Jev 调用。检查使用与服务器相同的模型 commit；模型不同时加 `--model`。

若超限，先提高 Worker 和模板的上下文长度，再准备新的 suite 版本并重新检查；禁止静默截断目录。

## 7. 预览与分阶段运行

以下预览不发送请求：

```bash
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block checkpoint
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block main --model jev
```

预览会打印所选 job、剩余请求、预热和 API 最大请求数。运行时逐阶段、逐模型执行，先完成 checkpoint：

```bash
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block checkpoint --model qwen --execute
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block checkpoint --model jev --execute --max-api-requests 305
```

检查两模型的 summary、错误状态和 usage。语义准确率低需记录和解释，接口错误则先修复并重新冻结版本。main 完成后再 load：

```bash
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block main --model qwen --execute
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block main --model jev --execute --max-api-requests YOUR_MAIN_REQUEST_BUDGET
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block load --model qwen --execute
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block load --model jev --execute --max-api-requests 5460
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block scale --model qwen --execute
python -m decisionbench.suite run --plan experiments/massive-v1/plan.json --block scale --model jev --execute --max-api-requests 1845
```

`YOUR_MAIN_REQUEST_BUDGET` 用预览打印的数值替换。5460 对应本模板 120s/1,2,4,8RPS/3轮/每轮5条Jev预热；修改参数后必须重新预览。`--max-api-requests` 是本次调用剩余请求的上限校验，不是美元费用上限，也不覆盖此前运行或后续显式重试。

执行 load 前要求相同数据/目录下已有 main 质量基线，并达到合法成功率要求。不要在单次 --execute 中同时选未完成的 main 和 load，因为预检查时 main 尚未完成。

完成初测后编辑模板 duration_s>=300，输出新目录（例如 massive-formal-v2）。新计划需要相同冻结输入的 main 质量基线，当前代码不跨 plan 自动借用旧基线；在新版本执行 main 后再运行 load。报告分别标记 pilot 和 formal。

## 8. 中断和续跑

相同命令重跑会跳过已经完成、日志哈希一致的实验。index.json 保留各次 attempt 和 run_dir；失败/中断不会自动重复付费请求。

先检查 run_dir 的 manifest 和已发送日志，确认计费后，用相同命令加 `--retry-failed` 重跑整个未完成 job。失败尝试仍留在 attempts 和原 run 目录中。预算需要重新覆盖该次完整 job；不会从某个 sample_id 自动接着发送。

`running.lock` 防止同一套件同时执行。进程被强制杀死可能留下锁；确认对应 PID 已停止且无其他 Controller 使用该计划后，人工删除该计划目录中的 running.lock，再按上述规则重试。

## 9. 离线分析和真实价格

```bash
python -m decisionbench.analysis --plan experiments/massive-v1/plan.json --out reports/massive-v1-before-cost --plots
```

输出 runs/groups、逐类/混淆表、配对差与95%区间、错误案例、确定性 audit 和 PNG 曲线。部分完成也可分析，报告写明已完成/总计划数。分析发现缺请求、真值不一致、输入/日志篡改或指标不符会报错。

复制 pricing-real.template.json 为自己的真实价格文件，填实际价格、来源和日期；同币种。模板中的 null 有意不能直接运行。

```bash
python -m decisionbench.cost_analysis --plan experiments/massive-v1/plan.json --pricing configs/pricing-real.json --out reports/massive-v1-cost
python -m decisionbench.analysis --plan experiments/massive-v1/plan.json --out reports/massive-v1-priced --plots
python -m scripts.aggregate --out results/comparison-priced.csv
```

月度对照另指定已独立验收的容量，示例中的占位值必须替换，不能使用任意峰值：

```bash
python -m decisionbench.cost_analysis --plan experiments/massive-v1/plan.json --pricing configs/pricing-real.json --scenarios configs/tco-scenarios.json --max-slo-qps VALIDATED_QWEN_QPS --out reports/massive-v1-monthly
```

月度脚本不自动证明容量或 API 峰值配额；assumptions.json 记录这些边界。API usage 缺失则费用是下界。不要把测试服务器整段租赁账单与“测量窗口费用”混为一项。

报告以正确有效请求成本、常驻 TCO 和适用流量解释；Jev/Qwen Token 计数不同，不能仅凭 Token 数比较成本。

## 10. 拉回结果

保存 results、reports、冻结 experiments 套件、实际价格及环境记录。密钥不放入结果压缩包。将结果拉回本地后，可在项目根目录执行同样的 analysis/cost 命令复算；冻结输入/代码必须保持字节一致。

正式报告前核对：真实数据、模型版本、同目录、完整状态、重复次数、合成标记、价格来源、网络条件、SLO、稳态证据及人工错误分析。
