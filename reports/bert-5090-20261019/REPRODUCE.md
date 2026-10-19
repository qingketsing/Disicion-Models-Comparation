# BERT RTX 5090 结果复算与复现

本目录记录源码提交 `820625e53d082219f571dee64bd12a46c478f24c` 的一次实测。详细结论见 [REPORT.md](REPORT.md)。报告发布没有改动训练或评测核心逻辑。

## 仅使用仓库复算

在项目根目录、已安装 Controller 依赖及 NumPy 的 Python 环境运行：

```bash
python reports/bert-5090-20261019/verify_publication.py
```

校验发布文件的 SHA256，重新计算三个训练种子的 Accuracy、全 60 类 Macro-F1、均值和样本标准差；核对历史样本 ID / 真值，复算历史 Qwen / Jev 指标与 54 行配对 bootstrap 区间；检查逐轮、窗口和已保存复算摘要之间的一致性。原始请求在归档中时可再运行 `--raw`，逐文件核验 15 轮原始输入哈希，并与九轮质量预测逐条核对。

`sample-predictions.csv` 按原始测试顺序保存 2974 个唯一样本，每个训练 seed 一列预测。九轮响应均为 `ok`，同一种子的三轮逐样本预测相同，因此无需复制三遍；三个 seed 的结果不能当作 8922 个独立样本。文本沿用 `reports/qwen-jev-main-paired-20261015/paired-sample-outcomes.csv`，原始分析已核对 ID、文本与真值完全一致。配对 bootstrap 固定 2000 次、seed 42，区间仅反映测试样本不确定性。

`publication-manifest.json` 记录复制来源、来源文件哈希、发布文件哈希及转换规则。原始冻结计划、训练元数据和归档回执保持原字节；统计表及审计中的 Controller 绝对路径改为项目相对路径，指标与输入哈希未变。`training/*/metadata.json` 中的 `artifact_files` 指向原模型目录内文件，而非本发布目录。

## 原始证据与完整离线分析

两份归档已在本地与执行节点保存，但未发布到 GitHub。持有归档时先核对对应 `evidence/*.sha256.json` 的哈希和大小，再在实验仓库中解压。Worker 归档包含数据、冻结计划、三份最终模型、训练记录及质量原始请求；Controller 归档包含六轮负载原始请求及分析记录。优化器 checkpoint 仅保留在执行节点。

```bash
sha256sum dist/bert-5090-20261018-worker.tar
sha256sum dist/bert-5090-20261018-controller.tar.gz
tar -xf dist/bert-5090-20261018-worker.tar
tar -xzf dist/bert-5090-20261018-controller.tar.gz
python reports/bert-5090-20261019/verify_publication.py --raw
python -m scripts.analyze_bert \
  --index results/massive-bert-native-v1-quality-20261018T154916107912Z/index.json \
  --index results/massive-bert-native-v1-quality-20261018T155417633132Z/index.json \
  --index results/massive-bert-native-v1-quality-20261018T155813909767Z/index.json \
  --index results/massive-bert-native-v1-pilot-20261018T160300777242Z/index.json \
  --baseline reports/qwen-jev-main-paired-20261015/paired-sample-outcomes.csv \
  --out results/bert-5090-reanalysis-001
```

使用尚不存在的分析输出目录。延迟百分位、调度迟滞及 60 秒窗口需要原始请求才能独立重算；紧凑质量预测表不包含这些时间信息。当前 `capacity_points` 为空，因为未执行 formal 300 秒 × 3 轮确认。

## 在 GPU 节点重跑

环境安装、准备新计划、训练、恢复和服务启动遵循 [BERT_RUNBOOK.md](../../docs/BERT_RUNBOOK.md)。复现本轮使用 `frozen-plan/plan.json` 中的参数及固定基座 revision `86b5e0934494bd15c9632b12f734a8a67f723594`；新实验设置新的 name / data_dir / model_dir / 输出目录，不能覆盖本轮证据。使用镜像时保持模型 ID 与 revision，并核对 `evidence/base-model-origin.json` 的官方文件哈希。

本轮使用 RTX 5090、驱动 595.71.05、Python 3.12.3、PyTorch 2.9.1+cu128，完整依赖见 `evidence/setup/pip-freeze.txt`。先完成环境自检、CUDA smoke 和 pytest，再开始正式训练。原生 train/dev/test 保留、不去重，文本重叠只警告；源代码与数据哈希由计划验证。

质量评测分别启动 seed 42/43/44，每个 seed 三轮完整 test；本轮质量请求在 Worker 同机 loopback 上执行。切换模型时先等待旧进程退出，再等待新服务的模型版本与 seed 符合目标。部署 seed 42 由 dev 指标选定。负载在独立 Windows Controller 上执行，经 SSH 隧道到 Worker，本轮只测了计划候选集中的 32 和 64 RPS：

```bash
python reports/bert-5090-20261019/run_controller.py evaluate \
  --plan experiments/bert-native-v1/plan.json --stage pilot \
  --rps 32 64 --base-url http://127.0.0.1:18001 \
  --network-note "independent-Windows-controller-to-RTX5090-over-SSH;timerPeriodMs=1;single-worker-fp32"
```

该包装器在 Windows 请求 1 ms timer，并在退出时恢复；训练和评测 CLI 与原实现相同。Linux Controller 无需该 timer，请使用自身环境描述。确保隧道已就绪，负载期间不并行训练或传输大文件；如重跑产生新 index，应保留新 run 与本次报告的区别。

MASSIVE 1.1：Amazon Science，CC BY 4.0。数据出处、原包及归一化文件哈希见 `data-provenance/provenance.json`。类别说明沿用 PR #2 的 AI 审阅版本。
