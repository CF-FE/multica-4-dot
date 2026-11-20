# Multica Backend 云端 Dot 接入素材

本目录用于本地审阅。目标是让云端 Dot（G8）找到已接入实例中的项目与现任协调员，核查原生记录，并在交办动作经授权、兼容验证和实际发现后沿同一请求交办和对账。Multica 的真实 HTTPS MCP 入口、OAuth、原生 App 登记和目标 Dot 联验均待取证。

| 素材 | 用途 |
| --- | --- |
| [连接登记表](examples/connection.json.example) | 从部署方和原生管理面核读后填写，供 ChatGPT 自定义 MCP 表单使用。空值表示待核。 |
| [原生更新包样例](examples/native-update/) | 展示 portable 清单、Codex 兼容清单和原生 App 绑定的文件形状。包名与版本是样例，App ID 留待原生登记后读回。 |
| [Multica Dot Skill](multica-backend/skills/multica-dot/SKILL.md) | 云端 Dot 的发现、交办、同请求对账与汇报指引，随包携带[对账参考](multica-backend/skills/multica-dot/references/reconciliation.md)。 |

## 装配方式与实证

2026-11-20 通过 Plugin Creator 只读回查，Task Mailbox 和 Decision Service Cloud 的当前发行均为 `USER / PRIVATE`、`1.0.2`。两个发行都包含 `plugin.json`、`.codex-plugin/plugin.json`、`.app.json` 和各自的 Skill。每个发行的两份清单拥有一致的包身份、版本和展示元数据，均引用其原生 App 绑定。发行包内没有 `mcp.json`。目标会话调用另由既有验证记录证明，本次取证未重跑。Task Mailbox 初版 portable MCP 包曾显示仅限桌面并已卸载。后续原生 App 在云端 Dot 取得身份、查询和原件回程证据。Decision Service 的原生 App 加挂 Skill 后，云端读回了与 REST 相同的决策记录。[Task Mailbox 验证](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/docs/verification.md) · [Decision Service 安装](https://github.com/CF-FE/decision-service/blob/main/docs/plugin-installation.md) · [Decision Service 联验](https://github.com/CF-FE/decision-service/blob/main/docs/evidence-and-open-questions.md#当前交付边界)

1. **核部署。** 由服务维护方提供已验证的 HTTPS Streamable HTTP MCP URL。验证 `initialize`、工具清单、OAuth 受保护资源及签发方元数据、PKCE `S256`、令牌受众和作用域。OAuth 客户端方式（CIMD、DCR 或预登记）取双方已实测的设置，回调取宿主实际值。批准后在 ChatGPT 网页的 **插件 → ＋ → 添加自定义 MCP 服务器** 使用真实 URL 和 OAuth，选择 **创建为插件**，安装并用目标身份完成授权。上游 Multica REST origin 与服务端 PAT 留在服务端。登记表的私有填写件和授权信息留在受控位置。[官方连接流程](https://developers.openai.com/api/docs/guides/custom-mcp-server#how-to-use) · [官方 OAuth 要求](https://developers.openai.com/plugins/build/auth) · [项目身份边界](../docs/decisions/002-identity-and-workspaces.md)
2. **沿原发行加挂 Skill。** 从同一原生插件读回当前 release ID、现有清单和 `.app.json`。保留实际包名、展示元数据、App ID、连接及受众。以现有版本为基准提升补丁版，同步根 `plugin.json` 和既有 `.codex-plugin/plugin.json`。前者用 Agent Plugins 1.0 的 `extensions.com.openai.apps`，后者沿用原生 `apps` 和 `skills` 路径。把 `skills/multica-dot/` 连同 `references/` 复制到更新包根的 `skills/`。同组织已验证的更新包由根 portable 清单、兼容清单及 Skill 组成。Plugin Creator 按原 release ID 覆盖更新，沿用当前发行的 `.app.json`。样例展示它在更新后的最终发行中的位置。完成后读回同一个插件、当前发行、App 绑定与 Skill，核对引用均可解析。[官方原生插件流程](https://developers.openai.com/plugins/build/plugins#create-and-test-a-plugin-locally-with-an-mcp-server) · [官方包结构](https://developers.openai.com/plugins/build/plugins#plugin-structure)
3. **用目标 Dot 验证。** 在原生 App 详情刷新和核对工具开关，再在目标云端会话显式选中插件、加载 Skill，记录当前发行、已发现工具和实际调用身份。先在获准的隔离实例做只读：查两个已接入项目、同属的 Issue / Run，并验证越界与无权限情形被拒。核运行版本和每项兼容证据后，单独获准的写入样例才试一次交办，按同一 `request_id` 重查及模拟丢响应，核原 Issue 只有一张、Run 数符合预期。另核静默备注零额外 Run、复审的实际工作流触发，以及约定的原信箱结果版本、摘要、原收件人 ACK 和项目验收。详见[集成验收 G–K](../docs/multica-backend-tasks.md#集成任务)。

## 使用边界与版本

云端插件用于分发 Dot Skill 并绑定认证的 MCP。[服务端设计](../docs/decisions/001-dot-multica-gateway.md)由 MCP 将获准动作映射到固定版本的 Multica REST，并保存派发回执，模块进度见 [mcp/](../mcp/README.md)。原生 [Multica 后端 Skill](../skills/multica-backend/SKILL.md) 由 Multica Agent 的运行环境加载，提供该岗位的 CLI / REST 操作指引。Task Mailbox 保管原件、结果和读确认，Decision Service 仅在授权范围内提供有限选择及反馈记录。

包发行、工具发现和上游兼容分别核对。2026-11-20 的公开发行检查以 `v0.11.0` 为部署比较基线，`v0.11.1` 为最新正式发行及待验证候选。生产最近核实的应用镜像标签为 `v0.11.0`，本次检查的当前生产版本、候选 MCP 读写兼容性为 `UNKNOWN`。公开发行、组件测试、某版本的读取资格与写入资格分别取证。发生未知、权限变化或副作用变化时暂停该动作，继续使用已验证且仍获准的能力。[版本记录](../compatibility/multica-releases.json) · [兼容验证](../docs/decisions/005-upstream-compatibility.md) · [候选正式发行](https://github.com/multica-ai/multica/releases/tag/v0.11.1)

### 本地检查

- 用 `python3 -m json.tool` 逐个解析 `examples/` 下四个 `.json.example`。核 portable `$schema`、`extensions.com.openai.apps`、兼容版 `apps` 及 `skills`，以及两个清单的共同元数据。`./.app.json` 对应发行根目录，样例保留 `.example` 后缀。生成正式更新包时以真实发行的清单和引用路径为准。
- 用 YAML 解析器核 Skill 的 `name` 和 `description`，核名称与目录相同、相对链接在包内可读。审阅 Skill 中的能力描述，实际调用名及入参以目标发行的工具发现为准。
- 真实 URL、OAuth 授权、Multica App 发行号、Dot 工具清单、原生和信箱回执属于线上证据。此目录的检查只覆盖素材和格式。
