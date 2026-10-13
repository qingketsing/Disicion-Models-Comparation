# 开发清单

## P0：当前起点

- [x] 独立目录与 Python 包，配置、fixture 和本机运行入口。
- [x] 真值隔离的统一 Adapter；Jev/Qwen/分类服务请求契约。
- [x] Quality、开放环 Load；超时/非法输出/过载不丢弃。
- [x] 请求日志、冻结输入与源码、Manifest、质量和性能指标。
- [x] 实例/API 离线成本重算、月度常驻容量/TCO、CSV 汇总与可选 Parquet。
- [x] TF-IDF/SVM 训练与 HTTP 服务；BERT 训练/Serving 代码入口。
- [x] Compose profiles 与 Prometheus 基础配置。
- [x] 初步动态目录回放。
- [ ] MASSIVE 真实数据准备、类别说明审阅、冻结 300 条验证样本。
- [ ] Jev 实际 API、Qwen 4090 与训练后 BERT 端到端验证。
- [ ] Worker 容器构建、镜像 digest、模型 commit 与环境记录。
- [ ] Checkpoint 1 五项验收。

## P1：正式实验

2026-10-13 已补齐实验编排工具：冻结套件、无请求预览、Jev 请求预算、断点续跑、10/30/60 嵌套类别实验、可选说明消融、配对准确率区间、独立质量复算、真实价格批量重算、CSV/PNG 和上传包。见 `refine-logs/EXPERIMENT_PLAN.md` 与 `docs/REMOTE_EXPERIMENTS.md`。这些工具通过本地 Mock/fixture 验证；下面的真实实验、稳态容量和 GPU 验证仍待完成。

- 质量：完整 MASSIVE/BANKING77 测试集，CLINC150 已知/OOS 分组，错误分析。
- 性能：固定 RPS 扫描、Poisson 到达、120 秒初测后扩展稳态，3–5 次重复与置信区间。
- 对照：用 `vllm bench serve` 交叉验证 Qwen 内部与客户端指标。
- 计量：真实发票、API 用量对账、统一汇率时间、成本容量曲线及 API/实例盈亏平衡。
- 模型：BGE、BERT CPU/GPU 对照、INT8、置信度校准与拒识阈值。
- 动态：更新事件、重训/热加载耗时、new/old class 分组、精度恢复与旧类退化。
- Infra：镜像依赖锁定、Worker 元数据自动抓取、Prometheus 快照与 Grafana 图表。
- Harness：高 RPS 异步日志落盘、流式聚合、测量客户端资源占用与取消时所有已准入请求的最终状态。

## P2：报告与扩展

- Prefix Cache 与其他缓存消融；分开说明缓存输入分布。
- 技术报告生成与独立复算工具；长期可扩展 Adapter 注册机制。
- 有单机结果解释不了的系统行为时再评估多机部署。

建议先完成 Checkpoint 1，之后按方案的 14 天路线推进。未验证项不能在报告中写成已接通或已测得性能。
