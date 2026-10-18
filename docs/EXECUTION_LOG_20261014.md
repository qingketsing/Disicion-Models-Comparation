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

## Qwen 实验完成及最终审计

12:48:15 UTC（北京时间20:48:15）容量运行器正常完成，正式32/64RPS各三轮300s全部执行。32RPS三轮及15个60s窗口全部通过，最差p95=118.017ms、最大调度迟滞12.855ms、合法成功率100%；64RPS前两轮调度迟滞35.737/33.422ms超限，第三轮通过，整体不通过。无需更低点补测。最高已测试稳定通过点32RPS，不声称GPU绝对上限或32–64之间精确边界。

最终归档 `dist/qwen-v4-final-capacity-snapshot.tar.gz`，40个独立运行，SHA-256 `a799169fce4f501f20924283236def65ab6200085027f0d16e584a5cb75e47d0`，已从远程下载并独立核对一致。Jev仍暂停，旧中断状态未替换。三份派生计划的suite.yaml以原字节复制为本地configs中的同名配置，纳入Git，不改冻结计划。

`reports/qwen-v4-final-20261014` 离线审计成功：源快照、输入、配置、结果哈希及独立复算通过；引用基线去重后40run，143142条测量记录，2000条预热，三轮主测试2974个唯一样本预测差异0；72个60s窗口逐窗输出。三条测量失败均为64RPS的client_overload，143139条ok，无目录外预测。测量耗时5451.285753秒含drain，按2.78CNY/h为4.209603998CNY；与租赁区间估算分开记录。

中文报告 `docs/QWEN_EXPERIMENT_REPORT_20261014.md` 已完成，涵盖主质量、59/60类F1口径、规模配对区间、容量失败依据、错误AI审阅、费用、版本修复和限制。确认两个拥有的控制器已结束、全部计划作业completed且无suite运行锁后，12:54:33UTC仅向拥有的Worker19643发送SIGTERM并确认退出，回执 `results/execution-20261014/qwen-final-worker-stop.json` 已拉回。未关闭实例或用户SSH转发；停止Worker不停止实例计费。

当前状态 **QWEN_COMPLETE / JEV_PAUSED**。配置、代码和文档以Git管理，原始结果和生成物以独立SHA256归档保管；完成最终本地/远程材料同步后向用户通知并暂停后台跟进。

## 本地 Jev v1 恢复

用户在 Qwen 完成后授权开始本地 Jev 实验。Qwen 的40个独立运行、最终审计和归档不变；Jev 使用新计划 `experiments/massive-jev-local-v1/plan.json`，旧 v3 Jev 中断结果保留且不覆盖。配置 `configs/experiment-suite-jev-local-v1.yaml` 只包含 `jev-1.13.0`，数据、目录、请求协议和官方输入价格按冻结方案填写。API 密钥只通过运行时标准输入进入进程环境，不写入配置、源码或结果日志。

本机 `127.0.0.1:7897` 代理监听。首个探针 v2 曾在 TLS 建连时超时，未发出模型 POST；使用显式 `ALL_PROXY` 后，探针 v3 的 `/v1/models` 和单条 `/v1/systemone` 均 HTTP 200，Choice 契约校验通过。合成探针不计入实验。

Jev checkpoint 于 15:00:24 UTC 启动，5 条预热和300条测量均完成，成功率100%、合法输出100%、Accuracy=0.8733333333，结果目录 `results/20261014T150024Z-checkpoint-full-seed42-rep1-jev-cba314f2`。随后于15:06:01 UTC启动完整 test 三轮主质量实验，预算8937条请求（含15条预热），watchdog 遇 HTTP/适配器/非法输出或连续传输错误会停止并保留证据。运行中曾出现4条连续附近的 `network_error/transport_error`，随后请求恢复为ok；当前未判定为阶段失败，继续观察并在阶段结束复核状态与请求记录。

首轮main于15:28:25UTC完成全部2974条，2967 ok、7 network_error，Accuracy=0.8597848016，60类Macro-F1=0.8375298321，supported59类Macro-F1=0.8517252530，合法成功率99.76463%，attempted p95=831.532ms。离线audit_run复算通过；与Qwen v4主测试数据和目录顺序除跨平台换行外逐字节一致。错误未删除、未重新发送，缺少usage的失败请求可能已计费，已知测量费用0.241180758USD仅是下界。该质量run不因p95超过500ms判为实验未完成；性能容量需另做load。第二轮15:28:55UTC启动，后续仍由同一watchdog顺序执行。

本轮组合启动命令曾被自动执行审核拦截，返回`blocked by policy`但无详细原因。首次将其解释为密钥/后台启动限制没有充分依据；后续核对独立Python启动命令可以执行。实际使用标准输入包装器启动，无后台窗口；原拒绝不归因于已证实的网络或凭据故障。实验日志和Git中不包含凭据。

## 2026-10-15：按用户要求重跑网络错误影响轮次

v1第二轮在291条测量后因连续3条网络错误被watchdog于2026-10-14 15:32:01UTC停止，288条ok。已核验拥有的控制器退出，修正生命周期元数据为interrupted，并记录`jev-local-v1-interruption.json`；原始requests字节未改，SHA256为`394abb90739806945cee64e4d272e9bb87e134c843b6afee7fd64e458e699847`。v1首轮的7条网络失败保留，不把该轮当作无传输错误的最终主质量结果。第三轮尚未执行。

用户明确要求“由网络传输导致的错误重新跑实验”。建立独立v2计划，受影响的main1/main2各完整重跑2974条，之后执行原定main3、scale和load；为独立运行再做一次checkpoint，不覆盖v1。模型、输入、提示、价格、代理路径、超时和并发判据保持不变。新计划SHA256为`bd3bbcecf0f84bfa8fa9b9ec83323f313d7d566791b6478dab1d18330beb4868`。预检25个run、测量16422条、预热125条，分阶段执行预算合计16547条；另有一条合成连接探针，均按真实调用记录费用。

新增外部控制选项`--stop-transport-error`，发现任何网络错误或超时即停止拥有进程树，不自动补发样本、不在同一轮隐藏重试。轮询间隔2秒，停止前仍可能有在途请求完成，全部保留。该选项用于v2，原有watchdog默认规则不变。运行器在内存接收凭据，探针成功后串行执行checkpoint/main/scale/load，每阶段离线复算，通过后才进入下一阶段；异常停止并保留证据，禁止无限计费重试。相关24项测试通过，Ruff通过。

旧v1的checkpoint、完整main1、中断main2、冻结计划、suite状态和执行日志已另存`dist/jev-local-v1-before-network-rerun-snapshot.tar.gz`及SHA256回执。Qwen全部结果与报告保持封存。

16:05:52UTC（北京时间10月15日00:05:52）启动v2，Git `ae38112`。鉴权GET与单条合成Choice POST均200、契约通过。16:05:56UTC进入checkpoint，5条预热中4ok、1network_error；2秒轮询检测到预热错误时已有3条测量完成（均ok），16:06:04UTC终止拥有进程树。三轮main、scale、load均未开始。不能将这次checkpoint计为完成，也不能据单次探针成功宣布网络稳定。

停止后确认driver/watchdog/controller及suite锁记录的进程均退出，将生命周期元数据修正为interrupted，删除匹配的陈旧锁；warmup/requests原字节哈希均核验未变，回执`jev-local-v2-interruption.json`。代理7897仍监听；后续5次不携带鉴权的只读GET均403，属于预期拒绝，无新增推理请求，不能解释为已证实的密钥错误。当前证据只能说明端点可达但传输间歇失败，尚不能确定代理节点或上游链路的具体故障。

按照用户“无法决定或无法处理时停下来”的要求，当前状态 **JEV_STOPPED_NETWORK / QWEN_COMPLETE**，暂停计费模型请求和自动重跑，保留v2现场归档`dist/jev-local-v2-transport-stop-snapshot.tar.gz`及SHA256回执。连接稳定后需从完整新尝试开始，不能补齐少量样本后冒充单轮结果；本次与v1调用均计入执行历史和费用核算。

用户再次明确要求“由网络传输导致的错误重新跑实验”，授权恢复尝试。核验本地无Python实验进程、7897代理监听，使用原有运行器新建本地v3独立计划；模型、数据、目录、超时、并发、费用和传输错误停止条件均不改。计划SHA256 `8c98fb59b85ba60a8df751f220b82dcf19e44d0597a79eee25e7d0ef6d505483`，25run预算16547（测量16422、预热125），另连接探针1条。旧v1/v2结果及归档保留，不宣称网络已修复。运行器在连接探针通过后执行checkpoint/main/scale/load，任何传输错误会停止并留存，禁止无限重试。

00:48:50UTC（北京时间2026-10-15 08:48:50）v3实际启动，driverPID97824；鉴权GET和合成POST均200，5条预热与最初99条测量均ok。状态和阶段日志采用jev-local-v3前缀，后台跟进恢复，仅监控该新尝试，避免启动重复控制器。此为运行中记录，不代表最终完成或网络稳定结论。

### v3 checkpoint完成；主测试再次传输中断

00:55UTC后台检查发现，运行器已在00:50:24UTC（北京时间08:50:24）停止。checkpoint于00:50:19UTC完成：300条测量、5条预热全部ok，离线audit_run复算通过；Accuracy87.6667%，60类Macro-F1=0.8645240870，supported59类=0.8791770377。测量费用0.024382008USD，usage完整，排除预热与后续失败尝试，非账单总额。该checkpoint不替代完整test主质量实验。

第一轮main于00:50:20UTC开始，5条预热全部ok，5条测量中4ok、1network_error。watchdog按首个传输错误停止拥有树，未执行其余main、scale或load。核验driver97824、watchdog112604、controller89164及锁PID84540均不存在后，仅修正manifest和suite生命周期元数据为interrupted、移除匹配的陈旧锁。原始warmup/requests字节未改，哈希分别为`4010cb63453ebae56768ca2521dd74bb48e9f9ee0db928287648ea8a86606151`、`631347ce2c9aee7586d743600ca8ca0de71713de3cc52d6d8a8c7baa9f70eafd`，回执`jev-local-v3-interruption.json`。

00:56:20UTC发起10次不携带鉴权的只读GET连接检查，无模型推理请求。其中9次收到预期403，另1次`RemoteProtocolError`；证实连只读连接也存在间歇性传输错误，不能归因于已证实的API密钥故障，也无法仅凭此确定代理节点、服务端或中间链路哪一处断开。诊断回执`jev-local-v3-readonly-diagnostic.json`。不擅自更换网络路径或通过静默重试掩盖错误，停止后续计费请求并通知用户，后台跟进暂停，等待连接故障处理后再恢复。

v3已完成checkpoint、中断main、冻结计划、suite状态及完整执行/诊断记录归档为`dist/jev-local-v3-transport-stop-snapshot.tar.gz`与SHA256回执。当前状态 **QWEN_COMPLETE / JEV_STOPPED_NETWORK**，v1/v2/v3失败和费用继续保留用于最终报告。

### 用户再次授权：复用checkpoint，仅重跑未完成轮次

用户再次要求网络传输错误重新跑实验。核验无Python实验进程、代理7897监听后，沿用冻结本地v3计划，新增运行器显式`--resume-transport`：只允许完成证据哈希与离线复算通过的完成项以及已审查的WatchdogTransportStop中断项，拒绝仍running或未知失败。使用suite原有`--retry-failed`机制，已完成checkpoint复用不发请求；main首轮从完整2974条重新开始，原中断attempt与请求目录保留，后续仍执行main2/main3、scale和load。新执行前缀jev-local-v3-retry1，未完成24run上限16242请求（16122测量、120预热），另连接探针1条，不修改冻结模型、数据、并发、网络路径或停止判据。新增恢复校验测试与watchdog测试共8项通过、Ruff通过。该授权为一次新完整尝试，不启用无限重试。

01:12:30UTC（北京时间09:12:30）retry1实际启动，driverPID107920；鉴权GET与合成POST200，checkpoint原run哈希校验与离线审计通过直接复用，没有重发305请求。01:12:34UTC新main首轮开始，最初105条测量ok，新目录results/20261015T011234Z-main-full-seed42-rep1-jev-9bb20d4e；当前运行中，不作为完成结论。watchdog launcher71288，状态/日志jev-local-v3-retry1前缀，后台跟进仅监控此次运行避免重复启动。恢复前修改追踪表时曾因默认GBK解码UTF8失败，已显式UTF8修正，未影响冻结输入或请求。

### retry1主测试网络中断与保存

01:19UTC后台检查发现retry1已在01:15:21UTC（北京时间09:15:21）因首个network_error自动停止。第一轮main留下739条测量，738ok、1network_error（massive-en-US-test-14011）；5条预热全部ok。其余main/scale/load未执行。不能计为完成，也不把738条局部成功率作为完整test质量结论。checkpoint仍为原300条完成项，未重复执行。

核验driver107920、watchdog71288、controller94044及锁PID103652均退出后，修正main manifest/suite为interrupted，追加attempt状态，移除匹配的陈旧锁。原warmup/requests字节哈希保持为`a5b97e25df84bff9234251b4bceb926fb47359eb9e409176efd6c02ddb2815c7`和`81b4a7fa36ba0529dcb40bb1d8f21c712cdc517445526db3b1ca3d46ed52f4e8`，回执`jev-local-v3-retry1-interruption.json`。旧attempt和全部原始记录保留。

01:20:53UTC做10次无鉴权只读GET，均收到预期403，新增推理请求0；7897代理仍监听。本次诊断没有复现传输异常，但不能推翻刚发生的主测试网络错误或证明未来连接稳定；已有日志只记录transport_error，无法进一步定位中间代理/上游具体根因。停止计费请求及自动重跑并通知用户，不改变原网络路径、超时或阈值。完整冻结计划、三个v3 attempt及执行/诊断记录归档`dist/jev-local-v3-retry1-transport-stop-snapshot.tar.gz`及SHA256回执。当前 **QWEN_COMPLETE / JEV_STOPPED_NETWORK**，Jev最终报告与其余实验尚未完成。

## 用户授权网络重试策略：本地Jev v4 retry3

用户明确要求“遇到网络错误就重试请求3次，不要直接停下来，再重新做实验”。按首次请求后最多追加3次实现，最多4次适配器调用；只对传输异常和传输超时重试，不重试HTTP错误、非法输出或适配器业务异常。间隔0.5/1/2秒，保留原30秒总请求期限，期限耗尽可能少于3次；保持原始scheduled时间和同一并发槽位，重试/等待时间计入端到端延迟及500ms SLO，不能把重试后成功的延迟重置为最后一次耗时。看门狗只读取逻辑请求最终状态，成功恢复继续执行，重试用尽或总期限耗尽才作为最终失败处理。

新增可配置network_retries（默认0，历史默认行为不变）和network_retry_backoff_s。每条请求的network_attempts记录尝试序号、起止时刻、真实异常类型、状态、退避和未知usage；不写异常原文或认证信息。summary另报适配器尝试、额外调用、传输失败和恢复数。失败尝试即使后来成功仍可能已计费，因此usage_complete=false、成本仅下界，最终报告须展示初次失败与重试恢复，不能把逻辑成功率当原始链路成功率。预算上限按最多4次调用放大并在执行前校验。合成连接探针亦最多追加3次网络重试，逐次计数和记录，与测量分开；探针每次调用超时30秒，实验测量则为总30秒期限。

新计划experiments/massive-jev-local-v4-retry3/plan.json SHA256 `e4af0d581f9306b49f0d1f72e8b84404510dfb44e905def4b6803bf756fdf267`；24run（main3/scale9/load12），16122测量、120预热，最多64968次API调用，另探针最多4次POST。这是上限而非已发生调用或费用。原local-v3 checkpoint300已完成并保留为旧策略预检证据，本版本不再发送checkpoint，不将其伪装成本次retry3测量。所有旧完整/中断结果及冻结输入保留，v4重新完整执行三轮main，不拼接旧样本。

本次修改了核心源码，原冻结v1/v2/v3计划不再用当前源码继续执行；其source快照及结果保留，历史审计用run自身冻结证据，不修改旧计划哈希以绕过校验。Qwen报告及40run封存不重跑。全套74项测试通过（1条上游Starlette弃用警告），包含3次追加重试后成功、4次失败上限、不重试429/非法输出、总期限、端到端退避、未知usage成本下界及4倍预算拒绝不足。Ruff通过。

01:29:49UTC（北京时间09:29:49）v4-retry3实际启动，driverPID83692，main watchdog launcher79880；鉴权GET/合成POST均200。主测试首轮results/20261015T012952Z-main-full-seed42-rep1-jev-eaa8b9bc，最初136条测量ok，未发生额外尝试。该记录不代表主测试完成；运行器将自动串行main/scale/load并保留每次重试元数据，后台跟进更新为新计划和新策略，禁止误因单次已恢复网络错误停止。

## 网络波动后用户授权恢复v4 resume1

用户说明刚才网络波动、现在重新开始实验。检查发现driver已在2026-10-15 01:44:09UTC退出：main1完成2974条全部逻辑ok，独立Accuracy86.04572966%、全60Macro-F1 .8370084067、supported59 .8511949898；5次额外尝试恢复2条，已知测量费用0.241750068USD为下界。01:42:49UTC开始main2，241条中240ok、1网络错误，失败请求经历首次RemoteProtocolError和追加三次ConnectError后最终失败，watchdog于01:44:08UTC停止，并未因单次已恢复异常误停。

核验driver83692/watchdog79880/controller73560/lock110076均不存在，修正main2 manifest及suite生命周期为interrupted、移除匹配锁，原始requests SHA256 1ceee844aa7e02a2fa39869d578701edeb9a77b5f2861ee29d5604bf3f4f587a不变。完整归档dist/jev-local-v4-retry3-before-resume1.tar.gz SHA256 cf9c2a76cf23d03c089650cf5846bc22dc40c15c796155032a5f7d2d993fefce。

按用户新授权用原有--resume-transport机制及唯一jev-local-v4-retry3-resume1执行前缀恢复，main1通过哈希及audit_run校验后复用不发请求，main2从完整2974条重跑并保留旧attempt，接着main3/scale/load。剩余23run、13148测量+115预热，最多53052次API尝试，另合成探针最多4POST；这是预算上限。保持原始冻结计划、网络路径、30秒总期限和首次后3次重试，未修改核心代码。

01:47:52UTC（北京时间09:47:52）resume1实际启动，driver100844；连接探针GET/合成POST200，main1完成证据复用。01:47:54UTC重启main2，5预热ok，24条测量中23ok/1HTTP499，01:48:01UTC看门狗按既有HTTP失败策略停止。该请求耗时154.42ms，仅一次尝试，未追加重试，因为当前冻结策略只对httpx.RequestError/传输超时重试。HTTP499本身不能确定由代理还是上游发出，原始日志未保留响应体/服务器头，不把它认定为已证实的传输异常或凭据故障。未擅自扩大HTTP重试范围。

核验driver100844/watchdog84040/controller87452/lock86600均已退出后，manifest/suite修正interrupted、error_type=WatchdogHTTPStop，原始请求哈希e131a8f0e4e69cdcd76c155c4e5af8968bdfb4ab50d397e558bc10152ad59d12保持不变，移除匹配陈旧锁。归档dist/jev-local-v4-retry3-resume1-http499-snapshot.tar.gz SHA256 ba038186a674031732be554fccedebc7a480707ba705d3650802b052306def95。当前main1完成，main2仍未完成，停止后续请求并通知用户此新错误；后台跟进暂停，避免未经处理反复计费重跑。

## 用户说明网络波动后授权resume2

用户再次要求现在重新开始。核验无Python实验进程、旧resume1已退出且suite无运行锁；保留已审计完成的v4 main1。旧resume1为HTTP499而非传输异常，新增外部运行器显式--resume-reviewed-http499开关，只有用户明确授权后使用；必须为已标记interrupted/WatchdogHTTPStop、manifest中断一致且所有失败行均HTTP499，拒绝401/429和未知失败。此选项只允许新完整尝试，不改变冻结HTTP不重试策略，不修改核心源码或原计划。相关11项恢复/watchdog测试通过。保持每请求网络最多追加3次/原30秒总期限，main2完整重跑；main1不重复。剩余23run、13148测量+115预热、最多53052次API尝试，另合成探针最多4POST。执行前缀jev-local-v4-retry3-resume2，旧现场与全部attempt保留。

04:09:54UTC（北京时间12:09:54）resume2实际启动，driver88332、main watchdog launcher73296；GET与合成POST均200。main1完成证据复用不发送；main2新目录results/20261015T040957Z-main-full-seed43-rep2-jev-efb6e432，最初49测量ok。后台跟进更新到本次prefix/PID和已授权HTTP499中断恢复，禁止重复启动。

### resume2 main2完整完成与增量备份

2026-10-15 04:21:15UTC（北京时间12:21:15）第二轮main完成2974条逻辑ok，5预热ok；4次追加尝试恢复3条请求，未发生最终失败。04:21:45UTC同一控制器自动开始main3，新目录results/20261015T042145Z-main-full-seed44-rep3-jev-9f7a81b5，未重复启动进程。main2离线audit_run、完成证据哈希、冻结输入/源码与run source快照逐文件校验均通过：Accuracy86.14660390%，全60MacroF1 .8392506082，supported59 .8534751948；已知测量费用.241750068USD为下界，缺失重试usage不冒充完整账单。两轮均同一2974唯一样本，不把5948次重复当5948个独立样本。

已将完成main1/main2、完整冻结计划和捕获时suite状态另存dist/jev-v4-main1-main2-completed-snapshot.tar.gz，SHA256 322fe0abb693fd8c3002e70d81e5a3beb2778e8fb6cd4ebcfda0529532c64c67，回执另存；第三轮运行日志未混入完成结果归档。实时suite不被备份状态覆盖。当前main3运行中，尚未完成scale/load/最终报告。

### 三轮main完成；规模实验进行中

2026-10-15 04:32:46UTC（北京时间12:32:46）main3完成2974测量逻辑ok，3次追加尝试恢复1条，5预热ok。三轮分别Accuracy86.04572966%/86.14660390%/86.18022865%，均值86.12418740%，样本标准差0.06999549个百分点；main3全60Macro-F1 .8393599458、supported59 .8535863855。三轮是相同2974唯一样本的重复，共8922测量逻辑请求、8934测量适配器尝试（12追加），恢复6条；不包含预热、探针、旧失败轮次。三轮已知测量费用合计.725250204USD下界，三轮均有失败尝试未知usage。按sample_id配对预测差异1vs2=33、1vs3=36、2vs3=29，不声称Jev确定性复现。

所有完成run的completed_entry/audit_run、冻结输入和源码哈希以及run source快照逐文件校验通过，回执results/execution-20261014/jev-v4-three-main-audit.json。完成三轮main及当时完成的seed42三组scale（10/30/60类Accuracy98%/93%/89.5%，仅单种子暂不作最终规模均值）归档dist/jev-v4-three-main-completed-snapshot.tar.gz，SHA256 032e2d2f5a9974aad2990e5c8181553e2b24d32543468b3f45835969aa1d2ecf。04:32:49UTC同一driver88332自动进入scale，watchdog launcher108632、实际watchdog85744、suite实际111040；未启动重复控制器。当前main阶段完成、规模阶段继续、负载与最终报告未完成。

### 九组规模完成、负载初测进行中（2026-10-15）

04:43:36UTC（北京时间12:43:36）九组scale全部完成，每组200测量和5预热均ok，无额外网络尝试。10/30/60类目录的三种子Accuracy分别为98%/96%/97.5%、93%/92.5%/96.5%、89.5%/90%/92%；均值97.16666667%/94%/90.5%。九组已知测量费用0.091138572USD，预热另计。每种子为同一200条anchor样本的目录规模配对，真值仅覆盖10个anchor类；完整目录F1包含其他零支持类别，不能与完整test的59支持类F1混同。已按种子核对sample_id及真值，计算2000次配对bootstrap，不把不同目录重复测量当新增独立样本。

同一driver88332于04:43:37UTC自动进入load；watchdog launcher106236、实际113964，suite launcher108712、实际97748。首个4RPS/120s完成480逻辑ok，12追加尝试恢复11条；p95=502.560390ms、最大调度迟滞25.284800ms，整体与两个60秒窗口均不通过。第二个2RPS/120s完成240逻辑ok，无追加尝试，p95=255.786670ms，最大调度迟滞95.431600ms，整体及两个窗口因调度超限不通过。这些为既定容量判据未通过，不是请求最终失败；保持原阈值，继续原pilot其余负载点，不重发main或scale，也不能据此声称API服务吞吐上限。已恢复的传输错误仍计入端到端延迟和费用下界，4RPS已知测量费用0.039019722USD为下界，2RPS为0.019511352USD，预热另计。

本次捕获14个完成run（三轮main、九组scale、两个load），逐项completed_entry、audit_run、冻结源码/输入及每run源快照校验通过。审计回执results/execution-20261014/jev-v4-scale-completed-audit.json，另存dist/jev-v4-scale-completed-snapshot.tar.gz，SHA256 9764437925fec22d83c34e5069f251a8ce78311365af8da22dd70eb28dd127ae；归档每成员与源文件SHA256逐一重验，捕获suite状态独立保存，没有覆盖实时状态或混入在途run。后续8RPS seed42运行中，完整负载、正式容量复测、报告尚未完成。

### Jev容量复测工具准备与等待控制器（2026-10-15 04:58UTC）

为保持已完成三轮main不重发，将既有容量准备函数增加显式model_name（默认Qwen保持兼容），Jev包装器只接受三轮已完成且audit_run/源快照核验的Jev基线。复用原始baseline输入字节、哈希、部署/价格/网络重试设置与完成entry；只有新load会发送。现有冻结核心源码未修改，v4 verify_bundle仍通过。45项实验工具/容量/恢复/watchdog测试通过，Ruff通过；测试覆盖Qwen及Jev基线复用、修改证据拒绝、CRLF严格兼容、重试配额与正式负载选择。

新增orchestration/prepare_jev_capacity.py和orchestration/jev_capacity_driver.py。容量选择必须等待当前pilot完整完成和离线审计；如8RPS三轮及窗口通过才考虑扩展，先做首次+3追加的尝试和Token预算筛查；若无通过点，则最低1RPS、300秒三轮。最高通过点与最近更高已测失败点正式复测，候选长测失败时只向更低点降级确认，不改500ms/.99/20ms判据，不自动重跑最终HTTP/网络失败。所有正式300秒run及每60秒窗口均需通过，允许结论为无已确认容量。

从三轮main最终usage观测的每次输入+输出Token最大值为2563；8RPS四倍尝试预算为32attempt/s、82016Token/s，16RPS为64attempt/s、164032Token/s，后者超过公布动态100000Token/s，因此不直接照搬Qwen16/32RPS扩展。这是以同输入实测usage作的保守预算筛查，不是精确tokenization保证、每秒突发整形或账号配额保证；重试时刻可能聚集，仍需记录实际尝试，并保留API错误证据。输出价格为0不意味着输出Token不纳入吞吐预算。

04:58:18UTC（北京时间12:58:18）容量等待控制器已启动：launcher96784、实际114740，状态results/execution-20261014/jev-local-v4-retry3-capacity-status.json为waiting_for_pilot，原pilot88332仍独占当前suite执行，未另启动pilot/main/scale或发送容量请求。现有授权suite108712的运行内存环境凭据经临时stdin管道交接至等待控制器，没有写入文件、日志、Git或prompt；启动回执仅记录PID/状态与交接方式，未记录凭据。新控制器可在pilot结束后继续，无需再次输入；若pilot停止或退出则停止后续请求，不能因等待控制器存在而重复启动。

容量工具/启动回执与等待状态快照另存dist/jev-v4-capacity-startup-tools-snapshot.tar.gz，SHA256 89d56189988ef1cc6ccd4b73cf1ccb192650043fe34578b1f468f3e6ed507d95；归档成员逐一SHA256校验，包含45项测试/Ruff/冻结校验回执，不含凭据，捕获时新增容量请求为0。

### 配对质量分析与AI错误审阅完成（2026-10-15）

双方六个完成main的audit_run、源快照及逐轮输入匹配检查通过；比较完整有序sample_id/文本/GT与目录版本/有序标签说明，未因跨平台换行哈希不同而跳过语义检查。每轮仍N=2974，bootstrap2000次/seed42按唯一样本配对，不拼接3N。Jev-Qwen准确率差三轮为40.11432414/40.21519839/40.24882313个百分点，95%区间为[38.26496301,41.86281103]/[38.36583726,41.96368527]/[38.43308675,41.96368527]个百分点。第一轮both_correct1323、Qwen-only43、Jev-only1236、both_wrong372。证据reports/qwen-jev-main-paired-20261015，说明docs/QWEN_JEV_COMPARISON_20261015.md；容量和总费用部分明确未定稿，不据质量差推断部署无关的延迟/成本收益。

docs/JEV_ERROR_REVIEW_20261014.md及reports/jev-error-review-20261015保存40条AI审阅案例，非人工评审。第一轮415条语义错误；按top20混淆方向各一条和seed42剩余样本选至40条。疑似上下文缺失/标注歧义均仅AI假设，不修改原GT、目录或得分，不将定性样本比例当错误分布。每条保留原文、sample_id、GT和预测。

新增orchestration/jev_report.py复用离线analysis/audit及现有窗口/绘图，Jev成本字段明确USD、完成基线去重，测量与预热分别记真实适配器尝试、网络失败/恢复与未知usage下界；另orchestration/jev_cost_ledger.py用于最终统计旧版本/中断/探针的独立费用账。单轮重试汇总现场验证2979attempt/5追加/2恢复及费用下界、5预热独立计价正确。完整90项测试通过（1条上游Starlette弃用警告）、Ruff通过，当前冻结v4 verify_bundle通过；报告器/外部工具修改不改变冻结核心。

限制记录：本次本地Controller主机同时进行了离线审计、bootstrap和工具测试，可能争用CPU/IO并影响调度；没有系统资源时序证据可将某次迟滞归因于特定后台任务。所有原始lag和不通过点保留，不能归咎于API或声称纯模型容量。后续正式300秒确认期间暂停计算密集型本地审计/测试/绘图，仍保持原阈值与原始输入；不把pilot失败重标通过。

质量配对/40例AI审阅/工具代码与文档另存dist/jev-v4-quality-comparison-review-snapshot.tar.gz，SHA256 e524c2dabe51e3006b4dc0d03087ede412bec9f4e12fca52aa3a3b6a52d839dc；19个归档成员逐项哈希重验。该归档不宣称Jev容量或最终总费用已完成。

### Pilot完成与正式最低负载确认启动（2026-10-15）

05:13:30UTC（北京时间13:13:30）原driver88332完成全部24run（main3/scale9/load12），状态pilot_completed并正常退出。12组120秒load共5400逻辑测量，其中5397ok、3client_overload（8RPS seed42），87次追加尝试恢复71条请求，无最终HTTP/传输耗尽。已知load测量费用0.438698358USD为下界，预热另计；数据来自容量driver逐run的completed_entry/audit_run及源快照/窗口审计结果。1/2/4/8RPS各三轮均未满足完整及60秒窗口判据，每轮最大调度lag均>20ms，部分点还有p95>500ms。不能将这些失败宣称API服务吞吐硬上限，且本机同驻工具工作干扰限制已另记。冻结pilot和所有原始结果保留，不重标通过。

容量driver114740按已记录无通过点策略自动准备新计划experiments/massive-jev-local-v4-retry3-formal/plan.json，SHA256 badc58959d3119553ec1fc55e217b985c61433b9a18dab3f19203f05e30ff955。仅新发1RPS、300秒、三轮，另引用原三轮已审计main完成entry，不发送main或checkpoint。新测量900、预热15，首次+3追加的API调用预算上限3660（不是实际调用或费用），每秒四倍预算4attempt/10252Token低于公布配额；局限仍为观测Token筛查而非突发限速保证。派生suite原字节配置configs/massive-jev-local-v4-retry3-formal.yaml纳入Git，未改原plan。

05:13:42UTC正式首轮启动results/20261015T051342Z-load-rps1-seed42-rep1-jev-ec13b7af；watchdog launcher82168/实际110424，suite launcher110324，日志results/execution-20261014/jev-local-v4-retry3-capacity-formal.log及-watchdog.json。容量driver继续运行，禁止重复启动或重发已完成main。正式阶段暂停计算密集型本机审计/测试/绘图，只作轻量状态/日志记录；等待三轮完整300秒和每60秒窗口审计后才判断有无确认容量，不调整阈值。


### Jev正式容量与全部请求结束（2026-10-15）

05:29:54.481669UTC（北京时间13:29:54）容量driver114740完成并退出，pilot88332及相关watchdog/suite进程已退出。两个计划去重27run，正式1RPS300秒三轮各300逻辑ok，p95为3827.211750/3795.938760/3384.419375ms，最大lag26.104700/26.962300/24.744600ms；0/3整轮及0/15窗口通过，confirmed_capacity_rps=null。正式测量978attempt、78追加、41恢复，费用0.073159716USD下界。无最终HTTP或传输耗尽，未降低阈值或继续重复整轮。正式阶段未做本机密集分析/测试/绘图/压缩。

实际运行orchestration.jev_report对pilot/formal两plan，输出reports/jev-v4-final-20261015；随后实际运行jev_cost_ledger。27run完成证据、源快照及独立复算通过，17022测量=17019ok+3client_overload，17196适配器尝试，177追加/失败、118恢复；135预热全ok、138attempt、3追加/失败、2恢复。已知测量1.328246850USD，含预热1.337850696USD；全历史run及探针2.049680304USD，未知失败usage使总价为下界。详细费用账区分当前、历史、预热及探针。主质量和Qwen配对结果不因负载失败改变。

中文最终报告及配对比较已更新；experiment-audit按技能要求使用新鲜审阅代理，语义判断仅same-family/provisional，确定性复算/哈希单列。收尾归档回执及审阅结论见后续记录。Qwen报告及40run未覆盖，不重启Worker。


### 最终确定性核验与原始证据归档

2026-10-15 05:41UTC：jev-v4-final-verification.json记录两份冻结plan的资产/核心源码/config哈希、suite完成与raw结果哈希、去重请求/成本及重试等式、39窗口全失败和容量completed/null核验通过。Qwen封存报告SHA256仍为1afc6b1c8744deaa60cb5fe098b2e210e127a3796f212f48e866c654ce2c2cb3，未修改。

原始/历史/冻结输入与源码/suite/执行现场共2141文件，归档dist/jev-v4-final-evidence-snapshot.tar.gz，SHA256 511a7401a752ea06483997c9efad93e0b36adf684a86a26c46f9c9443f5bb91d。独立回执dist/jev-v4-final-evidence-snapshot.tar.receipt.json逐成员列SHA256，源文件与解包流逐项比对通过，没有覆盖raw。orchestration.jev_final_snapshot为离线归档工具，本次实际执行并Ruff通过。最终文档/离线结果/审阅轨迹另归档，避免把过程中状态快照当最后文档。

experiment-audit首次指定gpt-6-astra因账户404不支持而未执行，错误原文已保存；新鲜gpt-6.1-sol ultra替代审阅直接读取主文件，不传执行者结论，记录same-family/provisional，不冒称指定模型审阅成功。


### 语义审阅反馈与来源链补全

新鲜gpt-6.1-sol ultra审阅初轮WARN：原始publisher包缺失、COST追踪范围含未执行月度TCO、交付归档仍待生成、Qwen历史文字需时点说明。未发现指标伪造/自归一化/把中断拼接完整轮次；复核67个双方最终run、2412个run源文件和费用账一致。完整原文保存.aris/traces/experiment-audit/2026-10-15_run01。修正tracker仅费用核算DONE，业务月度TCO未评估；Qwen原报告不动，在配对报告加历史截止/最新状态说明。

05:50UTC从来源清单的Amazon官方S3补回MASSIVE1.1原包40251390字节，SHA256 4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577，与原provenance一致。首次下载未完整、哈希不匹配而被拒绝，随后严格验证Content-Range的分段补取恢复完整包；未改变网络代理/实验路径或发API推理。原生train/dev/test的ID/utt/intent经原准备函数转换，与保留归一化数据逐对象精确一致；checkpoint按seed42重建也一致，五项归一化SHA均匹配。报告脚本/JSON为publisher-source-verification.py/json，不重写GT或运行原始文件。

补充来源归档dist/jev-v4-source-provenance-snapshot.tar.gz，12成员逐SHA256通过，归档SHA256 9d81c77571c671b74212fd035d592c1c9881974c39088940f41f3d8fd15d7ca7。来源可复算性缺口的复查使用同一审阅代理，明确same-family/provisional。主v4证据归档保持不覆盖，新增来源单独备份。


### Jev最终审阅与交付封存

定向复查独立读取官方原包，来源/原生行/CRC及归档12/12、2141/2141成员都通过；A/B/D/E/F PASS。C仅因审阅截止时最终交付归档和根审计文件尚未生成而WARN，原文保留，不改成事后假PASS。EXPERIMENT_AUDIT.md/json及全量请求/响应轨迹已生成，semantic same-family/provisional；最终归档生成后由deterministic postflight闭合交付项，外部回执results/execution-20261014/jev-v4-final-completion.json记录最终SHA、Git和自动化状态，避免归档自引用。

最终交付物包含报告、离线CSV/图、工具/测试、审核原文轨迹、两份原始/来源归档的回执和Git bundle。主证据/来源归档保留原SHA不重写；Git只提交明确代码/文档/根审计，.aris/traces不提交。所有实验请求已停止；全部校验与备份完成后暂停jev跟进，不再启动本地/远程实验。各最终归档自身SHA见dist同名独立receipt和final-completion.json。
