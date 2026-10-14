# 新服务器准备记录（2026-10-14）

用户授权上传全部代码并做好实验准备。本轮安装环境、下载模型和原始数据、运行软件演练与部署验证；正式模型评测和 Jev 付费请求尚未执行。

服务器：`ssh -p 16259 root@connect.westd.seetacloud.com`。项目路径：`/root/autodl-tmp/decisionbench`。此前 bjb2 服务器交接记录是历史记录，不代表当前机器。

## 版本和文件

原始代码基线为 `14a497e925acacc85d06f6a4cbb57b34d5ab3aaa`，74 个受管理文件。通过 Git bundle 上传全部提交历史，服务器 `git fsck` 通过。原始传输包 SHA-256 为 `4b6baf689562281c48942184efc6d07c3905d6bc73dc506186ef68ef76fc400d`。

本轮增加原生 vLLM 启动、Qwen 发布方镜像下载、草稿数据上下文检查和原生环境验收，最终同步版本见 `results/preparation/upload-receipt.json`。源代码、配置、测试和文档纳入 Git；模型、数据、环境和运行日志按既有忽略规则保存，密钥不写入文件。

## 环境与下载

- NVIDIA RTX 5090，32607 MiB，驱动 595.71.05。
- Python 3.12.3，基础解释器 `/root/miniconda3/bin/python`。
- Controller：项目 `.venv`；实际依赖另存 `results/preparation/controller-requirements.lock.txt`，没有宣称复用本地锁文件。
- Worker：`/root/autodl-tmp/decisionbench-worker-cu128`，复用基础 Torch 2.8.0+cu128 / torchvision 0.23.0+cu128。候选 vLLM 0.11.0 与 Torch 版本匹配，最终部署状态见本记录的验证结果。
- 没有 Docker，使用原生隔离虚拟环境，不填写虚构容器 digest。实验记录以 Worker 依赖哈希和 vLLM 版本替代。
- Aliyun 源失败或返回 403；使用 `https://pypi.tuna.tsinghua.edu.cn/simple`，安装失败和中止记录保留。
- Hugging Face 直连不可达，使用 Qwen 官方 ModelScope 镜像；每个文件固定 Revision、Size、SHA-256。整体快照 ID 为 `modelscope-manifest-sha256:f7cb819c0cbceca9170480b859dc0a593a11db4e976fba9104884828a020f993`，不是 HF commit。
- Qwen 权重 SHA-256：`f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`。全部文件校验通过，清单在 `models/qwen3-0.6b/download-manifest.json`。
- MASSIVE 使用 Amazon 发布方 1.1 原始压缩包，仅读取 en-US JSONL，不执行远程数据脚本。归一化草稿保留 `descriptions_reviewed=false`。

## 操作入口

```bash
cd /root/autodl-tmp/decisionbench
# 默认预览；每次使用新的输出和日志文件名。
.venv/bin/python -m scripts.launch_qwen_native --config configs/qwen-native-westd.json --out results/preparation/qwen-preview.json --log results/preparation/qwen-worker.log
# --start 才会启动本机服务。启动脚本重新检查模型全部文件哈希。
.venv/bin/python -m scripts.launch_qwen_native --config configs/qwen-native-westd.json --out results/preparation/qwen-launch.json --log results/preparation/qwen-worker.log --start
# 草稿检查不推理、不调用 Jev；正式说明审阅后仍需检查最终冻结套件。
.venv/bin/python -m scripts.check_dataset_context --dataset-dir data/normalized/massive-draft --model-dir models/qwen3-0.6b --out results/preparation/draft-context.json
```

## 正式实验前的待办

1. 审阅全部 60 类的英文说明，只参考 train/dev；生成新的冻结数据目录，不覆盖草稿。
2. 确认 Jev 实际账户模型版本、RPS/Token 配额和本阶段请求预算；通过环境变量注入密钥。
3. 补实际 API 单价、服务器租赁单价及来源日期，才能做真实成本/TCO。
4. 冻结正式 suite，检查全部启用目录的输入长度，先 checkpoint，再 main、load、scale。120 秒负载仅是初测，正式容量实验使用新计划且至少 300 秒。

准备阶段的 Mock 和合成启动测试不能进入真实实验结论。
