# 服务器代码交接记录：2026-10-14

日期与时间口径：Asia/Shanghai。

## 本轮范围

用户将当前任务限定为上传全部代码。仅传输仓库、恢复 Git 历史和校验文件；不安装依赖、不启动模型、不下载正式数据、不调用 Jev、不开始实验。

## 版本与位置

- 本地仓库：`C:\Users\Hp\Desktop\GIt\Disicion-Models-Comparation`。
- 上传前代码起点：`2245580ea6a4eb0efcf31892ad3f6e8d56116794`，工作区干净。
- 本记录纳入 Git 后，使用新的 HEAD 制作 Git bundle，完整保留提交历史和所有受 Git 管理的代码、配置、文档、测试及 fixture。
- 服务器地址：`connect.bjb2.seetacloud.com:15492`，用户 `root`。
- 目标目录：`/root/autodl-tmp/decisionbench`。
- 传输包与清单目录：`/root/autodl-tmp/decisionbench-transfer-20261014`。
- SSH 非交互认证已成功；目标项目目录在本轮只读检查时尚不存在，数据盘有约 50GB 空闲空间。

## 校验和交接证据

- 本地生成传输包 SHA-256，服务器校验同一包的 SHA-256。
- 在服务器从 bundle 恢复仓库，核对 HEAD、受管理文件数量、Git 对象完整性和工作区状态。
- 对每个受管理文件核对其 Git blob 哈希，确认检出字节与当前提交一致。
- 最终传输回执保存在本地 `dist/upload-receipt-20261014.json` 及服务器项目的 `results/upload-receipt-20261014.json`，记录实际提交号、文件数量、包哈希和校验结果。
- 认证密钥不写入仓库、日志、传输包或回执。虚拟环境、历史 Mock 输出、模型权重、未受管理的本地文件不属于本次代码交接。

## 后续

实验启动、环境安装、正式类别说明审阅、计费信息和实验报告在后续执行。历史 `EXECUTION_LOG_20261013.md` 是早前记录，不作为本轮服务器环境已验证的证明。
