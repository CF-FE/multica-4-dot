# 后端接入决策 · v0.2 提案

这是对 v0.1 的增量收敛：不改变部署落点、生产巡检和权限。当前只交付 Skill 与参考资料，未接实际实例、未增开插件权限。

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
