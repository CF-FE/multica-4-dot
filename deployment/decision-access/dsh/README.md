# win-work DSH 共享 Decision Service OAuth

在 Multica 的 `cloud-work` 工作区，为需要决策能力的 win-work DSH 角色挂载 **`decision-service-dsh`**。如需决策方法说明，再挂载名为 `decision-service` 的 Skill。新角色在下一次 Run 即可使用同一 Windows 账号保存的 GitHub 授权。取消某个角色的挂载只影响该角色。分别控制角色权限或撤销整份授权时，要区分 Multica 挂载与服务端 GitHub 身份。

## 宿主维护

共享目录是 `%USERPROFILE%\.dsh\multica-oauth\decision-service`。运行时使用已安装的 FastMCP 4.1.6、MCP Python SDK 2.3.0 及本目录的 [decision_oauth.py](decision_oauth.py)。OAuth 凭据及动态客户端注册信息由 Fernet 加密，密钥由当前 Windows 用户的 DPAPI 保护。多个角色同时续签时通过 Windows 文件锁互斥，后取得锁的进程先重读共享凭据。普通查询可并行。[并发续签回归用例](test_decision_oauth.py)

从旧目录迁移时，等相关 Run 结束，在同一 NTFS 卷移动原授权目录，核对文件标识、所有者及 ACL。`py-key-value-aio 0.4.6` 在 `credentials/*-info.json` 的 `directory` 字段保存各集合的绝对路径。须将旧前缀更新到共享目录下对应的实际子目录，保留路径校验。再通过 stdio 列举工具并实际完成查询。2026-11-20 的迁移沿用了辩证复核专员原有的登录。

首次安装或授权失效时，用运行 DSH 的 Windows 账号执行：

```powershell
$python = 'D:/Hindsight/app/.venv/Scripts/python.exe'
$adapter = Join-Path $env:USERPROFILE '.dsh/multica-oauth/decision-service/decision_oauth.py'
& $python -I -B $adapter login
```

用浏览器确认程序输出的授权链接。从 Mac 确认时，将 Mac 的 `127.0.0.1:49328` 通过 SSH 转发至 win-work 的同一回环端口。回调最多等待 15 分钟。出现 `"status": "authorized"` 表示该授权已经可以列出决策工具。

工作区 MCP 以 stdio 调用上述 Python 和脚本，参数为 `-I -B <脚本绝对路径> stdio`。凭据仅由 win-work 的适配器读取。DSH 已选用共享入口的角色应停用此前直接连接同一服务的 HTTP 条目。保留该角色原有的其他 MCP 配置。

## 验收

2026-11-20，「DSH 默认模型验证」从无 Decision 挂载开始，只增加这一项工作区 MCP 后，在新会话调用原生 `get_decision`，对未使用请求号收到业务码 `not_found`。随后移除了它的临时挂载。修正存储索引中的绝对路径后，辩证复核专员也在独立新会话收到同一业务码，并保留原有 Hindsight 只读工具。两个角色都复用了同一份授权。[共享授权验收 CLOU-35](http://10.207.56.3:3000/cloud-work/issues/CLOU-35)
