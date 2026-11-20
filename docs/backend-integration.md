# Multica Backend MCP 决策与任务

云端 Dot 直接操作 Multica 的完整方案由以下五项决策共同定义。各项状态见正文。跨仓的信箱、岗位和基础设施约定仍由原记录维护。[任务、依赖与复核](multica-backend-tasks.md)

| 决策 | 回答的问题 |
|---|---|
| [ADR-001　Dot 直连与组件分工](decisions/001-dot-multica-gateway.md) | 为什么建独立 MCP，哪个系统持有项目、指令、Run 和结果 |
| [ADR-002　身份与工作区](decisions/002-identity-and-workspaces.md) | G8 如何取得并使用跨项目业务权，新增工作区、任命或换任时如何找对人 |
| [ADR-003　命令交付与运行控制](decisions/003-command-delivery.md) | 怎样处理重复交办、响应丢失、静默备注、改派、取消和重跑 |
| [ADR-004　跨端报告与恢复](decisions/004-reporting-and-recovery.md) | 如何回原 job，如何识别未受理、运行异常、待汇报、已读与待验收 |
| [ADR-005　上游版本与兼容](decisions/005-upstream-compatibility.md) | 如何发现正式发行、复核受影响的能力、升级和回退 |

## v0.2 历史提案

以下保留 v0.2 当时以只读查询起步的依据。此后的实际部署、回执和角色变更见[工作流实施记录](workflow-reporting.md)。

## REST 会更稳吗？

| 方式 | 适用 | 反证 |
|---|---|---|
| 官方管理 CLI | 首轮人工校验、快速定位工作区与对象、人工排障 | 受 CLI/服务器版本、profile、输出和退出码影响；stdout 不是长期接口契约 |
| 固定 REST 适配器 | 长驻 MCP 的身份核验、精确 Issue 与 Run 只读 | 少一层进程和解析，但源码路由无独立稳定承诺；配置、鉴权、字段与分页每次升级都要回归，不能宣称整个 API 更稳 |
| Daemon 内部协议 / 浏览器入口 | 已授权 worker、人工操作 | 内部协议版本、会话、角色与执行耦合；不作为通用控制 API |
| 把全量 CLI 包装成 MCP | 覆盖看上去完整 | 把秘密读取、删除、运维和执行混入工具暴露面；禁止通用命令 passthrough |

**建议：CLI 先验证，REST 窄接入，CLI 只作人工回退。** 首期保留 `get_issue`、`list_issue_runs` 和按同 Issue 匹配的 `get_run`；固定白名单 workspace，workspace 枚举和 runtime 状态不是必需则不开放。输入仅 ID 与有界分页，输出是白名单字段、来源/时间、分页边界。锁定服务发行版与镜像；先用 fixture 验字段，再用隔离实例跑身份、跨工作区拒绝、分页、超时和升级兼容。某个 REST 操作尚无契约时就标记不支持，不能自动用 CLI 或浏览器绕过权限。CLI 全量目录用于选型与覆盖审计，不是工具权限表。详情见 [Skill](../skills/multica-backend/SKILL.md) 和 [认证与调用](../skills/multica-backend/references/access.md)。

## 各系统只负责一件事

| 系统 | 权威状态 | 接入建议 |
|---|---|---|
| Multica | Issue、Run、绑定的 Runtime、执行状态 | 执行面；不把结束状态当验收 |
| Task Mailbox | 原任务、结果版本及读回 | 回执主渠道；接入、巡检不变 |
| Decision MCP | 对有限问题的决策记录、建议与反馈 | 只在真有多项合法候选且有授权时调用；规则确定的流程直接按规则 |
| GitHub Projects | 跨项目里程碑、Issue/PR 链接、验收看板 | 保留现有插件和只读巡检；不是 MVP 依赖，不参与派发；不双向同步。试点可只挂链接。若后续证明无人使用或 Multica 足以覆盖组合视图，再另议移除 |
| Hindsight | 设计和已验证经验 | 作为知识索引，不作队列、水位或验收凭据 |

### Decision MCP 如何用，何时不用

复用 [CF-FE/decision-service v1 合同](https://github.com/CF-FE/decision-service/blob/main/docs/api-contract.md)；不在 Multica 插件里复制逻辑或凭据，不给 Decision 服务 Multica 写权限。先过滤权限、候选机器能力和业务硬规则，冻结合法候选、任务原引用和状态快照，保存稳定 `request_id`。必要时才用 `evaluate_decision`，响应未知按同 ID `get_decision`；足够的输入用 `recall: skip`，需要记忆时只用明确授权的 bank。读取成功不表示可执行。

只有 `complete + suggested` 且命中冻结候选，才能进入**独立的授权与时效复核**；建议不是权限。拒答、缺结果、状态过期或要求评审时不自动派发、不换键盲重试，走原流程的人工/规则回退。经授权执行后，从真实系统读回原 Run 与结果，再由原执行者按合同提交应用/结果反馈。区分建议、已应用和运行事实，不用推荐的 runtime/model 填未知实际值。

## 最小落地顺序

1. 固化现有授权、版本基线与 CLI/REST 只读契约，拿同一个隔离样本比对。
2. 先接原 Task Mailbox 回执；验证一个样本就够，不让 Decision/Projects 成为任务能否完成的前置依赖。
3. 只有发现真实的多候选决策问题，再试一条 Decision MCP 旁路；故障时不阻塞原业务回路，不绕过审批。
4. GitHub Projects 起初仍是人工/原有只读视图；只有明确字段所有者、更新权限和去重规则后，才另行评估单向摘要更新。事件唤醒也是另行授权的增强项。
