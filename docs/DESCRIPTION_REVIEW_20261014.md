# MASSIVE 类别说明 v1

说明由 Codex 编写和审阅，依据原始 train 分区每类固定 seed=42 的最多 8 个例子及类别名；没有依据测试集预测修改说明。不声称人工审阅。用户授权代理执行实验，本轮将 AI 审阅状态明确写入 provenance 和报告。

映射覆盖 60 类，英文说明、按标签字典序，共用于两个模型。原始标签和数据划分不改动。cooking_query 在训练集仅 4 个例子，和 cooking_recipe 有显著语义重叠；general_quirky 边界宽泛。若数据标签存在噪声，仍按原始真值计分。所有模型使用相同描述，冻结后不因测试错误调优。

运行位置按用户最新要求：Qwen Controller/Worker 在 westd 服务器；Jev Controller 在本地 Windows，HTTP 代理 `127.0.0.1:7897`。服务器不再运行 Jev，请求不再经过 SSH 远程转发。这是实际部署端到端比较，质量可按样本配对，延迟差异同时受 Controller 位置及网络影响。
