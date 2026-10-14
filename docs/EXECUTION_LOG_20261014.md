# 实验执行日志：2026-10-14

时间口径：UTC；服务器为 `connect.westd.seetacloud.com:16259`，项目目录为 `/root/autodl-tmp/decisionbench`。

## 本轮授权和边界

用户授权执行 Qwen3-0.6B 与 Jev 的既定对比实验，要求记录日志、使用 Git 管理版本、修复可判断的问题并在结束后生成报告。当前阶段只完成实验前验证；由于 Jev 服务按服务器出口区域拒绝访问，正式质量、负载、规模实验均未启动。

## 成本参数

- Qwen Worker：RTX 5090，用户提供的按量价格为 **2.78 CNY/小时**。
- Jev：用户确认使用官方价格。官方模型页面（访问日期 2026-10-14）列出 Jev 1.13 / `jev-1.13.0` 输入 **42 USD / billion tokens = 0.042 USD / million input tokens**，输出 Token 免费；公开限额为 80 requests/s、100,000 tokens/s，页面同时说明限额可能动态调整。
- API 与 GPU 当前不是同一币种。没有用户确认的汇率日期前，不生成混合币种的虚假总成本；完成实验后按统一汇率日期换算。

## 运行记录

1. Qwen 原生 vLLM 已在 RTX 5090 上完成部署验证：vLLM 0.11.0、Transformers 4.57.6、BF16、4096 上下文、prefix cache 关闭。健康接口和模型列表正常，一条合成 QwenAdapter 请求返回合法 `alarm_set`，该请求不计入实验结果。
2. Qwen 合成验证后服务已停止，GPU 显存恢复空闲。
3. MASSIVE 1.1 原始压缩包和 en-US 草稿数据已完成哈希核验；训练集 11514、验证集 2033、测试集 2974、checkpoint 300、60 个类别。类别说明仍是标签名占位文本，`descriptions_reviewed=false`，因此不能生成正式 suite。
4. Jev 探针只先请求 `GET https://api.typesafe.ai/v1/models`，服务器返回 HTTP 451：`Typesafe is not available in your region.`，Cloudflare 响应。探针在模型推理 POST 前停止，记录 `evaluation_requests=0`；没有正式 Jev 请求、质量请求或计费请求。
5. 依据 HTTP 451 的明确原因，未重试 Jev，也未启动需要两模型比较的正式实验。继续从同一出口重试不能解决区域访问策略。

## 证据位置

- Jev 探针记录：服务器 `results/execution-20261014/jev-probe-1.json`。
- Jev 阻断请求头和压缩备份：服务器 `/root/autodl-tmp/decisionbench-transfer-20261014/execution-jev-blocked.tar.gz`，SHA-256 `d0da5de9106c7d05a0e95918f7359425cf6573d020e43559ceeb397c85f8f633`。
- Qwen、数据、依赖、测试和上传回执：服务器 `results/preparation/` 与 `results/preparation/upload-receipt.json`。
- Jev 探针代码：`scripts/probe_jev.py`。密钥只用于运行时环境，未写入源码、配置或实验日志。

## 当前状态和恢复条件

状态为 **BLOCKED_EXTERNAL_REGION**，不是模型质量失败，也不是预算耗尽。恢复需要一个能访问 `api.typesafe.ai` 的服务器出口、用户提供的代理/网络方案，或用户明确批准将本轮改为 Qwen 单模型实验。恢复后必须重新做一次小额模型列表/单样本契约验证，再执行 checkpoint；不直接从失败探针进入批量请求。

## 本机代理验证（2026-10-14，Asia/Shanghai）

用户指定使用 SSH 远程转发到本机代理。已确认 Clash/Mihomo 本机端口为 `127.0.0.1:7897`；显式经该代理访问 Jev 模型列表返回 HTTP 403，错误类型为 authentication_error、原因是本次未携带密钥，没有区域 451，未发起推理请求。创建后台 SSH 转发进程的命令被自动审批检查拒绝（`blocked by policy`，没有详细原因），隧道未建立。手动启动命令及验证步骤见 `SSH_PROXY_WESTD.md`。下一步需建立隧道，再验证服务器代理及认证，正式实验尚未恢复。

## 恢复、部署调整和 v1 checkpoint

用户自行建立转发后，服务器代理认证探针成功。随后用户明确调整部署：Qwen 和 Controller 在 westd 服务器运行；Jev 和 Controller 在 Windows 本机经 `127.0.0.1:7897` HTTP 代理运行。两端认证/契约验证成功，区域阻断解除；远程 Jev 临时凭据已删除。

使用冻结的 MASSIVE en-US 数据和 AI 审阅的 60 类说明（非人工审阅，见 `DESCRIPTION_REVIEW_20261014.md`），v1 计划 SHA-256 为 `37985034ad4534587645e133a3dd755b478311128a2080aa9ab54151d27663df`。2026-10-14 07:07 UTC 两端分别开始 checkpoint，均完成 300 条测量请求。

- Qwen 无枚举约束：accuracy=0.530000，success_rate=0.980000，6 条目录外标签。输出未截断，无网络失败；保留为真实无约束结果，不能后处理映射为合法标签。
- Jev Choice：accuracy=0.873333，success_rate=1.000000。
- Qwen 结果目录：`results/20261014T070731Z-checkpoint-full-seed42-rep1-qwen-abf24e29`（服务器）；Jev：`results/20261014T070732Z-checkpoint-full-seed42-rep1-jev-3c751fa6`（本机）。
- Windows/Linux Git 检出行尾导致源文件字节哈希差异；v1 在首条实验请求前发现并停止。上传本机原始源字节后校验通过。服务端工作区行尾差异已明确记录，不宣称 Git 干净。

## 用户批准的 v2 方法调整

用户选择“增加枚举约束，新版本重跑”。在 Qwen 请求中加入 vLLM `response_format=json_schema`，`label` 的 enum 严格等于当前实验目录；temperature=0、max_tokens=64、禁用 thinking、数据、说明、模型权重和 Jev Choice 均保持原协议。适配器仍校验返回值，不能把非法输出伪装为成功。默认配置保留原无约束路径。

配置：`configs/experiment-suite-split-v2.yaml`。新增请求契约测试验证当前目录枚举和服务端非法返回的处理；44 项测试和 Ruff 检查通过。v1 原始结果和冻结计划保留；v2 必须使用新计划目录和新运行目录，先验证真实 vLLM 结构化输出再重跑 checkpoint。

## v2 checkpoint 与数值边界修复 v3

v2 计划 SHA-256：`9ede63afe8bafa266813d01d580e692ff51cc5391fbd0271eadfda09ebe487d9`；代码版本 `ed27337`。两端源字节同步及 11 组上下文检查通过，真实 vLLM 枚举探针返回合法 `alarm_set`（独立合成请求，不计入 checkpoint）。

- Qwen：`results/20261014T072215Z-checkpoint-full-seed42-rep1-qwen-c62cf027`；300/300 合法，Accuracy=0.5333333333。
- Jev：`results/20261014T072225Z-checkpoint-full-seed42-rep1-jev-3e4eb4fd`；299/300 合法，Accuracy=0.8733333333。独立复算与日志完整性检查通过。
- 唯一非法条为 `massive-en-US-validation-5755`，预测标签合法、60 类概率齐全；概率和为 0.99，计算偏差 `0.010000000000000009` 被旧校验器误判为超过 0.01。该预测本身与真值不符，数值修复不提高该样本 Accuracy。
- 例行修复：使用 `math.fsum` 求和，在既有 1% 容差边界加入 1e-12 的浮点比较精度，保留 0.989/1.011 等越界拒绝。49 项测试和 Ruff 通过。
- v2 的失败状态不改写。冻结 `configs/experiment-suite-split-v3.yaml`，在相同枚举解码、数据、模型、价格及部署条件下两端重跑 checkpoint；主实验只使用通过检查的新版本。
