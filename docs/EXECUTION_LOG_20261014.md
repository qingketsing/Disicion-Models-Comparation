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
