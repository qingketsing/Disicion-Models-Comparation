# westd 通过本机代理访问 Jev

2026-10-14（Asia/Shanghai）检查确认 Windows 本机 Clash/Mihomo 在 `127.0.0.1:7897` 监听。显式 HTTP 代理访问 `https://api.typesafe.ai/v1/models` 返回 HTTP 403，响应为 `authentication_error: Must supply an API key`；未携带密钥，未发送推理请求。此前服务器直连返回区域限制 HTTP 451。

自动审批检查拒绝了创建后台 SSH 转发进程的命令，仅报告 `blocked by policy`，未给出具体原因。隧道尚未建立；本文件不表示服务器代理已经可用。

## 在本机 PowerShell 启动

```powershell
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:17897:127.0.0.1:7897 -p 16259 root@connect.westd.seetacloud.com
```

保持该终端运行；无输出通常表示正在保持连接，失败时会显示错误。转发链路为服务器 `127.0.0.1:17897` → SSH → Windows `127.0.0.1:7897` → Clash 出口。只绑定服务器回环地址。

## 在服务器验证与实验进程中使用

```bash
curl --proxy http://127.0.0.1:17897 --noproxy '' --connect-timeout 10 --max-time 30 -i https://api.typesafe.ai/v1/models
```

未携带密钥时预期收到认证错误；若仍为 451 或代理连接失败，不能开始 Jev 实验。

```bash
export HTTP_PROXY=http://127.0.0.1:17897
export HTTPS_PROXY=http://127.0.0.1:17897
export NO_PROXY=127.0.0.1,localhost,::1
```

现有 httpx 客户端默认读取代理环境变量。`NO_PROXY` 保证 Qwen 本机服务继续走回环直连。变量应设置在执行 Jev 的进程中，不修改全局 shell 配置。API 密钥单独通过环境变量注入，不写入代理配置。

隧道就绪后必须重新执行带认证的模型列表和小量接口验证。实验环境的 Jev network_path 应记录经 Windows 本机代理的实际拓扑；其端到端延迟包含 SSH 和代理链路，不能继续标作服务器直连。

停止本机命令使用 Ctrl+C；停止后服务器代理端口会失效。正式运行期间本机需要保持开机、联网且代理可用。
