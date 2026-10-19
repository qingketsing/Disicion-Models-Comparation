# BERT RTX 5090 节点测试报告

执行时间：2026-10-18 至 2026-10-19（北京时间）。本轮完成环境配置、GPU 冒烟测试、三种子训练、九轮完整质量评测和两档负载初测。

代码为 main 提交 `820625e53d082219f571dee64bd12a46c478f24c`。训练与评测核心源码未修改；节点执行编排脚本随证据保存。

## 环境与协议

Worker：RTX 5090（32607 MiB），驱动 595.71.05；Xeon Platinum 8470Q，容器 CPU 时间配额相当于 25 个逻辑核、内存上限 120 GiB。Python 3.12.3、PyTorch 2.9.1+cu128、Transformers 4.57.1、datasets 4.3.0、accelerate 1.11.0。依赖检查、实际 CUDA 前向/反向/优化器更新、端到端 smoke 和 42 项测试均通过。

基座：google-bert/bert-base-uncased，固定 revision `86b5e0934494bd15c9632b12f734a8a67f723594`。通过镜像下载的五个文件已与 Hugging Face 官方 Git blob/LFS 哈希核对。

MASSIVE 1.1 en-US 保留原生 train/dev/test（11514 / 2033 / 2974），按要求不去重，保留 11 条 train/dev 重复文本。FP32、eager attention、batch 16、5 epochs、AdamW、LR 2e-5、weight decay 0.01、warmup 0.1、max_length 128、seed 42/43/44；关闭 TF32。train/dev/test 最大 token 长度分别为 39/31/64，均无截断。

原生分区另有 21 条 train/test、5 条 dev/test 共享文本，均按原协议保留，跨分区 sample_id 无重复；因此本报告属于原生分区结果，不能解释为文本完全隔离的泛化估计。重叠审计见[发布核验回执](evidence/publication-validation.json)。

只按 dev 全 60 类 Macro-F1 选 checkpoint，再按 dev Macro-F1、Accuracy、较小 seed 选部署模型。test 中有样本的类别为 59 个，Macro-F1 始终按冻结的 60 类计算，无支持类别 cooking_query 记 0，与历史结果口径一致。

## 质量结果

| 训练种子 | 最佳 epoch | dev Macro-F1 | test 正确数 / 2974 | test Accuracy | test Macro-F1 | 训练秒数 |
|---|---:|---:|---:|---:|---:|---:|
| 42 | 4 | 83.54% | 2641 | 88.80% | 81.84% | 292.0 |
| 43 | 5 | 83.10% | 2659 | 89.41% | 82.25% | 293.6 |
| 44 | 5 | 81.98% | 2651 | 89.14% | 82.77% | 295.7 |

三个训练种子的均值 ± 样本标准差：Accuracy **89.12% ± 0.30 个百分点**；Macro-F1 **82.29% ± 0.47 个百分点**。

部署选择为 seed 42，模型版本 `bert:faad5c920150b6d1`。三种子训练总计 881.4 秒（14.69 分钟），最大 PyTorch 分配显存 2.06 GiB。

每个种子在完整 test 上测三轮，同一种子的逐样本预测差异均为 0。九轮共 26766 次测量请求，成功率均为 100%；仍然只有 2974 个独立测试样本，重复调用未合并为 3N 或 9N。

### 与历史 Qwen / Jev 对照

相同样本 ID、文本和真值已逐项核对。下表历史结果是原三轮的均值，没有重新调用 Qwen / Jev；BERT 使用本次监督微调，训练方式与历史模型不同。

| 模型 / 汇总方式 | Accuracy | Macro-F1（60 类） |
|---|---:|---:|
| qwen 历史三轮均值 | 45.93% | 48.72% |
| jev 历史三轮均值 | 86.12% | 83.85% |
| BERT 三训练种子均值 | 89.12% | 82.29% |
| BERT 部署模型 seed 42 | 88.80% | 81.84% |

BERT 的 Accuracy 更高，Macro-F1 低于 Jev；不能据此概括为所有类别全面领先。部署模型首轮与各历史轮次的配对 Accuracy 差值如下，bootstrap 以 2974 个唯一样本为单位，2000 次抽样、seed 42；该区间不包含训练种子不确定性。

| 历史对手 | 对手轮次 | BERT Accuracy 差值（百分点） | 95% 配对 bootstrap CI（百分点） |
|---|---:|---:|---:|
| qwen | 1 | +42.87 | [+40.99, +44.69] |
| jev | 1 | +2.76 | [+1.58, +3.93] |
| jev | 2 | +2.66 | [+1.48, +3.80] |
| jev | 3 | +2.62 | [+1.45, +3.80] |

小类是当前 Macro-F1 缺口的重要来源。下列类别在部署模型 seed 42 的测试中召回率为 0；测试样本数量少，作为后续训练集频次加权消融的定位线索。

| 类别 | train 样本数 | test 样本数 | BERT F1 | Jev 三轮平均 F1 |
|---|---:|---:|---:|---:|
| music_dislikeness | 14 | 4 | 0.00% | 100.00% |
| audio_volume_other | 18 | 6 | 0.00% | 69.84% |
| iot_hue_lighton | 22 | 3 | 0.00% | 46.30% |

## 独立 Controller 负载初测

Windows 11 / Ryzen 9 8940HX Controller，经 SSH 隧道访问单进程 CUDA Worker；请求 1 ms Windows timer。负载期间无训练、模型打包或传输任务。每档 120 秒 × 3 轮，warmup 50、轮间冷却 30 秒、并发上限 128；门槛为 p95 ≤ 500ms、成功率 ≥ 99%、最大调度迟滞 ≤ 20ms，并逐 60 秒窗口复算。

| RPS | 三轮请求总数 | 成功率范围 | p95 范围（ms） | 最大调度迟滞（ms） | 整轮及所有窗口通过轮数 |
|---:|---:|---:|---:|---:|---:|
| 32 | 11520 | 100.00%–100.00% | 101.5–109.7 | 17.4 | 3/3 |
| 64 | 23040 | 94.14%–95.78% | 2154.4–2213.5 | 21.2 | 0/3 |

负载阶段失败类型及次数：`client_overload`：1160，`network_error`：1。并发上限拒绝计入成功率分母。

这些是 pilot 结果，尚未执行 300 秒 × 3 轮的正式容量确认，不能把最高通过档位称为最大容量。延迟包含此次 SSH 网络路径，不能与同机 loopback 延迟直接混用。没有获得实际节点价格，因此没有填入成本或使用示例价格。

## 证据与恢复

质量阶段曾发生一次模型切换就绪检查过早：seed 43 在发出测试请求前连接失败。修复编排脚本为核对模型版本和 seed 后才继续，原失败日志保留，已完成的 seed 42 三轮没有重跑。训练和评测核心代码未变更。

最终权重与各自最佳 checkpoint 的文件哈希相同。Worker 备份已下载到本地，归档 SHA256 `a72221fb45d39ef0ee1f026e162f05b3cf011d9d3c2c152c524efcb2a37cfcdc`，665 个清单内文件通过逐文件校验（归档另含清单自身，共 666 个文件），三个最终模型通过元数据哈希校验。优化器 checkpoint 留在 Worker；环境、归一化数据、冻结计划、训练日志和原始请求记录均已保留。

Controller 归档 SHA256 `d71dcf9d49db3b40ee42143beebdc8cb66886f5b4f309523f2bba8545ae4b375`。两份归档及最终权重已在执行机和本地保存；归档未上传到 GitHub，因此仅凭本仓库可以复算质量与配对结果，完整延迟重放需要原始归档。测试进程已停止。

MASSIVE 数据来自 Amazon Science MASSIVE 1.1，遵循 CC BY 4.0；沿用仓库已有公开测试样本 ID 和标签。本目录的紧凑预测表省略重复文本，每个 seed 保留一列预测；三轮推理完全一致的核对结果见质量汇总。类别说明沿用 PR #2 的 AI 审阅映射，不代表人工审阅。

## 已发布证据

- [逐轮指标](analysis/runs.csv)、[60 秒窗口](analysis/steady-60s-windows.csv)、[配对比较](analysis/paired-comparisons.csv)
- [2974 个唯一样本的三种子预测](sample-predictions.csv)、[类别差异](per-class-comparison.csv)、[质量汇总](quality-summary.json)
- [冻结计划](frozen-plan/plan.json)、[模型选择](training/selection.json)、[环境验证](evidence/setup/environment.json)
- [原始输入哈希审计](analysis/audit.json)、[归档验证回执](evidence/local-verification.json)、[发布清单](publication-manifest.json)
- [复算与复现说明](REPRODUCE.md)

`runs.csv` 的 `duration_s`、`offered_rps` 是配置字段，仅对 load 模式表示实际到达计划；quality 会顺序执行完整测试集，不受其中的占位值 10 秒 / 1 RPS 限制。`passed` / `windows_passed` 是负载 SLO 条件，不用于判断 quality 是否成功。质量吞吐仅反映同机 loopback，独立 Controller 的负载数据见 pilot 六轮。
