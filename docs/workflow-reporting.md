# Multica 工作流、通知与跨端汇报方案

2026-11-20 · 已采纳，适用 Multica v0.11.0。公子明确直接拆卸 Mac 协调桥，腾讯云异常补报独立推进。工作流由 Multica 组织和运行，Task Mailbox 的 PostgreSQL 18.7 部署在 win-work。配置与交付分别通过运行回执验证。

当前工作区的协调入口是 **Mike**。在 `cloud-work → 智能体 → Mike` 可发起对话或从所属项目任务指派给他。岗位绑定与能力核验见[工作区协调员登记](harness-role-guide.md#工作区协调员-mike)。桥退役与异常补报的决策归属见 [Task Mailbox ADR-001](https://github.com/CF-FE/task-mailbox-mcp/blob/main/docs/decisions/001-task-collaboration-platform.md)。

## 推荐方案

G8 与所有工作区协调员的职责、决策时机、指令和回报格式以[职责与协作规范](../skills/workspace-coordination/SKILL.md)为准。本方案记录通路设计与实际验证。

任务从所属 Multica 项目进入。日常分工、执行、返工和面向公子的通知都在原 Issue 或原聊天线程完成。只有约定向云端 Dot 汇报的事项才进入 Task Mailbox。对这些事项，**协调员解释工作结果，一个独立于 Worker 的程序核对运行事实并补报异常**。即使 Worker 来不及说最后一句话，协调方也有证据可查。

| 收件人或场景 | 触发与交付 |
|---|---|
| 项目内执行与复审 | 用项目工作流把任务交给执行者和复审者。并行子任务按阶段组织，可在父 Issue 设置 `--until-children-done --stage N`，让协调员在截至该阶段的子任务都关闭后复核产物。需要等某个具体 Run 时，由协调会话用 `chat wakeup create --until-run <Run UUID>` 跟进成功、失败或取消，回查该 Run 和产物。 |
| 公子需要介入 | 需要决定时，在原任务写明问题、可选动作、等待谁，并 @ 对应成员。订阅任务会收到运行失败等通知，状态变更通知需开启。若从已接入的聊天渠道发起，协调员可回原线程汇报。普通工具调用和中间日志留在 Run。 |
| 云端 Dot 需要进展或行动 | 只为约定的项目和任务报告阻塞、待验收或结果。每条都能回答“发生了什么、证据在哪、接下来谁做什么”。Dot 按项目查阻塞或任务轨迹。有原信箱委托时，按原 `job_id` 取结果版本。要求即时叫醒 Dot 的任务另验实际通知渠道，记录入库、消息送达和 Dot 读回三个时点。 |

[任务唤醒与阶段条件](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/issue-wakeups.zh.mdx) · [会话唤醒与 Run 条件](../skills/multica-backend/references/access.md#收件箱与会话唤醒) · [收件箱与订阅](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/inbox.zh.mdx) · [聊天渠道的回复路径](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/channels.zh.mdx)

例如，三项子任务中有两项交付、一项在复审时缺附件。公子在原线程应看到一条可行动的汇报：“两项已通过复审，第三项缺附件，已交回执行者补交。当前无需您处理。” 如果补交需要公子选择授权范围，协调员再单独 @ 公子，给出选项和原任务链接。Dot 可从同一任务轨迹了解变化，日常进展集中在原线程。

## 取舍

| 路径 | 值得采用的地方 | 代价与选择条件 |
|---|---|---|
| 仅用 Multica 原生功能 | 内部任务从分配到汇报均有原始记录，部署成本最低。 | 适合收件人都在 Multica 或已绑定聊天渠道的任务。Dot 若要独立查历史回执，还需要跨端读回路径。 |
| 协调 Agent 经 MCP 回报 | 工作区登记一次，分给协调 Agent 即可。能说明交付质量、阻塞原因和需要公子决定的事项，适合先走通真实样本。 | 需要该身份在实际 harness 中完成 OAuth 并取得项目上报权限。协调 Run 也可能失败，单靠它无法保证发现漏报。 |
| 增加 Multica 来源适配器 | 小程序按指定项目读取 Issue 和 Run，把有外部收件人的变化写入 Task Mailbox 现有观测接口。Worker 退出后仍可工作，无需为每条状态变化启动模型。 | **推荐作为正式跨端汇报路径。** 新增成本集中在一个服务、来源凭据和少量待确认投递记录。交付物是否齐全、下一步需要谁决定，仍由协调员说明。 |
| 重构 Task Mailbox 或全量镜像 Multica | 如果将来多套执行系统都需要统一订阅、主动投递、逐收件人送达追踪，中心服务可以统一承载这些能力。 | 当前已有观测去重、版本化结果和精确读回。优先复用，等试点出现现有合同确实表达不了的需求，再针对该能力改造。 |

## 跨端交付怎么工作

1. **确定谁要收。** 普通 Multica 任务只在原项目流转。需要给 Dot 看但没有原信箱委托的，用约定的 Task Mailbox 项目和任务标识发布观测。有原委托的，在同一 Multica Issue 留下原 `job_id`，把工作区、项目、Issue、每次 Run 和原任务对应起来。返工用新的 Run 引用，保留历次结果。Dot 发起的试点先由获授权的协调员在 Multica 核读并绑定原 job。若要让 Dot 的来件自动建单，可再用 Multica 自动化收取指定收件人的来件，每个授权 job 只交一个派发者处理。建单响应丢失时，先按绑定回查原 Issue，关联不明就挂起核对。[项目归属](../skills/multica-backend/SKILL.md#任务项目归属) · [原信箱合同](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/SPEC.md)
2. **保存事实和判断。** 适配器以专用来源身份，通过 HTTP `POST /mailbox/api/v1/observations/batches` 报告读自原 Run 的状态及证据引用。例如查到 Run 失败且无交付记录，适配器报告“运行失败，尚未找到交付物”。协调员可用 MCP 的 `publish_observation_batch` 补充原因和接手人。对原信箱委托，协调员负责核过产物后调用 `publish_result` 提交结果版本，适配器只写观测。负责人验收沿原项目流程记录。有正式 GitHub Project 关联的任务沿用原引用。[Multica 查询入口](../skills/multica-backend/references/access.md#最小-rest-接口) · [观测来源与权限](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/docs/implementation/platform-v1-contract.md#来源接入合同)
3. **避免漏报和重复。** 第一版适配器只回查已登记且仍需跟进的任务，用 Issue 下的 Run 列表找到完整 Run UUID，并核对公开给该收件人的字段。在适配器本机持久保存稳定事件 ID、批次 ID 及原内容，确认信箱已持久化后再标为送达。超时先查原批次回执。信箱结果以原 `event_id` 重传同一份内容。Dot 取到精确版本和摘要后才写读确认。如此，Win 数据库短时不可达只延迟回报，恢复后补传原件，工作流继续沿 Multica 的原状态运行。[批次与回执](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/docs/implementation/platform-v1-contract.md#来源接入合同) · [结果版本与已读接口](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/server.py#L141-L165)
4. **按需缩短延迟。** v0.11.0 的官方插件演示了 `issue.status_changed` 出站 HTTP hook。若回查间隔影响公子处理阻塞，可给适配器加入验签的事件入口，收到后立即核原对象，并保留对待办的定期回查。一个 Issue 可以经历多次 Run，Issue 状态不变时也可能有 Run 失败。目标实例上 hook 的实际覆盖、重试和送达仍要以试点取证。[固定版本事件示例](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/examples/plugins/deploy-sentinel/multica.plugin.json#L95-L103) · [签名与重放处理示例](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/examples/plugins/triage-notify/README.md)

如果 Worker 的 Run 已结束而协调员也退出，独立程序仍可报告该 Run 的终态。Dot 沿原 job 另外读取与该 Run 对应的结果版本。缺回执时显示“运行已结束，交付待核”，由协调员核对原件后补报。这样即使出现两次故障，仍能区分需要重新执行的工作和只需补交的报告。

## 部署与旧桥退役

建议将适配器放在腾讯云，靠近 Multica API，通过经验证的 HTTPS 路径向 Vultr 的现有 Task Mailbox 入口上报。选址依据是适配器频繁查本地 Run，只在出现需汇报的变化时跨机发送。适配器的 Multica 身份只需读取约定项目的执行证据，写信箱时使用限定项目的来源凭据。腾讯云不依赖工作机的 Verge 登录 GitHub。协调 Agent 的 MCP OAuth 在实际运行它的工作机上验证。Vultr 继续服务云端 GPT，信箱业务库保留在 win-work，Multica 自身使用腾讯云的 PG17。四台主机已建 EasyTier 私网，但腾讯云到 Vultr 的服务级可达性、TLS 和投递延迟仍需从适配器所在环境测试。[腾讯云部署基线](tencent-upgrade.md) · [信箱部署记录](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/docs/verification.md)

Mac 可继续作为 Multica 执行机，本地只读看板可单独使用。已决定一次拆除桥专属启动项、钩子、程序和调用旧 socket 的 bridge-pump，归档历史台账。11 月 20 日原信箱已核至本机游标 24，之后无新增事件。本机待发报告与观测缓冲为空，仍有一份已发送的协调结果缺少精确读确认。原收件方可在旧桥退役后按原版本核读。切换时的新来件与原审批交接按 ADR-001 局部修订处理。[协调桥收件机制](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/mac/README.md) · [独立看板](https://github.com/CF-FE/task-mailbox-mcp/blob/0e6bda47ee2caa7d01c7adff546dd05efad42d9c/docs/verification/local-monitor.md)

## 首轮试点与判定

选一个有外部收件人的试点项目，协调员和 Worker 优先使用 win-work 上已登记的运行时，以便验证新链路可独立于 Mac 协调桥运行。先在 Workspace MCP 库登记 Task Mailbox 并仅分给该协调员，在新 Run 核对 `whoami`、原 job 读取和一次真实上报。再在同一试点项目核验以下场景。[工作区 MCP 分配](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/agents-create.mdx#L149-L195)

| 场景 | 从收件方判定是否通过 |
|---|---|
| 交付成功 | 源 Run 有可核对产物，协调员发布到正确 job，原 Dot 读到相同版本与摘要。记录 Run 结束、持久化、Dot 读回的时间。 |
| Worker 提前退出 | 选一个已知失败的测试 Run，交付前没有 Worker 报告。独立适配器仍能定位 Run 并发布失败观测，Dot 可查到失败原因或原错误引用。接手人尚未确认时显示待定。 |
| 投递中断或重复 | 在隔离环境模拟服务端已收、客户端未收到响应，再重启发送端。原批次可查，重复发送后仍只有一条业务事件，原任务的执行次数不增加。 |

第一项验证通过即可先用原生通知和协调员回报。后两项通过后，再让适配器承担无人值守异常汇报。若试点只有内部读者，原生路径已经足够。若 Dot 读回太晚，用上述三个时间点定位延迟，再决定增加事件触发、调整巡检，还是接入即时通知渠道。

## 2026-11-20 实施核对

Mac 协调桥的启动定义、专属 bridge-pump、7 条钩子和活动运行环境均已拆除。看板依赖的 CA 证书保留原路径。腾讯云已安装独立补报程序和 systemd 单元，Vultr 已签发仅覆盖本试点项目的观测写入身份。生产定时器已启用。专用读取身份只能通过本机 HTTP 入口查询试点项目中已登记的 Issue 和 Run，字段来自 Multica PG17 的受限视图，并已与 v0.11.0 正式 API 对照。北京时间 14:08:05，原 CLOU-20 首轮 Run 的终态观测取得信箱水位 278 的持久回执。14:09 的自然周期再次成功，沿用同一回执。[生产验证与维护说明](tencent-run-reporter.md)

CLOU-20 在一张卡和一个信箱 job 上完成验证。首轮发现 OMP 未完成 Task Mailbox OAuth，Mike 在原卡记录阻塞。授权后沿原卡开启新 Run，经 OMP 的 `xd://` 工具入口调用 `whoami`、`get_job` 和 `publish_result`。发送侧工具回执（消息序号 32、46、53）和独立信箱读回相符。北京时间 11:54:57 保存 v1。报告核实 CLOU-4 的结项证据，并标明历史回执与本次直接观察的区别。

12:02:02（北京时间）信箱保存该 job 的 `RESULT_READ_ACKNOWLEDGED`，与 Mike 发布的版本 1 及 SHA-256 完全匹配。原 G8 在本件验收提示后读取 v1，准确复述第 12 条消息写入结项评论、第 16 条消息将卡片改为 done，并由其原生会话写入精确 ACK。本轮覆盖真实收件和读确认，自动唤醒时效仍待单独验证。

公子随后确认 G8 默认可读写全部现有和未来项目。云端连接读回 `all_projects: true`，查询到了原生观测 278，并以自报来源写入和读回业务观测 279。协作规范 1.0.0 的登记记在同一任务轨迹的游标 280。G8 与 Mike 使用的 Decision Service 由外网 Vultr VPS 提供。规范编制时，云端真实决策在“逐步骤通报、按实质变化和检查点通报、只在阶段结束通报”间建议了第二项，编制方复核并采用。

CLOU-21 验证反向交办。G8 从原会话投件，获授权的操作者将该 job 关联到一张 Multica Issue 并交给 Mike。Mike 的 OMP Run 核对了实际加载的规范 1.0.0、分配给本人的 Decision Service MCP 和一条已存决定。北京时间 14:41:11，信箱保存原任务结果 v1，复核方独立读回同一摘要。Mike 还留了一条回执引用评论，并把 Issue 转到 `in_review`，触发项目原有自动复审。复核方在追加 Run 派发前按本单限定范围取消了它，原 Mike Run 已完成。云端独立建单及本单原 G8 的精确已读回执仍待验证。

规范随后原位更新到 1.1.0。复核方核对工作区 Skill 全文字节、Mike 的既有分配，并在同一规范轨迹读回游标 281。新版本把决策服务列入项目负责人任命时的默认装配，现有试点项目尚未登记负责人。[职责与协作规范](../skills/workspace-coordination/SKILL.md)

## 运行时验证项目的按需决策工作流

2026-11-20，「Multica 运行时验证」启用命名工作流 **运行时验证 · 按需决策**（`4a2e1770-6805-458e-9fca-13a026a21a6d`）。实际配置包含原来的七个状态和新状态「待决策」（`started_2`），处理人为 Mike。切换预检和实际回执均为 18 张原卡、0 条状态迁移。其他项目仍可选择工作区 Default。协调规则由 `workspace-coordination` 1.2.0 维护。[试点 CLOU-22](http://10.207.56.3:3000/cloud-work/issues/CLOU-22) · [岗位与交接规则](../skills/workspace-coordination/SKILL.md#当前-issue-的下一步由谁执行)

| 做法 | 收益 | 在本项目的代价 |
|---|---|---|
| 每个阶段都请求决策 | 每次选择都有统一记录 | CLOU-3 的返工对象、复审人和结束条件已有明确规则。重复请求会增加一次服务依赖和等待，也可能让建议偏离验收条件。 |
| 在原卡按需联系负责人 | 改动少，适合偶发判断 | `blocked` 也可能表示等凭据或等指定验收人。单看这个状态无法区分谁应接单，普通备注也未必唤起协调员。 |
| 仅在有实质取舍时进入「待决策」 | 状态变更能原生派给协调员，候选可以对应不同的执行人、复审或交付路径 | 调用方须在交接前保存原执行人和可行动作。项目使用独立工作流后，工作区默认审查规则的后续修订需要对照同步。 |

执行者进入「待决策」前在原卡列明目标、当前事实、每个可行选项的动作与接手人、验收条件和回程。只改状态即可触发接手。Mike 在原授权内取得建议，读回后复核当前 Issue，再执行一个候选：例如将实现交回原执行者、将已有候选交独立审查、就地核查并按原约定交付。等待公子授权或明确暂停的任务继续按原等待条件处理。没有固定的决策出口。协调员分别记录推荐的动作、实际采用的动作和后续结果。原任务规定的独立复审及最终验收继续由各自责任人完成。

已有责任人同时具备决策权限与工具时，可以在当前 Run 就地选择和回填。需要另一位责任人接手、或需要在看板上单独跟进的取舍，再使用「待决策」。普通执行者遇到凭据缺失时直接交给凭据持有人，重复咨询决策服务无法解决这个阻塞。

首个试点用两个历史案例构成一次真实选择。选 CLOU-3 就核查返工证据并交独立复审，选 CLOU-21 就核查信箱交付及多派审查的原因，向发起者回执。「待决策」自动派发、建议读回、实际走到哪条分支、`application` 与 `result` 反馈分别核验。后续复盘看实际改变了哪些动作、耗时、重复派发次数，以及建议失效时是否沿原卡恢复。需要回到 Default 时先用 `project workflow set <project-id> default --dry-run` 核对处于自定义阶段的任务，再按各卡实际交接情况处理。

**首次实单。** CLOU-22 只改变状态，平台即把卡交给 Mike，并在 15:00:33（北京时间）启动 OMP Run `01a1f7c1-c36d-7db3-bd5b-b42deeee6303`。该 Run 加载规范 1.2.0，保存了候选快照。请求使用真实项目 UUID 和 `recall=skip`。`evaluate_decision` 返回 `forbidden_scope`，按原 `request_id`（`multica-cloud-work-handoff-pilot-20261120-01`）读回为 `not_found`。Mike 在原卡记录错误并转为 `blocked`，Run 随后结束。原卡共一个 Run，两项候选均未执行。Vultr 部署配置也确认该项目未列入现有 OAuth 身份的项目范围。此测验证了按需派发和拒绝后的处理；生成建议、按建议分流及两类反馈待项目授权后用同一请求验收。[CLOU-22 原始回执](http://10.207.56.3:3000/cloud-work/issues/CLOU-22)

### 决策服务的项目与 Agent 授权

公子随后授权所有 Multica 项目，以及已经获配并启用决策 MCP 的 Agent。工作区负责人分配 MCP，运维按 Agent 的原生 UUID 配置独立服务身份。项目范围取自获准 Multica 实例的实际项目清单，包括已归档项目。决策服务复用现有 HTTP MCP，工作区条目 `decision-service-agent` 的 Authorization 头从 Agent 进程的 `DECISION_AGENT_TOKEN` 取值。共享 GitHub OAuth 的权限另行管理。每个新身份的 Hindsight bank 清单为空。2026-11-20 实例中有一个工作区、一个项目、十二个 Agent，其中 Mike 符合条件。首次配置及再次同步均已读回。[协作规范](../skills/workspace-coordination/SKILL.md)

新建项目或给 Agent 分配决策 MCP 时，管理员在有权查看全部目标工作区的机器运行[授权同步程序](../deployment/decision-access/sync-agents.py)。它列举项目，只给指定工作区内已启用决策 MCP 的 Agent 发放独立凭据，并逐项回读服务端清单和 Multica 挂载。已有凭据复用。示例使用本机 SSH 隧道，第一条命令保持在独立终端。先查看覆盖数，再加 `--apply` 生效。多个工作区按工作区分别同步角色。新增角色首次在其实际 harness 验证 HTTP Authorization 环境变量展开和一次实际调用。

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18080:127.0.0.1:8080 tencent
python3 deployment/decision-access/sync-agents.py --workspace e25be43b-82b6-419d-9085-bb5c5700b1af --server-url http://127.0.0.1:18080 --decision-ssh vps-herdr
```

退任时先禁用该 Agent 的决策 MCP 条目，再在同一命令中加 `--revoke-agent <agent-uuid> --apply`，撤销服务端凭据并从角色环境删除对应变量。服务端策略发生变化时会重启 Decision Service 并检查健康，健康检查失败则恢复原配置。授权同步由项目创建和角色任免的操作者触发。系统管理员依照宿主与 Multica 管理权限维护凭据。
