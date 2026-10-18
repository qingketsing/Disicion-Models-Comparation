# Qwen 与 Jev v4 实验结果交付

实验实际日期：2026-10-14/15。此分支整理已完成实验的报告、离线结果、图表和证据索引，供后续提交审阅使用。没有启动新实验或修改冻结结果。

本次面向上游的提交以原作者 `main` 为基线，只包含最终结果材料和可视化脚本，合并为一个 commit；不包含实验过程的核心实现、部署配置及中间提交。原始证据依赖封存源码归档，不能将原项目当前源码当作当时执行源码。

## 先看图解

[完整五组实验图解](VISUAL_EXPERIMENT_RESULTS_20261015.md)展示分类质量、目录规模、正式判据、初测状态矩阵与每分钟稳态。图均读取原CSV，原封存报告和数据保持不变。

![分类准确率与逐轮配对差值](../reports/experiment-results-20261015/visualizations/01-quality-paired.png)

![正式负载为什么没通过](../reports/experiment-results-20261015/visualizations/03-formal-thresholds.png)

![每分钟稳态通过情况](../reports/experiment-results-20261015/visualizations/05-formal-minute-windows.png)

## 报告入口

- [Qwen 最终报告](QWEN_EXPERIMENT_REPORT_20261014.md)：40 个独立完成 run，远程 RTX 5090 / vLLM / Qwen3-0.6B BF16。
- [Jev 最终报告](JEV_EXPERIMENT_REPORT_20261014.md)：两份计划去重 27 个完成 run，Windows Controller 经本地代理调用 Jev-1.13.0 API。
- [双方主质量配对比较](QWEN_JEV_COMPARISON_20261015.md)：同样本、同有序目录，逐轮配对 bootstrap。
- [Qwen 错误审阅](QWEN_ERROR_REVIEW_20261014.md)、[Jev 错误审阅](JEV_ERROR_REVIEW_20261014.md)：均为 AI 定性审阅，非人工评价，不据此修改 GT。
- [完整性审计](../EXPERIMENT_AUDIT.md)：保留同系列代理的 provisional 结论与审阅截止状态；最终交付存在性提示由独立确定性验收闭合。

Qwen 原报告中“Jev 尚未完成”的文字反映其 2026-10-14 截止时点，封存字节保持原状；最新 Jev 状态以本页、配对比较和 Jev 最终报告为准。

## 主要结果

| 指标 | Qwen v4 | Jev v4 |
| --- | ---: | ---: |
| 主质量三轮平均 Accuracy | 45.9314% | 86.1242% |
| full60 Macro-F1，各轮 | .487239 / .487239 / .487239 | .837008 / .839251 / .839360 |
| supported59 Macro-F1，各轮 | .495498 / .495498 / .495498 | .851195 / .853475 / .853586 |
| 10类目录平均 Accuracy | 79.3333% | 97.1667% |
| 30类目录平均 Accuracy | 63.5000% | 94.0000% |
| 60类目录平均 Accuracy | 52.5000% | 90.5000% |
| 正式技术容量 | 最高已测通过点32 RPS | 当前路径无已确认容量 |
| 完成 run / 测量 / 预热 | 40 / 143142 / 2000 | 27 / 17022 / 135 |
| 完成实验测量费用 | 4.209604 CNY，按租用时段估算 | 1.328246850 USD，下界 |

主质量每轮为相同2974个唯一样本，不将三轮当作8922个独立样本。test真值支持59/60类，cooking_query无真值。规模实验每种子固定200条、10个anchor真值类，嵌套增加目录干扰类，不是完整test替代。主质量平均差约40.19个百分点只适用于本次固定数据、目录与部署。

容量采用500ms p95 / .99成功率 / 20ms最大调度迟滞，正式300秒三轮及每个60秒窗口均需通过。Jev正式1RPS三轮900条测量最终全成功，但p95为3.38–3.83秒、迟滞也超限；不能把null解释成API容量为0或硬件极限。双方网络、服务和重试条件不同。

Jev完成v4含预热1.337850696USD；全部已记录历史/中断/预热/探针2.049680304USD下界。未知失败usage未补算；无供应商账单、无汇率换算，月度业务TCO未评估。

## 本分支可直接读取的数据

| 路径 | 内容 |
| --- | --- |
| [Qwen最终结果](../reports/qwen-v4-final-20261014/) | runs/groups、逐类F1、混淆矩阵、窗口、规模配对、错误与图表 |
| [Jev最终结果](../reports/jev-v4-final-20261015/) | 上述指标，加逐次网络尝试、恢复请求、历史费用、发布者来源验证 |
| [主质量配对](../reports/qwen-jev-main-paired-20261015/) | 逐轮配对区间、逐样本结果、重复差异及输入核验 |
| [Jev错误案例数据](../reports/jev-error-review-20261015/) | 40例原文、GT、预测与选样证据 |
| [证据索引](../reports/experiment-results-20261015/) | 冻结plan副本、归档回执、最终验收回执和本次提交材料SHA256清单 |

报告器原始产物按原字节纳入Git，`.gitattributes`禁用这些文件的换行转换；结果内容未重新计算或改写。表内run路径、原始请求哈希和source快照路径为原现场定位信息，原始目录不随此次结果提交复制。

## 原始证据与复算范围

此分支包含可审阅的派生结果和哈希索引。完整请求日志、冻结数据/source快照、发布者原始包、历史中断和完整审阅轨迹保留在本地SHA256归档，没有提交大型压缩包、模型权重、虚拟环境、凭据或临时`.aris`目录。仅凭此Git检出不能从原始请求重跑全部离线分析；需要配套原始归档恢复原相对路径。它也不包含已封存实验的运行凭据。

| 本地归档 | SHA256 |
| --- | --- |
| `dist/qwen-v4-final-capacity-snapshot.tar.gz` | `a799169fce4f501f20924283236def65ab6200085027f0d16e584a5cb75e47d0` |
| `dist/jev-v4-final-evidence-snapshot.tar.gz` | `511a7401a752ea06483997c9efad93e0b36adf684a86a26c46f9c9443f5bb91d` |
| `dist/jev-v4-source-provenance-snapshot.tar.gz` | `9d81c77571c671b74212fd035d592c1c9881974c39088940f41f3d8fd15d7ca7` |
| `dist/jev-v4-final-deliverables-snapshot.tar.gz` | `b7769df59a79b725d4d0051baa540573005158cb680485214ed86535e166ee14` |

归档内的Git SHA是实验封存时点；此次整理分支基于封存提交并新增结果材料，不改旧归档或历史回执。审计完整请求/响应轨迹仅在本地交付归档保留，不提交Git。数据来源为Amazon MASSIVE 1.1，en-US，CC BY 4.0；原包SHA与实验前provenance一致，原生分区文本/intent/ID已重建比对通过。
