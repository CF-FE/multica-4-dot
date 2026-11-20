# Multica 角色创建与 Harness 选型指南

在 Multica 新建或调整智能体时，用本文选主机、运行时、工具和验收任务。角色职责取自 Herdr 角色库，宿主能力以目标机器上的实测为准。本文是本仓库的选型主文档，后续直接更新同一文件。当前范围为 `cloud-work` 的 mac-work 和 win-work，按项目约定暂不纳入 Claude。选型基线为 2026-11-18 的 Multica v0.10.0。工作区协调员条目于 2026-11-20 按 v0.11.0 实例核对，本文时间均为北京时间。[角色库索引（1.0.3）](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/docs/worker-library/roles/index.json)

**快速索引**　[找 Mike](#工作区协调员-mike) · [按岗位选](#从角色要交付的结果开始) · [两端版本与实测](#两端实际登记的运行时) · [按架构问题查](#架构比较) · [速度与 Token](#速度与-token) · [实际推理档位](#实际推理档位) · [推荐分工](#推荐分工与换选条件) · [创建与验收](#建一个可以验收的角色) · [按来源查](#资料索引) · [新增或升级](#新增升级或停用时怎样更新本文)

**按 Harness 查**　[Codex](#codex) · [Kimi](#kimi) · [OMP / Oh My Pi](#omp) · [DSH / DeepSeek Harness](#dsh) · [Hermes](#hermes)

## 工作区协调员 Mike

G8 向各工作区协调员交办的统一约定见[职责与协作规范](../skills/workspace-coordination/SKILL.md)。本节登记 `cloud-work` 的现任人员和运行时。

新工作区上线时，由建立者核对本工作区的协调员及原生 ID，向该协调员分配同一份 `workspace-coordination`、适用的后端技能、Task Mailbox 和 Decision Service MCP。可复用服务 URL，OAuth 要在实际调用的身份和运行时完成。登记已接手的原 Issue、可读回的决定和回报作为该工作区的接入证据。更换协调员时，连同在途任务和回程交给新任。

任命项目负责人时也默认装配 Decision Service MCP。先读项目的 `lead_type` 与 `lead_id`。Agent 负责人使用同一工作区已有的 MCP 条目增量分配并读回；成员负责人在其实际客户端接入。公子已就这项业务使用作常设授权。2026-11-20 的 `cloud-work` 盘点中，原生项目的这两个字段均为空。

Decision Service 部署在外网 Vultr VPS，由 `decision-service.service` 监听回环端口 8768，对外服务路径为 `/decision-service/mcp`。2026-11-20 已核对生产单元运行状态和云端决定读回。[服务部署说明](https://github.com/CF-FE/decision-service/blob/main/docs/deployment.md)

**找人入口**　进入 `cloud-work → 智能体 → Mike`。名片登记为“工作区协调员（Chief of Staff）”。跨智能体分工、项目任务派发、阻塞跟进及复审交接找 Mike。需留存的事项从所属项目的原 Issue 交办，验收人仍以原任务约定为准。按 `system_key=mika` 可识别内置岗位，显示名、绑定和可调用范围以工作区智能体详情为准。

**当前绑定与证据**　2026-11-20 回读为 win-work OMP，模型配置 `cli-proxy-chat/gpt-6.2-sol`，允许工作区成员调用，并发 3。CLOU-4 的原卡及回合记录显示，Mike 汇总了多个运行时的结果，指出待补的验收证据，并按公子确认的标准回报结项。建议沿用这位协调员及其原有绑定。Hermes 的记忆与跨会话分诊、DSH 的流程工具可由专项岗位使用。

**能力评估**　Mike 已有内建 Chief of Staff 系统指令和 Multica CLI 操作指引。2026-11-20 已增量挂载 `multica-backend`，任务归属、按 Run 取证、对账和唤醒规则均以该技能为准。工作区 `task-mailbox` HTTP MCP 已分配给 Mike，配置读回为启用。CLOU-20 补齐授权后，Mike 用 OMP 经 MCP 读取身份、按原 job 取件并发布了 v1。信箱已保存相同版本与摘要的独立读确认。OMP 的 Shell 权限还受 Windows 宿主账户影响，现有配置缺少强制工作区写入隔离的证明。[后端技能](../skills/multica-backend/SKILL.md) · [跨端汇报方案](workflow-reporting.md)

## cloud-work 新增专业角色（2026-11-20）

在工作区的「智能体」中按下表名称查找。四个岗位均允许工作区成员调用，并发各为 1。已逐一读回运行时、实际角色指令及工作区调用范围；Dot 专属账号对试点项目的四次指派预览均命中对应智能体。岗位正文固定自 [Herdr 角色库 1.0.3](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/docs/worker-library/roles/index.json)。项目负责人、业务验收与跨端回程按原任务办理。

| Multica 名称 | 角色 ID | 工作内容与验证单 |
|---|---|---|
| 视觉设计师（mac-work Codex） | `workspace_visual` | 视觉候选、可编辑源和导出后的实物检查。Codex 显式指定工作区写入、网络可用、按需审批。CLOU-24 |
| 知识管理员（win-work DSH） | `workspace_knowledge` | 依据原件整理索引和冲突清单。使用 Multica 专用 DSH profile 与项目绑定的 Hindsight。CLOU-25 |
| 产物处理（win-work DSH） | `artifact_processing` | 确定性文件或数据转换，另存输出并核对内容、大小和摘要。CLOU-26 |
| 辩证复核专员（win-work DSH） | `workspace_dialectic` | 对固定方案做对抗、优化与对齐。需声称独立双线时，应有可追溯的两个独立上下文。CLOU-27 |

三名 DSH 岗位使用已有的 `multica` profile 和 `local-gpt/gpt-6.2-sol`。Hermes 的 ACP 工作目录是工具解析起点，当前 `local` 终端继承 Windows 账号权限。知识管理员采用已有 `workspace-write` 策略的 DSH；角色配置读回与宿主级文件隔离的实测各自记录。[Hermes 工作目录与后端](https://github.com/NousResearch/hermes-agent/blob/09ded63/website/docs/user-guide/profiles.md#L239-L244) · [DSH 项目记忆](win-work-hindsight.md)

**上一轮 win-work Hermes。** 原「Hermes 默认模型验证（win-work）」保留原 ID，盘点时空闲，6 个历史 Run 全部终结（4 完成、1 失败、1 取消）。CLOU-4、12、16、19、23 均已结项，无启用中的 Issue 唤醒。CLOU-16 已验证正常 ACP 首轮记忆注入、按 ID 读取与本库留存；CLOU-19 的单行留存已在限制内重交并读回。CLOU-4 曾在 daemon 重启后自动重试但未恢复交付，后来成功的是独立新会话。修复后版本的故障恢复仍需受控演练。未来升级先对照 CLOU-12 的三处源码适配及备份。原验证 Agent 的模型和推理档位继承运行时，角色本身没有另行分配 Multica Skill 或 MCP。[Hermes 接入证据](hindsight-installation-report-2026-11-20.md)

## 从角色要交付的结果开始

| 要创建的角色 | 建议首选 | 什么情况下换选或补验 |
|---|---|---|
| 质量审查员 · `workspace_quality` | **win-work DSH**。沿用原审查员 ID，两份工作流都指派同一角色。角色模型为 `local-gpt/gpt-6.2-sol`，推理档位继承 DSH profile，使用 Multica 专用 profile 的 `workspace-write` 策略。 | 先核原件、候选 Run 和必验产物。审查者须独立于被审版本的制作。旧卡 CLOU-1 至 CLOU-3 的审查由当时的 mac-work Codex 执行。 |
| 研究分析师 · `workspace_research` | **win-work Kimi**。已交付带固定版本源码引用的研究附件。 | 素材只在 Mac 时优先考虑 mac-work Kimi，以同一验收题补一条真实 Run。 |
| 软件实现工程师 · `software_implementation` | **win-work Kimi**。已有小改动和独立回归测试的成例。任务明确指定 dsh-ops 的文件、搜索或 Bash 工具时选 **win-work DSH**。 | 工作要求由系统强制限制写入时，先取得目标主机的边界实测。两位现有 Kimi 角色使用宿主权限的授权仅适用于这两位。 |
| 结构化重构、交互调试 · `software_implementation` | **win-work OMP** 是工具匹配的候选。AST、LSP 和 DAP 可提供结构匹配、引用及断点证据。 | 确认目标语言服务和调试器可用。该岗位目前有固定版本架构依据，项目历史案例覆盖的是宿主运维。 |
| Windows 运维工程师 · `workspace_runtime` | **win-work OMP**。可使用本机 PowerShell、Windows 管理工具和 MCP 服务，已验证提升后的进程身份和工具结果。 | 普通工作区维护可复用 DSH。修改系统文件、安装服务或使用凭据时，按任务给出目标、授权范围、恢复方法及验收证据。 |
| Multica 系统管理员 | **win-work OMP + `multica-backend`**。适合查实例、核对 Run、使用任务内 CLI 回报。 | 涉及 workspace owner 能力时，分别核验操作者与普通 Run 的身份、调用范围和一项可恢复操作。技能、宿主管理员、平台令牌各有独立作用。 |
| 项目知识维护 · `workspace_knowledge` | **win-work Hermes** 已用真实 Multica ACP 任务验证首轮项目记忆和获准的跨库读取。OMP 和 DSH 也有各自的派发与读取回执。 | 需要在宿主中断后无人值守续跑的岗位，仍须单独验证恢复。引用具体历史结论时按原文档核查。[五端安装与验收报告](hindsight-installation-report-2026-11-20.md) |

有可复用角色时，先看它能否交付样本、是否接触过待审产物、权限是否覆盖任务。统一使用一种运行时可减少插件和升级维护，但 Windows 服务、独立审查与特定工具各有自己的验收条件。只有任务确实受数据位置、权限边界、工具或独立性约束时，才值得增加一个组合。以下判断有对应案例，速度、成本和模型质量尚无同题对照数据。

## 两端实际登记的运行时

2026-11-18 17:55 从 Multica CLI 读回运行时、启动入口和角色绑定。下表七个组合当时均为 `online`。截至 11 月 20 日，mac-work Kimi、win-work Kimi 和 win-work Hermes 均有新的 Multica ACP Run，模型、档位及回执见[实际推理档位](#实际推理档位)。在原任务卡的 Runs、工具活动和附件可核对各次证据。

| 主机 | Harness 与版本 | Multica 启动入口 | 当前已证实的最高层级 |
|---|---|---|---|
| mac-work | Codex 0.169.0-alpha.11.1 | `codex app-server` | Multica 独立审查和返工复审，CLOU-1 至 CLOU-3 |
| mac-work | Kimi 2.6.3 | `kimi acp` | 运行时在线，本项目角色任务待验 |
| win-work | Codex 0.162.1 | `codex app-server` | 运行时在线，本项目角色任务及 Windows 沙箱待验 |
| win-work | Kimi 2.6.3 | `kimi acp` | Multica 研究附件、代码修改及独立测试，CLOU-6、CLOU-7 |
| win-work | OMP 18.22.2 | `omp (json mode)` | Multica 运维、平台技能和项目记忆，CLOU-5、CLOU-9、CLOU-10 |
| win-work | DSH 0.2.2-rc.3 | `dsh --profile multica`，stdio | Multica 文件、搜索、Bash、返工及记忆，CLOU-1 至 CLOU-3、CLOU-8 |
| win-work | Hermes 0.19.0（11-18 登记），0.23.2（11-20 实测） | `hermes acp` | CLOU-16 的真实 ACP 新会话已验证首轮注入和跨库只读；故障后自动续跑待验。 |

mac-work 有经过返工复审验证的审查链路。win-work 上的工具、插件和模型配置更齐全，运维及执行角色同时依赖该机 daemon 的 Windows 身份和服务会话环境。在一端验证过的版本、沙箱或凭据迁移到另一端后，需要以另一端的新会话复核。宿主还查到 mac-work 的 Herdr 会话管理器、两端的 Zed 编辑器和 win-work 的 ZCode 3.16.3 桌面应用。ZCode 目前只确认了安装，仍缺可供 Multica 选择的运行时与任务回执。

## 架构比较

同是一次“派任务”，五种 harness 保存的状态、能替换的部件、以及由谁批准工具调用都不同。下表可用来定位需要深读的部分。

| 要比较的架构问题 | 优先阅读 |
|---|---|
| 如何知道审查员读过哪个差异、在哪一轮复审？ | [Codex 的 Thread、Turn、Item](#codex) · [OMP 的分支会话](#omp) |
| 研究与实现能否共用一套引擎，同时各自配置工具和角色指令？ | [Kimi 的三级作用域与 ACP](#kimi) |
| 想换工具、模型接入或记忆插件，改动会牵涉哪些部件？ | [DSH 的 Cordis 插件树](#dsh) · [OMP 的内核与宿主工具](#omp) |
| 换会话后，原始记录、项目经验、操作手册各存在哪里？ | [Hermes 的会话、Memory 与 Skills](#hermes) · [三端 Hindsight 实装](win-work-hindsight.md) |
| 哪一层能限制文件写入，谁会回应权限申请？ | [Codex 的执行沙箱](#codex) · [Kimi 的客户端授权](#kimi) · [DSH 的 Windows 边界](#dsh) · [创建时的核对步骤](#建一个可以验收的角色) |

### Codex

**结构。** Multica 作为客户端，通过双向 JSON-RPC 驱动 `codex app-server`。服务端的线程管理器为每个 Thread 维护一个 Rust 核心会话。Thread 包含多个 Turn，每个 Turn 产生可识别的 Item，例如命令执行、文件变更或回复。模型请求工具后，内核把执行结果送回同一回合。线程存储用 JSONL 保存可重放的历史，SQLite 保存用于查询的线程元数据。[OpenAI 架构说明](https://openai.com/index/unlocking-the-codex-harness/) · [mac-work 对应版本的线程存储](https://github.com/openai/codex/blob/226fa88979b1a9d76dc36f339ee9c5fbdb2c8e7f/codex-rs/thread-store/README.md#L7-L30)

**选型取舍。** 审查员可以沿同一线程定位命令、差异和答复，退回后再对新产物复审。CLOU-3 已走完这条链。代价是必须同时理解客户端审批和宿主沙箱。内核把策略、审批与操作系统执行分层，Multica v0.10.0 会自动回应命令、补丁和部分权限申请。mac-work 审查员显式使用工作区写入、允许网络、`on-request`，其实际人工授权仍要经操作者确认。Mac 默认有全权限回退，Windows 已登记另一版本。凡岗位要求强制文件边界，均在目标宿主新会话中验证一次工作区外临时写入遭拒。[工具与沙箱编排](https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/core/src/tools/orchestrator.rs#L1-L25) · [Multica 沙箱选择](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/daemon/execenv/codex_sandbox.go#L64-L128) · [Daemon 的审批响应](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/pkg/agent/codex.go#L2970-L3004)

### Kimi

**结构。** 现装 Kimi Code 2.6.3 的 TypeScript 内核分为 App、Session 和 Agent 三层作用域。CLI 和 ACP 入口共用内核。一次任务在 Agent 层运行模型与工具循环，内置工具、MCP 和已加载工具进入作用域内的注册表。每个 Agent 的 Wire 日志按顺序追加事件，循环可从相应分支重建历史。权限层对一次工具请求作放行、拒绝或询问的决定，询问如何落地取决于连接它的客户端。[2.6.3 作用域](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/app/scopes.ts#L3-L15) · [工具执行器](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/agent/toolExecutor/toolExecutorService.ts#L90-L124) · [Wire 日志](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/wire/wireService.ts#L73-L154)

**选型取舍。** 一套宿主能给研究角色配引用与附件要求，给实现角色配编辑与测试工具，模型接入和会话逻辑可复用。代价在 ACP 边界。Multica 固定启动 `kimi acp` 并应答工具授权，`cwd` 和角色指令无法强制限制提升后的 Windows 账户。现有两位 Kimi 角色已获准采用指令限定的工作区。CLOU-6 的源码引用可读回，CLOU-7 首次 Run 结束却没有产物，原卡复跑后才得到通过 7 项独立断言的修复。研究和实现可复用这条交付链，有硬隔离或逐次人工审批要求的岗位要另验宿主与客户端。[Kimi 权限决策](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/agent/permissionGate/permissionGateService.ts#L31-L69) · [Multica 的 ACP 入口](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/pkg/agent/kimi.go#L52-L76)

### OMP

**结构。** Oh My Pi 将模型与流式响应、模型到工具的循环、编码会话与工具集分层。应用层使用 TypeScript/Bun，Shell、搜索等能力调用 Rust 原生模块。SessionManager 把会话作为带父节点的 JSONL 日志保存，当前分支决定哪些记录进入下一次推理。Hindsight 是独立的项目记忆后端。Multica 常规任务从 stdin 传入提示、从 stdout 读取 JSONL 事件，需要任务中途补充输入时才切换到 OMP 的 RPC 模式。[代理循环](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/agent/README.md#L34-L94) · [会话分支](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/session/session-manager.ts#L916-L927) · [Multica 启动方式](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/pkg/agent/pi.go#L1190-L1213)

**选型取舍。** 要同时用宿主工具、MCP 和现有技能处理 Windows 服务时，OMP 能把它们放进一次可回看的操作。CLOU-5 实际写入并恢复临时受保护目录，完成了临时 stdio MCP 的握手、列工具和调用。代价是工具批准策略按类别生效，Shell 子进程仍继承宿主身份。安装 MCP、修改系统与管理 Multica 需要分别授予相应能力。CLOU-9 的普通 Run 验证了加载技能、读取和评论，操作者另用 owner 身份完成临时元数据的写入、读回、清理。给角色挂上技能后仍须核验实际使用的令牌身份。[原生 Shell](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/tools/bash.md#L23-L55) · [审批等级](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/approval-mode.md#L16-L27) · [Multica 令牌身份](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/apps/docs/content/docs/auth-tokens.zh.mdx#L78-L84)

**工程工具为何改变任务选择。** Hashline 的 `edit` 引用行锚点，`ast_edit` 通过语法模式匹配、预览并应用结构化改动。LSP 查询符号及引用，DAP 调试器提供断点和栈等操作。v18.22.2 源码列出 14 项 LSP 操作、28 项 DAP 操作。哪种语言或调试器能用，仍取决于项目、已安装服务和握手能力。对于有复现用例的深度 Debug、批量语法重写，OMP 也应进入工程执行岗候选。Advisor 是可选的第二模型，适合高代价、难以及时发现错误的步骤，不能代替有身份与回执的独立审查。[AST 编辑](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/tools/ast-edit.md) · [LSP](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/tools/lsp.md) · [DAP](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/tools/debug.ts#L69-L98) · [Advisor](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/advisor-watchdog.md#L24-L48)

### DSH

**结构。** DeepSeek Harness 通过 Cordis 把 profile 中的 bundles、独立插件和配置覆盖组合成一棵插件树。模型适配器、工具注册表、会话日志，甚至运行模型与工具的循环都由插件提供。工具请求经过校验、策略与审批后才执行。持久会话事件构成模型历史的重建依据，尚在流式传输、没有提交的片段在中断时可能丢失。[固定 RC 的架构](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/architecture.md) · [工具执行顺序](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/tool-execution-pipeline.md#L3-L39)

**选型取舍。** 要求明确到“用哪个工具写、用哪个工具搜索，再用 Bash 验证”的角色，很适合 DSH。固定同一 profile 就能复用模型、dsh-ops 与记忆插件，CLOU-2 的文件、grep、glob、Bash 均有原始结果。代价是 Multica 固定使用 `multica` profile，升级插件会影响共用它的全部角色。插件以宿主进程身份加载，当前无界面适配器可自动回应审批。Windows 的文件约束另受 ACL 和该版本实现限制。升级后应从服务会话复测已锁定的插件、PowerShell 启动与真实工具结果。[Multica 固定 profile](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/pkg/agent/dsh.go#L119-L121) · [文件沙箱边界](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/subsystems/sandbox.md#L6-L35) · [dsh-ops 0.5.5](https://github.com/T-Auto/dsh-ops/tree/v0.5.5)

**长期运行与安全。** 上游有桌面及 Web 组合，Web Host 可以挂载 Schedule，Teams 是否启用由会话配置决定。本机 Job 可以跨回合继续，所属 Agent 或 Job 服务销毁时才进入相应取消与回收流程。安装后需要长期存活的服务应明确独立的服务所有者和生命周期。审批事件能帮助审计一次调用，Windows 文件沙箱的部分约束、网络和进程可见性仍要分别考虑。通过这些机制无法直接推出企业合规结论。[Job 生命周期](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/packages/jobs/jobs-local/README.md#L53-L67) · [定时投递](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/docs/subsystems/schedule.md#L118-L133) · [团队模式](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/docs/subsystems/agent-team.md#L78-L82)

### Hermes

**结构。** CLI、ACP 及可选的常驻 Gateway 共用 Python 的 `AIAgent`。核心循环在预算内调用模型、经工具注册表选择处理器，把结果送回下一轮。Gateway 另管入口、会话路由和结果投递。运行时把原始会话与消息放在本机 SQLite，内置 Memory 保存短事实，Skills 按需加载操作方法，外部 Hindsight 提供项目经验。对跨日交接而言，这意味着原始会话可查证、已有经验可召回、操作方法可单独维护。[0.19 对应发布线的官方架构](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/website/docs/developer-guide/architecture.md) · [工具注册与筛选](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/tools/registry.py#L530-L565)

**选型取舍。** Hermes 适合跨会话故障分诊、交接和知识维护。11-18 的 win-work CLI 新会话首轮注入 15 条记忆。11-20 的 CLOU-16 进一步验证了 Multica 派发：Hermes 0.23.2 的新 ACP 会话在首个业务工具前收到 21 条项目记忆，并按 ID 读回本库和获准外库的文档，显式召回各 7 条。自动注入可能遗漏具体结论，需以实际模型上下文和原件核对。运维涉及本机会话历史、profile、外部 bank 及工具后端，local 终端权限来自宿主账户。Gateway 常驻、故障后自动恢复和后台形成 Skills 各需专门验证。[ACP 验收原卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-16) · [各端接入报告](hindsight-installation-report-2026-11-20.md) · [原生后台复盘的工具范围](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/agent/background_review.py#L809-L833)

**周期任务与经验复用。** 固定发布线中的后台复盘要累积到配置阈值、能使用技能管理工具，并取得完整且未被中断的回复，才有机会创建或修订 Skill。可重复的巡检、历史分诊、个人稳定偏好、跨渠道交接各有收益。临时故障只有经过再次复现才适宜固化成步骤。Gateway 投递账本可重投已完成的回复，必要时以业务 ID 去重。创建 Skill、下次加速、任务完成、消息送达需要各自的证据。[发布线复盘实现](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/agent/turn_finalizer.py) · [官方 Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) · [结果投递账本](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/gateway/delivery_ledger.py)

## 实际推理档位

2026-11-20 在 `cloud-work` 逐一读回了 12 个角色，包括本次使用的 Mac Kimi 验证角色。全部角色的 `thinking_level` 均为空。Multica v0.11.0 将空值解释为继承运行时默认；模型选择和推理档位可以分别设置。下表把云端 Dot 查到的上游默认值与实际 Run 对照。角色创建者可用前者做初估，用后者说明某次任务实际采用了什么。

| 主机与 Harness | 角色留空时的参考 | 本项目观察到的档位与证据 |
|---|---|---|
| win-work · Hermes | 官方文档中常见缺省为 `medium`，实际受模型覆盖、provider 和版本影响。该版 Multica 的 Hermes 适配器没有可选的角色级 effort 档位。 | **`high`**。CLOU-16 的新 ACP 会话使用 `gpt-6.2-sol`。`session.info` 同时记录 `reasoning_effort=high` 和 `reasoning_effort_wire=high`，两者均为运行时解析值。该 Run 没有独立的上游请求体。[Hermes 官方配置](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#reasoning-effort) |
| win-work · Kimi | 官方 K2.8 Preview 在开启 thinking 且调用未传 effort 时默认为 `max`，K3、K3.1 Pro 默认为 `high`。自定义端点按其模型配置解析。 | **`max`**。CLOU-18 的宿主初始绑定 `local-gpt/gpt-6.2-sol`，随后会话选择了 `kimi-code/kimi-for-coding`。`config.update` 与用量记录可核对模型，会话档位为 `max`。逐请求的推理字段未记录。[Kimi 官方模型表](https://www.kimi.com/code/docs/en/kimi-code/models.html) |
| mac-work · Kimi | 使用同一套 Kimi 规则。换模型时按模型 ID 查默认档位。 | **`max`**。CLOU-17 的宿主配置指向 `kimi-code/kimi-for-coding`（K2.8 Preview），本次新会话也读到 `thinking_effort=max`。逐请求的推理字段未记录。[Kimi 适配器](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/agent/kimi.go#L349-L382) |
| win-work · OMP | 18.22.2 的 `defaultThinkingLevel` 缺省为 **`high`**。配置、模型选择器后缀、模型能力或显式 `--thinking` 会影响取值。 | **运行档位未知**。默认模型验证和近期运维 Run 有 thinking 事件，未找到具体档位字段。[对应版本设置](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/settings.md#thinking) · [Multica 启动参数](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/agent/pi.go#L1228-L1240) |
| win-work · DSH | 0.2.2-rc.3 的内置 DeepSeek provider 默认 **`high`**。使用其他 provider 时查看实际模型在专用 profile 中公布的 `default_level` 和支持的档位。 | **运行档位未知**。已查的默认模型验证和 DSH 任务记录没有给出有效档位。[固定 RC 的 DeepSeek provider](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/packages/llm/llm-deepseek/README.md) · [Multica 适配器](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/agent/dsh.go#L432-L468) |
| mac-work / win-work · Codex | 可用档位取决于运行时和选中模型的目录。 | Mac 原审查员的历史 Run 没有记录具体档位。CLOU-19 在 Windows Codex 上试用 `gpt-6-luna / medium`，角色配置已读回，沙箱启动 PowerShell 失败。该试跑没有形成审查结论。 |

**查原始证据。** 在 Multica 的「Multica 运行时验证」项目中查看 CLOU-16 的 Run `01a1f6e9-96be-735c-b31a-fdf0255eec92`、CLOU-17 的 Run `01a1f6e5-81f5-75b7-99b2-244fc6e2e8e6` 和 CLOU-18 的 Run `01a1f6eb-8670-7886-a598-133fcc335a10`。在 Hindsight 的 `multica-4-dot` bank 中，云端 Dot 的原始调查 ID 为 `multica-v0-11-0-harness-thinking-defaults-2026-11-20`，本次合并回执 ID 为 `multica-harness-effective-thinking-levels-20261120`。

**用于估算 Token。** 先固定模型及 provider，再分别记录角色覆盖值、宿主默认值、会话解析值和供应商请求字段；缺哪层就注明哪层。原生默认 `high` 不能直接填进某次 Run 的实测栏。跨 provider 的同名档位也不能折算为固定 Token 数，费用估算使用对应模型、端点和工作负载的实际用量。

## 速度与 Token

希望比较的是拿到**可验收产物**需要多久、花多少，而不是模型首次出字有多快。下表的机制可由公开资料核对，其中“可缩短”“会增加”描述的是特定条件下的影响。本轮未找到覆盖五款指定版本、使用同一模型和同一组任务的完整公开测试。

| Harness | 哪些任务可能更快，时间会花在哪里 | Token 主要省在哪里，又会花在哪里 |
|---|---|---|
| **Codex** | 同一线程继续复审可以复用已有上下文。流式 Item 让审查者尽早看到命令进度。完整周转时间仍包含模型推理、工具和测试。 | 保持模型、工具顺序和说明稳定，有利于前缀缓存命中。切换模型、变更工具列表、长历史压缩都会改变后续请求。缓存主要节省重复预填计算，费用取决于端点定价。[官方执行循环与缓存说明](https://openai.com/index/unrolling-the-codex-agent-loop/) |
| **Kimi** | 工具执行器协调可并发的资源访问。独立查阅有机会并行，操作同一资源时可能等待。研究岗常把时间花在取资料和核验引用，实现岗还要计入测试及返工。 | Wire 保留历史，实际输入取决于投影给模型的消息、工具和返回正文。压缩可缩短后续上下文，摘要步骤和重新读取关键来源另有成本。本次检索未取得该版与其余四款同题的端到端数字。[工具执行器](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/agent/toolExecutor/toolExecutorService.ts#L90-L124) · [官方用量接口与压缩操作](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/reference/server-api.md) |
| **OMP** | 有语言服务、可用的调试适配器和可重复故障时，定位符号或断点能减少盲目试改。首次启动语言服务要等待。独立 Advisor 默认关闭，启用后可后台运行，追赶或收尾策略会增加等待。 | Hashline 用简短锚点引用原行，模型在部分编辑任务中少输出重复文本。AST 结构化编辑是另一条路径。Advisor、子代理、压缩和失败后换模型都可能增加整项用量，需计入辅助模型。[编辑协议](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/tools/edit.md#L1-L24) · [Advisor 的等待策略](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/advisor-watchdog.md#L198-L225) |
| **DSH** | 将高频操作做成参数明确、结果紧凑的工具，可减少模型与 Shell 之间的往返。插件过多、工具结果过长、重复审批或多次压缩会抵消收益。下方有独立公开样本。 | 系统提示随 scope、模型和工具 schema 动态组装，语言模型压缩旧历史也消耗请求。社区流传的“DSH 6k、Hermes 20k”缺少同版本、同工具条件，只能视为个别首轮提示估算。整项任务用量应累计每次请求。[提示组装](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/docs/subsystems/system-prompt.md#L11-L46) · [Token 计量口径](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.3/docs/subsystems/token-meter.md#L9-L29) |
| **Hermes** | 跨日跟踪、值守交接可以用记忆找回已有结论，减少重新排查。短任务很难摊薄检索等待。Gateway 送达和执行耗时也应分开。下方公开结果限指定模型和工作负载。 | 按需打开 Skills 和压缩历史可控制后续输入。召回内容会进入模型上下文，摘要或后台经验复盘可再用模型。收益取决于后续是否确实复用该经验，关闭外部自动留存与关闭本地历史是两项设置。[上下文压缩与缓存](https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/website/docs/developer-guide/context-compression-and-caching.md) · [经验复盘触发条件](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/agent/turn_finalizer.py) |

### 两组可复核的公开结果

- **改编辑格式，同一模型的输出可能下降，也可能上升。** OMP 作者对 180 道 React 单文件变异修复题比较三种编辑格式，每题三次，每次新会话。Hashline 的结果表中，Grok 4 Fast 输出 Token 少 61%，GPT-5.2 Codex 多 26%，DeepSeek V3.2 多 20%。实验改变的是编辑格式，衡量的是输出 Token。把 61% 当成 AST 工具或任意 OMP 任务的总成本节省，会得出错误预算。[作者原始方法和结果表](https://stencil.so/blog/the-harness-problem)
- **输入更多也可能更早交付。** 一项独立实验在同一 GB300 和同一 DeepSeek-V4.1-Flash-1017 端点上，以 high effort 对 20 道 Terminal-Bench 2.0 题各跑两次。DSH 0.2.1-rc.2 每条平均 337 秒，两轮引擎累计输入 38.68M、输出 0.84M，通过 28/40。Hermes 0.22.2 为 415 秒、输入 31.35M、输出 1.12M，通过 30/40。两个端的前缀缓存命中约 96%–97%，通过率差异未达到统计显著。版本、缓存环境和计量范围都限制外推，尤其不能据此为本项目设备报秒数或费用。[实验方法、数据与计时口径](https://al-engr.com/dsv41-1017-harness-shootout-hermes-dsh-claude-code.html)

后续收录评测时同时记下模型快照、推理强度、服务端点、任务集、权限、工具集、缓存条件、并发与超时处理。速度优先看通过率和每个已交付任务的墙钟时间，同批任务另报吞吐。Token 区分缓存命中输入、未命中输入、输出和供应商单列的推理量，避免重复相加。压缩、失败重试、Advisor 与子代理均计入总数。比较成本时可用该批全部尝试费用除以验收通过数。

## 推荐分工与换选条件

| 有价值的变化 | 什么时候值得 | 什么时候保持简单 |
|---|---|---|
| 普通实现交给 Kimi，结构化重构或深度调试选 OMP，独立复审交 win-work DSH 审查员。 | 跨文件语法模式、高频符号导航、断点或变量观察是交付条件时，OMP 的 AST、LSP、DAP 能直接提供证据。 | 单文件小改且已有回归断言时，沿用现有 Kimi 实现角色。一次修复若还要再启 Advisor 和一位正式审查员，先判断第二次审阅能否发现不同类别的问题。 |
| 把符合稳定输入输出的重复步骤交给脚本或 DSH 工具，把需要判断的步骤交给模型。 | 跨任务复用同一工具、需要逐项留痕或精简工具返回时，DSH 专用 profile 的维护成本容易摊薄。 | 一次性文件操作可复用现有角色和工具。安装插件、升级共享 profile 或建立常驻服务需要有持续需求或可衡量收益。 |
| 用 Hermes 做跨会话分诊、巡检交接和知识维护，平台只保留一个任务调度者。 | 任务会反复使用同一经验，或确实需要定时触发、经授权的跨渠道送达。固定采集和统计交给脚本，Hermes 解释异常和引用历史。 | 单次问答、固定格式转换或批量分类优先采用现有对话或脚本。Windows 高权限操作已有 OMP 路径，从 Hermes 再嵌套一个 OMP 会增加第二套身份、日志与取消处理。只有独立收益清楚时再考虑。 |

## 建一个可以验收的角色

1. **选职责与样本。** 从角色库当前定义取角色 ID 和版本，写清输入、允许的动作、交付物、原始回报位置和谁验收。例如，软件实现工程师在指定仓库修正一个边界条件，交付差异和可重复的断言，由独立审查员在原卡复核。[角色库公共约定](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/docs/worker-library/roles/common.md)
2. **选主机并核对权限。** 查当前 workspace、主机、provider、版本、已有角色及绑定。默认启用工具，使用工作区写入权限，按任务需要申请提权。分别确认调用者、可用工具、宿主可写路径以及凭据代表的身份，并记录提权由运行时自动应答还是由操作者确认。有硬隔离要求而该组合只有指令约束时，换用经验证的组合或先在隔离账户复验。
3. **创建后读回。** 以下是 v0.10.0 的 CLI 示例。`WS` 和 `RT` 分别取目标 workspace 和已核对的 runtime ID，`NAME` 与 `INSTRUCTIONS` 取本角色的名称、职责与边界。`AGENT` 取创建结果的 ID。示例选私有、并发 1，共享范围与并发按角色需求单独设置。管理令牌由授权者经平台的私密环境变量入口配置。[CLI 命令参考](../skills/multica-backend/references/cli-v0.10.0.md) · [后端操作与身份](../skills/multica-backend/SKILL.md)

   ```sh
   multica --workspace-id "$WS" runtime list --output json
   multica --workspace-id "$WS" agent list
   multica --workspace-id "$WS" agent create --runtime-id "$RT" --name "$NAME" \
     --instructions "$INSTRUCTIONS" --permission-mode private --max-concurrent-tasks 1
   multica --workspace-id "$WS" agent get "$AGENT"
   multica --workspace-id "$WS" agent skills list "$AGENT"
   multica --workspace-id "$WS" agent mcp list "$AGENT"
   ```

4. **在新会话走完整派发。** 在正确的项目新建小任务，派给目标角色。读回实际执行者、runtime、Run 终态和工具结果，再核对交付物。验收研究角色时点开一条固定版本引用，验收实现角色时独立跑一个边界断言。运维角色需展示可撤销操作及恢复结果。审查员需走一次退回、重交和复审。知识角色用已有来源对照自动注入和显式读回。配置变更后开新会话，避免复用旧权限。
5. **留下可追溯的结论。** 记录日期、主机、版本、Issue/Run、可复核产物及待验项。工具可用、Run 结束、角色能力通过、业务结果获负责人接受分开记录。角色调用范围用 `private` 或 `public_to` 表达。已有管理员允许整个工作区调用，是该角色经确认的例外。

## 资料索引

按要核对的问题选资料。固定源码用于复查观察当日的机制，官方总览用于理解分层，本项目回执用于确认 win-work 或 mac-work 的实际行为。原始实验用于比较作者实际控制的变量，第三方文章作为延伸阅读。

| 入口 | 适合检索的内容与版本 |
|---|---|
| [Codex 官方 App Server 设计](https://openai.com/index/unlocking-the-codex-harness/) · [Windows 0.162.1 线程存储](https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/thread-store/README.md) | JSON-RPC、Thread / Turn / Item、恢复、审批主体。Mac 与 Windows 分别按上文的已装版源码核对。 |
| [Kimi Code 2.6.3 仓库架构图](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/AGENTS.md#L16-L37) | App / Session / Agent、Agent Client Protocol（ACP）、Wire、工具作用域。检索当前 TypeScript 代码线。 |
| [OMP 18.22.2 代理内核](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/agent/README.md) · [原生 RPC](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/rpc.md) | Oh My Pi、模型流、工具事件、JSONL 与 RPC。核对 OMP 自身 tag 中的实现。 |
| [DSH 0.2.2-rc.3 架构](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/architecture.md) · [会话持久化契约](https://github.com/deepseek-ai/deepseek-harness/blob/38a6a5c965aa99ab525161efb7cc5cf1fe62fced/docs/subsystems/persistence.md#L3-L9) | DeepSeek Harness、Cordis、bundle、profile、事件提交和工具审批。 |
| [Hermes 发布线架构](https://github.com/NousResearch/hermes-agent/blob/3ef6bbd201263d354fd83ec55b3c306ded2eb72a/website/docs/developer-guide/architecture.md) · [Hindsight 官方 Hermes 接入](https://hindsight.vectorize.io/sdks/integrations/hermes) | AIAgent、Gateway、SQLite 会话、Memory provider、Skills。win-work 报 v0.19.0，本机 Git HEAD 无法解析，发布线用作参照。 |
| [大飞随笔的 Hermes 架构分析](https://ainoteatlas.com/writing/hermes-agent-architecture-deep-dive/) | 作者分析 v0.21.0 开发快照 `6327930`。可按执行循环、常驻入口与跨会话学习阅读。本文仅将已在 v0.19 本机或对应发布线核实的机制用于选型。 |
| [Hashline 原始评测](https://stencil.so/blog/the-harness-problem) · [DSH 与 Hermes 同端点原始实验](https://al-engr.com/dsv41-1017-harness-shootout-hermes-dsh-claude-code.html) | 分别索引编辑格式的输出用量、终端任务整批输入与墙钟时间。详见[速度与 Token](#速度与-token)。 |
| [OMP 工程工具介绍](https://www.cnblogs.com/itech/p/20176230) · [OMP 与 Pi 的对比](https://segmentfault.com/a/1190000047814238) · [DSH 五层架构解读](https://developer.cloud.tencent.com/article/2745941) | 用户提供的中文阅读线索。工具名称、数量、审批和后台进程语义以对应发布版的上游实现为准。 |
| [公子提供的知乎专栏原文](https://zhuanlan.zhihu.com/p/2022015752258027715) | 2026-11-18 访问原页返回 HTTP 403。保留原始入口，正文与具体论点待核。 |

## 新增、升级或停用时怎样更新本文

角色创建者补现场记录，项目维护者核对对应行和固定来源的适用版本。新增 harness 或主机时，在运行时表加一行，在“架构比较”增加同名小节，补全执行循环、状态、工具与权限如何影响选型。在快速索引与资料索引加入该名称、上游版本和链接。只有它改变某个岗位的选法时才更新首选表。暂时只有宿主 CLI 时可在此记为候选，待 Multica 登记后移入主表。

| 可复制的更新字段 | 填写内容 |
|---|---|
| 主机 / provider / 版本 / Multica 版本 / 日期 | 同一天的 `runtime list`、启动入口和宿主版本。注明 CLI、平台派发或独立复核的实际层级。 |
| 执行 / 状态 / 扩展 / 权限边界 | 写出入口如何到达模型与工具、状态由谁保存、如何恢复、扩展加载在哪里、谁批准并执行。用一处源码解释一项收益和一项代价。 |
| 岗位 / 交付物 / 必要工具 / 权限 | 写一个确实能受益的岗位，以及一个倾向选其他方案的条件。记录宿主权限、角色调用范围和必要凭据的类型。 |
| 速度 / Token / 对照条件 | 分开记录任务耗时与整项输入、缓存、输出，注明模型、负载、版本及通过率。有公开同题实验时附来源，无可比资料时写明缺口。 |
| 证据 / 限制 / 下一次复验 | 附任务与 Run 或本机会话，给出产物的预期和实际结果，链接上游固定版本来源。未验证处写最小复验任务。 |

升级 harness、Multica 适配器、daemon 身份或关键插件时，仅重验受影响的行。失败过的样本保留原回执，新增复验日期与结果。停用的组合标记退役日期和替代项。共享记忆只留脱敏结论及本文路径，配置和选型持续在本文维护。

| 修订日期 | 变更与依据 |
|---|---|
| 2026-11-18 | 首版。基于 Multica v0.10.0 双端登记、CLOU-1 至 CLOU-3、CLOU-5 至 CLOU-10 与 Hermes 本机会话。 |
| 2026-11-18 | 增补五种执行架构、角色选型取舍、按问题与来源检索，记录 Hermes 文章与实装的版本差异、两项公开性能实验与换选条件。 |
| 2026-11-20 | 按公子确认登记工作区协调员 Mike，核对原生岗位、OMP 绑定、CLOU-4 回报和待加强的技能与跨端回执。 |
| 2026-11-20 | 整合云端 Dot 的原生默认档位调查与 CLOU-16、17、18 的新会话证据，补入按主机对照和 Token 估算口径。 |
| 2026-11-20 | CLOU-23 核对 CLOU-12/16 的原件，修订知识维护岗位、运行时表和 Hermes 选型说明。Multica 派发已验，主机故障后自动恢复待验。 |
| 2026-11-20 | 独立审查迁至 win-work DSH。CLOU-19 首次业务工具调用约 18 秒，8 分 29 秒回写独立审查报告，5 项通过。原 mac-work 四次超时和 Windows Codex 沙箱失败均保留在历史 Run。 |
