# win-work Hermes 共享 Decision Service OAuth

在 `cloud-work` 为 win-work Hermes 角色挂载工作区 MCP `decision-service-hermes`。有需要时再挂载 `decision-service` Skill。挂载权限由 Multica 管理。已经挂载的同一 Windows 账号下的 Hermes 角色以同一个已授权 GitHub 身份调用该服务。

## 维护

- 在 win-work 保留 `%USERPROFILE%\.multica\integrations\hermes\shared\decision_service_bridge.py` 和相邻的 `decision-service-tools.json`，源脚本为本目录的 [decision_service_bridge.py](decision_service_bridge.py)。工作区 MCP 以 stdio 使用 Hermes 受管 Python 和参数 `-I -B -u <脚本绝对路径>`。Hermes 升级替换受管解释器时，核对工作区条目的解释器路径再用新 Run 验证。
- OAuth 由官方 Hermes profile `multica-decision-service` 持有。安装时把原 profile 的 `mcp-tokens` 整个目录在同一 NTFS 卷重命名，校验文件 ID、大小、所有者、所属组和 DACL，保留一份登录状态。适配器把这个 profile 用作 MCP 子进程的 OAuth 目录。角色的 Hermes home 仍按 Multica 的原配置取得，包括各自的任务会话和记忆。凭据目录继承 Windows ACL，访问边界是宿主账号及管理员等获准主体。
- 工具发现使用上次经认证读回的 `tools/list`，缓存只包含工具说明和输入结构。每次工具调用实时通过 Hermes 原生 OAuth 客户端发到 Decision Service。工具结构变化时，用当前受管 Python 执行 `-I -B <脚本> --refresh-schema`；成功后原子替换缓存。服务改变工具名时，要同步更新脚本内的工具清单。现有 Hermes OAuth provider 以 Windows 文件锁协调跨进程续签，持锁后重读凭据。
- Hermes 为超过模型工具名长度限制的 `record_decision_feedback` 生成带哈希的短名。按当前会话显示的工具说明识别。

## 验收

2026-11-20 在 `Multica 运行时验证` 项目中，知识管理员和新建的临时私有 Hermes 角色各进入新会话，各用一个不同且未使用的请求号调用一次 `get_decision`，均收到预期的业务返回 `not_found`。[知识管理员 CLOU-36](http://10.207.56.3:3000/cloud-work/issues/CLOU-36) · [临时角色 CLOU-37](http://10.207.56.3:3000/cloud-work/issues/CLOU-37)

## 撤回

单独撤销某个角色时，禁用该角色的 `decision-service-hermes` 挂载，新会话据此移除工具。撤回整个迁移时，等已挂载角色的相关 Run 结束，关闭共享挂载，把 `mcp-tokens` 同卷重命名回 `multica-knowledge`，恢复知识管理员原来启用的 `decision-service` 工作区挂载以及指向 `%USERPROFILE%\.multica\integrations\hermes\decision_oauth_bridge.py` 的角色级 stdio 配置，再开新会话核验。
