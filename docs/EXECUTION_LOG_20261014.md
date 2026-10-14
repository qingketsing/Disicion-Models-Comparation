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

## v3 checkpoint 通过与外部连接暂停

v3 代码 `d2052b2`；计划 SHA-256 `ffb1c6210eb9c1a506223df3ceba679c2911ce2ec628cb679930d540948d7977`。两端各 300 条 checkpoint 和独立质量复算通过。

| 模型 | Accuracy | 完整目录 Macro-F1 | 合法成功率 | 结果目录 |
|---|---:|---:|---:|---|
| Qwen | 0.5333333333 | 0.5126157589 | 1.000000 | `results/20261014T073054Z-checkpoint-full-seed42-rep1-qwen-81ef1d7f`（远程） |
| Jev | 0.8766666667 | 0.8645240870 | 1.000000 | `results/20261014T073104Z-checkpoint-full-seed42-rep1-jev-a99bd8c9`（本地） |

Jev 主测试首轮 07:36:24 UTC 启动，后续阶段尚未启动。Qwen 主测试启动前，SSH 反复在接受 RSA 公钥后的认证阶段断开；偶尔只读查询成功但启动未成功。尝试常规连接、单独密钥/签名算法及公共 DNS 解析出的真实地址（保持已验证 host key 检查），未能稳定恢复。无法确认服务端原因，已询问用户实例/端口是否改变，并按用户“无法处理时停下来”要求停止推进。

08:00:15 UTC 停止本轮拥有的 Jev Controller，核对 suite 锁中的实际 PID 108848 已退出后，明确将 manifest、suite entry、attempt 标记 `interrupted / ExternalControllerStop`，删除失效锁；原始请求记录未改写。部分测量 2933/2974 条，其中 2930 ok、3 network_error；不作为完整 main 结果，不启动第二/第三轮或负载/规模实验。请求日志 SHA-256：`b101c806fc11a807615d6660b4005bf8b7e1f4bfb96803c81ea20b0e20e3c893`。缺失请求/usage 不能据已知日志推断为零费用。

`results/execution-20261014/v3-jev-main-interruption.json` 和 watchdog 日志记录中断依据。外部 watchdog 代码存于 `orchestration/stage_watchdog.py`，不改变冻结套件请求协议；Windows 的 venv 启动器可能另有 Python 子进程，故自动异常停止处理整个拥有的子进程树。代码仅从 stdin 获取运行时密钥，不保存凭据。

当前状态：**PAUSED_UNRESOLVED_SSH**。远程 Qwen checkpoint 尚未拉回；Qwen Worker 之前在运行，SSH 不稳定导致无法确认其当前状态或停止，可能继续占用付费实例。用户自建转发保持原样。恢复后先验证连接、进程、输入哈希和 suite 状态，再显式重跑中断的 main，保留本次部分结果与预算记录。完整实验报告须等完整 main/load/scale 完成，不能把 checkpoint 当最终主表。

## 用户恢复授权：只执行 Qwen

2026-10-14 用户确认远程服务器正常，要求只完成 Qwen 实验，Jev 暂停。SSH、Worker 健康检查及 v3 输入/源字节核验通过；本次继续执行未发起任何 Jev 请求。

北京时间 18:28（10:28 UTC）启动 Qwen v3 main。首轮 2974 条完成，Accuracy=0.4593140551，2973 ok、1 invalid_output。目录外预测为 `datetime_settings`，样本 `massive-en-US-test-9193`，真值 `calendar_set`，输出 10 Token，非截断。第二轮在排查期间发出 602 条均正常请求，随后 SIGINT 停止；suite 记录 interrupted，未启动 scale/load。原始首轮和部分第二轮均保留。

独立诊断复现：相同完整 60 类 response_format JSON Schema 请求返回目录外标签，但单一强制标记的枚举生效。直接 `structured_outputs.json` 的单标签诊断也生效；因此不是凭单次正常输出即可证明完整目录约束可靠。保存原始请求/响应于 `results/execution-20261014/qwen-enum-diagnostic-1.json`，3 条诊断请求独立计数，不混入实验。

已查阅已安装 vLLM 0.11.0 协议、结构化输出配置和 CLI：支持固定 `guidance` 后端（llguidance 0.7.30）及 `disable_fallback=true`。例行修复采用固定后端，不改类别说明、数据、权重、提示词、temperature、输出预算或后验映射。不能将当前证据推断为已定位 xgrammar 的内部缺陷；只记录 auto 后端的实际违约及固定 guidance 的验证。

新版本 `configs/experiment-suite-qwen-v4.yaml` 只含 Qwen，25 个 pilot run；部署配置 `configs/qwen-native-westd-guidance.json`。Worker 11305 正常停止，新 Worker 19643 已启动，启动参数与配置哈希保存在 `qwen-guidance-launch.json`。完整目录、强制枚举的 response_format 和 structured_outputs 共 3 条新诊断全部通过，原异常文本不再生成目录外标签，仍可能语义错误。50 项测试、Ruff 通过。v4 checkpoint 正在执行，通过后重跑全套 Qwen；不复用违约的 v3 main 作为新版质量基线。

## v4 质量、规模完成；负载持续执行

北京时间约 19:02（11:02 UTC）三轮 v4 main 完成，每轮 2974 条均为合法输出，Accuracy 均为 0.4593140551，完整目录 Macro-F1=0.4872393742，supported Macro-F1=0.4954976687。完整 test 对 `cooking_query` 无真值支持，共支持 59/60 类，保留该类目录和完整目录 F1 定义。已完成前两轮逐样本比较无预测差异；最终报告仍将独立检查三轮全部样本。重复调用不作为新增独立样本。

9 组 scale 完成，全部输出合法。每个种子内三个目录使用共同 200 条样本、目录嵌套；Accuracy如下。

| 种子 | 10 类 | 30 类 | 60 类 |
|---|---:|---:|---:|
| 42 | 0.755 | 0.660 | 0.585 |
| 43 | 0.785 | 0.575 | 0.505 |
| 44 | 0.840 | 0.670 | 0.485 |
| 均值 | 0.793333 | 0.635000 | 0.525000 |

40 个代表错误由 AI 审阅，记录于 `QWEN_ERROR_REVIEW_20261014.md`，非人工审阅。按首轮最高频 20 个混淆对各取一条，再 seed=42 抽取 20 条剩余错误；没有据此修改真值、类别说明或提示词。

当前在执行 1/2/4/8 RPS、120s、各三轮的 load。独立阶段运行器 PID20426，容量扩展/确认运行器 PID21480；后者等待前者完成，保证同一 Worker 不被两个实验 Controller 同时施压。所有真实 run 都有独立快照、日志、配置哈希和 suite 状态，异常输出会触发停止。

容量扩展规则已写入 `orchestration/qwen_capacity_driver.py`：如果 8 RPS 三轮均通过，先测 16/32，再逐级翻倍，遇失败或达到 256 RPS 的明确实验上界停止扩展；每点 120s 三轮。最高通过点及最近的更高失败点进入 300s 三轮独立确认。每个新计划明确引用并核验 v4 三轮 main，不重复发送质量基线请求。该规则只确定实验负载范围，不设业务语义精度底线。

最终审计 `orchestration/qwen_report.py` 会核验源快照和输入哈希、复算质量、按 run_dir 去重借用基线、报告重复差异和规模配对区间，并额外检查各 60s 稳态窗口。单元测试验证全窗口 p95 可掩盖局部失稳的情况。不能只凭 120s 或全窗口指标宣称正式可持续容量。

本地完整快照 `dist/qwen-v4-quality-scale-snapshot.tar.gz` SHA-256 `55f7567126d0fd046bbf5db760b3dbbf799a16cffeff4bf2d242c08f595c7abf`，保存当时 14 个完成 Qwen run（含首个 load）；Jev 本地状态未覆盖。其余 run 完成后再次完整拉回并校验。

为落实用户“实验结束后告诉我”，已设置本聊天后台跟进 `qwen`，检查运行状态，正常阶段不做周期汇报，完成或无法处理异常时通知。当前状态 **RUNNING_QWEN_ONLY**；Jev 保持暂停。本地回报、最终 Git 提交和完整 Qwen 报告尚待负载初测及正式复测完成。

## v4 pilot 完成；容量派生计划跨平台换行修复

11:40 UTC 基础套件 25/25 完成：checkpoint 1、main 3、scale 9、load 12。1/2/4/8 RPS 各三次 120s 初测均通过，四档最差 p95 分别为 122.750/123.915/126.365/123.181ms，合法成功率均 100%；最大调度迟滞分别为 2.622/2.778/2.695/6.140ms。尚不能据此确认最终可持续容量。

容量运行器 PID21480 在准备 `massive-qwen-guidance-extended16-32-v4` 时因输入哈希不一致停止，尚未发送任何扩展实验请求。只读检查确认新旧 JSONL 和 catalog 的解析内容相等，原文件 CRLF、新文件 LF，去除该换行差异后逐字节相等。原有 25 个结果、冻结计划、失败准备目录、状态和日志均保留。

例行修复仅作用于尚未执行的新派生计划：要求新旧数据与目录除 CRLF/LF 外逐字节相等，然后复制已审计主质量基线的原始输入字节，重新计算派生计划输入哈希并执行原有完整校验。不会放宽真值、样本顺序、类别顺序、类别说明或元数据检查。新增跨平台换行回归测试及四种内容/顺序变化拒绝测试，实验工具相关 21 项测试和 Ruff 通过。运行器新增尝试后缀，后续使用 `retry1` 新目录，避免覆盖失败准备证据；启动前核对旧 PID 已退出并归档失败状态。

修复提交 `2445f5d` 已同步服务器。本地全套 56 项测试通过（1 条上游 FastAPI/Starlette 弃用警告），服务器相关 21 项测试通过。11:52:47 UTC 启动容量运行器 PID22854，`--attempt-suffix retry1`，Worker19643 保持原配置。旧失败状态保存在 `qwen-capacity-status-failed-preparation-1.json`，新日志 `qwen-capacity-driver-retry1.log`。新派生计划 SHA-256 `273a0bc262e11c68ee5a02b2c1364254238b697ec45ac5c69a96a7894ffa62c3`；首轮32RPS于11:54:54UTC完成，其余轮次继续执行，尚未形成容量结论。后台跟进已更新为新运行器，避免重复启动。

基础套件25个完成运行已完整拉回本地，快照 `dist/qwen-v4-pilot-complete-snapshot.tar.gz` 的 SHA-256 为 `953c624110e36807e8fb9a9c79e4c71016494a42376647b37babe714811ddc0c`，下载后独立核对与远程一致。仅合并完成的Qwen结果，Jev中断状态保持原样。

## 扩展初测完成；32/64 RPS 正式确认执行中

12:07:51 UTC 16/32 RPS 各三轮120s完成，两档均通过；最差p95为109.024/118.405ms，最大调度迟滞为2.819/17.263ms，合法成功率100%。12:15:10 UTC 64 RPS三轮120s完成，最差p95=234.512ms、最低合法成功率99.98698%，但最大调度迟滞21.745ms超过冻结20ms限制，因此这一技术容量点未通过。第二轮一条失败为 `client_overload`（样本massive-en-US-test-296），并非目录外标签或证据已确认的网络错误。不得直接将该结果解释为GPU吞吐极限。

运行器按预先确定规则停止继续翻倍，12:15:11 UTC开始32/64 RPS各三轮300s正式确认，计划SHA-256 `30d4c2128d5c13588abc43f72fe11fe87ac184637b05ef12315002b1ab98297b`。当前仍运行，尚无正式可持续容量结论。运行状态中pilot阶段的rates字典被扩展结果追加；最终统计按各冻结计划和完成run独立审计，不以该可变状态字典归属计算阶段数量。

已完成的34个独立Qwen运行（借用main基线按run_dir去重）拉回并离线审计，快照 `dist/qwen-v4-extended-complete-snapshot.tar.gz` SHA-256 `550d85bfe1ca5fd18180b7f62bbd569f1399ccead525ef6cfe0b68c4a150a4d3`，下载哈希独立核对一致。预正式审计输出 `reports/qwen-v4-extended-preformal-audit`：源快照、输入、独立复算通过；main三轮2974个唯一样本预测无差异；完成测量请求56742、预热1700。测量区间含drain合计3651.013秒，对应2.819393 CNY，排除预热和空闲、并非租赁账单或最终总费用。最终审计须加入正式复测，不使用此次空的technical_capacity_candidate作最终结论。
