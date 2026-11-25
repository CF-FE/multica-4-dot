# Multica 角色创建与 Harness 选型指南

在 Multica 新建或调整智能体时，用本文选主机、运行时、工具和验收任务。新角色职责由所属 Multica 项目的交付目标、运行权限和验收人确定，宿主能力以目标机器上的实测为准。herdr-4-codexcloud 已于 2026-11-21 退役；既有角色的固定版本引用仅用于追溯来源。本文是本仓库的选型主文档，后续直接更新同一文件。当前范围为 `cloud-work` 的 mac-work 和 win-work，按项目约定暂不纳入 Claude。选型基线为 2026-11-18 的 Multica v0.10.0。工作区协调员条目于 2026-11-20 按 v0.11.0 实例核对，本文时间均为北京时间。[历史角色库索引（1.0.3）](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/docs/worker-library/roles/index.json)

**快速索引**　[找 Mike](#工作区协调员-mike) · [按岗位选](#从角色要交付的结果开始) · [两端版本与实测](#两端实际登记的运行时) · [按架构问题查](#架构比较) · [速度与 Token](#速度与-token) · [实际推理档位](#实际推理档位) · [推荐分工](#推荐分工与换选条件) · [创建与验收](#建一个可以验收的角色) · [Kimi 与 OMP 独立决策身份](#win-work-的-kimi-与-omp-独立决策身份) · [DSH 与 Hermes 独立决策身份](#win-work-的-dsh-与-hermes-独立决策身份) · [按来源查](#资料索引) · [新增或升级](#新增升级或停用时怎样更新本文)

**按岗位建角**　[角色库：职责、可复用岗位与首单验收](role-library.md)

**按 Harness 查**　[Codex](#codex) · [Kimi](#kimi) · [OMP / Oh My Pi](#omp) · [DSH / DeepSeek Harness](#dsh) · [Hermes](#hermes) · [win-work 原生子智能体配置与验收](#win-work-同一-run-内的原生子智能体)

## 工作区协调员 Mike

G8 向各工作区协调员交办的统一约定见[职责与协作规范](../skills/workspace-coordination/SKILL.md)。本节登记 `cloud-work` 的现任人员和运行时。

新工作区上线时，由建立者核对本工作区的协调员及原生 ID，向该协调员分配同一份 `workspace-coordination`、适用的后端技能、Task Mailbox 和 Decision Service MCP。可复用服务 URL，OAuth 要在实际调用的身份和运行时完成。登记已接手的原 Issue、可读回的决定和回报作为该工作区的接入证据。更换协调员时，连同在途任务和回程交给新任。

项目负责人有独立的任命、项目权限和验收要求。新建或换任时见[项目负责人怎么配](#项目负责人怎么配)。

Decision Service 部署在外网 Vultr VPS，由 `decision-service.service` 监听回环端口 8768，对外服务路径为 `/decision-service/mcp`。2026-11-20 已核对生产单元运行状态和云端决定读回。[服务部署说明](https://github.com/CF-FE/decision-service/blob/main/docs/deployment.md)

**找人入口**　进入 `cloud-work → 智能体 → Mike`。Mike 可在工作区内查现任负责人、按能力与权限找适配角色、汇总进度和转交工作。目标明确、归属清楚时可直达项目负责人。查人或查进度时直接答复，受托转交时沿原卡跟到接手；执行和验收由各自的责任人办理。需留存的事项从所属项目的原 Issue 交办，验收人仍以原任务约定为准。按 `system_key=mika` 可识别内置岗位，显示名、绑定和可调用范围以工作区智能体详情为准。

Mike 当前挂载四项 Skill：`workspace-coordination` 管交接与回程，`multica-backend` 查原件和办理转交，`stakeholder-map` 辨明任职与对口人，`decision-service` 用于有实质取舍的协调决定。

**当前绑定与证据**　2026-11-20 回读为 win-work OMP，模型配置 `cli-proxy-chat/gpt-6.2-sol`，允许工作区成员调用，并发 3。CLOU-4 的原卡及回合记录显示，Mike 汇总了多个运行时的结果，指出待补的验收证据，并按公子确认的标准回报结项。建议沿用这位协调员及其原有绑定。Hermes 的记忆与跨会话分诊、DSH 的流程工具可由专项岗位使用。

**能力评估**　Mike 已有内建 Chief of Staff 系统指令和 Multica CLI 操作指引。2026-11-20 已增量挂载 `multica-backend`，任务归属、按 Run 取证、对账和唤醒规则均以该技能为准。工作区 `task-mailbox` HTTP MCP 已分配给 Mike，配置读回为启用。CLOU-20 补齐授权后，Mike 用 OMP 经 MCP 读取身份、按原 job 取件并发布了 v1。信箱已保存相同版本与摘要的独立读确认。OMP 的 Shell 权限还受 Windows 宿主账户影响，现有配置缺少强制工作区写入隔离的证明。[后端技能](../skills/multica-backend/SKILL.md) · [跨端汇报方案](workflow-reporting.md)

## cloud-work 新增专业角色（2026-11-20）

在工作区的「智能体」中按下表名称查找。四个岗位均允许工作区成员调用，并发各为 1。已逐一读回运行时、实际角色指令及工作区调用范围；Dot 专属账号对试点项目的四次指派预览均命中对应智能体。岗位正文固定自 [Herdr 角色库 1.0.3](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/docs/worker-library/roles/index.json)。项目负责人、业务验收与跨端回程按原任务办理。

| Multica 名称 | 角色 ID | 工作内容与验证单 |
|---|---|---|
| 视觉设计师（mac-work Codex） | `workspace_visual` | 已实测读图和生图。读图时正确读出图形方位、颜色与字符；生图时公子指定的 `gpt-6.2-sol` 调用原生图像生成工具，生成《橘猫邮差》并将 1086 × 1448 PNG 上传原卡。下载件与生成原件的 SHA-256 一致。该 Agent 经 Mac 现有 Verge 连接模型，内网直连。[读图 CLOU-24](http://10.207.56.3:3000/cloud-work/issues/CLOU-24) · [生图 CLOU-28](http://10.207.56.3:3000/cloud-work/issues/CLOU-28) |
| 知识管理员（win-work Hermes） | `workspace_knowledge` | 依据原件整理索引和冲突清单，按稳定文档 ID 核对 Hindsight 原文。沿用 Agent `7fe827c7-11ad-4afa-ba03-9f883deb16c4`；换绑前后的 Run 均在同一张验收卡。[CLOU-25](http://10.207.56.3:3000/cloud-work/issues/CLOU-25) |
| 产物处理（win-work DSH） | `artifact_processing` | 确定性文件转换。已从原卡下载 UTF-8 CSV，逐字节核对 28 字节和 SHA-256。[CLOU-26](http://10.207.56.3:3000/cloud-work/issues/CLOU-26) |
| 辩证复核专员（win-work DSH） | `workspace_dialectic` | 已在原卡对齐同一简报中的正反证据，给出中断恢复的验收条件。独立双线复核另需两个各自形成首稿的上下文。[CLOU-27](http://10.207.56.3:3000/cloud-work/issues/CLOU-27) |

产物处理和辩证复核沿用 DSH 的 `multica` profile 和 `local-gpt/gpt-6.2-sol`。知识管理员按公子指定原位改绑 win-work Hermes，模型随运行时配置。岗位指令限定在当次工作区内操作；Hermes 的 `local` 终端继承 Windows 账号的文件权限，宿主级强制隔离待验。[Hermes 工作目录与后端](https://github.com/NousResearch/hermes-agent/blob/09ded63/website/docs/user-guide/profiles.md#L239-L244) · [项目记忆接入](win-work-hindsight.md)

**知识管理员的案例复用验收。** CLOU-40 的历史试跑覆盖按症状召回、按文档 ID 读回、原卡反馈以及已有案例去重。校验正文时直接取结构化响应的完整 `original_text` 并按 UTF-8 原样计算 SHA-256；预览截断或转录副本须标明边界。[知识管理员原卡反馈](http://10.207.56.3:3000/cloud-work/issues/01a1f9b0-ab24-7cf1-b748-8b5dc2c4e966#comment-01a201a7-3151-7a3b-b46b-6ba834065ce1) · [校验规则](../skills/workspace-coordination/SKILL.md#阻塞案例的检索沉淀与反馈)

**知识管理员的启动入口。** 2026-11-21 起，专属 profile 经 `KnowledgeHermes.exe` 启动原受管 Hermes，详见[独立决策身份](#hermes-的任务私有配置)。此前 CLOU-25 使用 Hermes 0.23.3，由岗位专属 Multica 运行时直接调用 `%LOCALAPPDATA%\hermes\bin\hermes.exe acp`。旧 checkout 的 `venv\Scripts\hermes.exe` 曾连续两次在初始化时无法导入 `ArgsKwargs`；同机受管启动器通过 ACP 握手。原卡新 Run `01a1f85f-a882-7805-8132-408f187f61c5` 核对了 CLOU-16、CLOU-23，调用 `mcp__hindsight__get_document` 按稳定 ID 取回原文并回报原卡，独立读回的 SHA-256 一致。此次使用显式读取；新会话的派生配置将外部 `memory.provider` 留空，首轮自动注入只在旧版本验收中得到验证。[换绑验收 CLOU-25](http://10.207.56.3:3000/cloud-work/issues/CLOU-25)

**已退役的 win-work Hermes 验证智能体。** 2026-11-20 17:53（北京时间），按公子要求归档「Hermes 默认模型验证（win-work）」，并核对其已从工作区活动列表移除。旧 ID `ea0882b6-f4b7-45be-91ab-7993f2df28cc` 的 6 个历史 Run 仍可读取（4 完成、1 失败、1 取消）。CLOU-4、12、16、19、23 均已结项，相关 Issue 没有启用中的唤醒。CLOU-16 曾验证正常 ACP 首轮记忆注入、按 ID 读取及本库留存，CLOU-19 的单行留存已在长度限制内重交并读回。CLOU-4 在 daemon 重启后自动重试，原任务未能交付；后来成功的是单独新开的会话。升级后仍需受控验证中断恢复，并复核 CLOU-12 的三处源码适配及备份。[故障原卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-4) · [接入验收](hindsight-installation-report-2026-11-20.md)

## 从角色要交付的结果开始

| 要创建的角色 | 建议首选 | 什么情况下换选或补验 |
|---|---|---|
| 质量审查员 · `workspace_quality` | **win-work DSH**。该角色担任质量团队 leader。新审核按项目生效路由或原卡约定交办。使用 Multica 专用 profile 的 `workspace-write` 策略，实际模型和推理档位以角色详情及 Run 为准。 | 先核原件、候选 Run 和必验产物。审查者须独立于被审版本的制作。旧卡 CLOU-1 至 CLOU-3 的审查由当时的 mac-work Codex 执行。 |
| 研究分析师 · `workspace_research` | **mac-work Codex**，现任角色使用 `gpt-6.2-astra`、`medium`。技术调查按原件和版本取证。产品研究按材料调用 `competitor-analysis` 比较同一场景的竞品，`summarize-interview` 从访谈提取用户任务，`sentiment-analysis` 按样本分组整理正反反馈。[pm-skills v2.3.0](https://github.com/phuryn/pm-skills/tree/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef) | 关键结论标来源、适用条件及可改变判断的证据。样本不足时保留实际数量和未知项。[Codex 换绑验收 CLOU-73](http://10.207.56.3:3000/cloud-work/issues/CLOU-73) · [原 Windows Kimi 记忆验收 CLOU-30](http://10.207.56.3:3000/cloud-work/issues/CLOU-30) |
| 软件实现工程师 · `software_implementation` | **win-work Kimi**。实际故障用 `debugging-and-error-recovery`，有回归风险的行为变更用 `test-driven-development`，复杂改动用 `incremental-implementation` 分步交付。三项取自公子的 [my-agent-skills 6.4.0 固定版本](https://github.com/ghyghoo8/my-agent-skills/tree/af606510148d79141ab6b9643c60d39a44f06d87/plugins/my-agent-skills/skills)。项目记忆按工作区统一 `hindsight-memory` 约定。 | 工作要求由系统强制限制写入时，先取得目标主机的边界实测。原 Windows 宿主授权按当时的角色与执行环境办理。 |
| 结构化重构、交互调试 · `software_implementation` | **win-work OMP** 是工具匹配的候选。AST、LSP 和 DAP 可提供结构匹配、引用及断点证据。 | 确认目标语言服务和调试器可用。该岗位目前有固定版本架构依据，项目历史案例覆盖的是宿主运维。 |
| Windows 运维工程师 · `workspace_runtime` | **win-work OMP**。可使用本机 PowerShell、Windows 管理工具和 MCP 服务，已验证提升后的进程身份和工具结果。 | 普通工作区维护可复用 DSH。修改系统文件、安装服务或使用凭据时，按任务给出目标、授权范围、恢复方法及验收证据。 |
| Multica 系统管理员 | **win-work OMP + `multica-backend`**。适合查实例、核对 Run、使用任务内 CLI 回报。 | 涉及 workspace owner 能力时，分别核验操作者与普通 Run 的身份、调用范围和一项可恢复操作。技能、宿主管理员、平台令牌各有独立作用。 |
| 项目知识维护 · `workspace_knowledge` | **win-work Hermes** 已用真实 Multica ACP 任务验证首轮项目记忆和获准的跨库读取。OMP 和 DSH 也有各自的派发与读取回执。 | 需要在宿主中断后无人值守续跑的岗位，仍须单独验证恢复。引用具体历史结论时按原文档核查。[五端安装与验收报告](hindsight-installation-report-2026-11-20.md) |

有可复用角色时，先看它能否交付样本、是否接触过待审产物、权限是否覆盖任务。统一使用一种运行时可减少插件和升级维护，但 Windows 服务、独立审查与特定工具各有自己的验收条件。只有任务确实受数据位置、权限边界、工具或独立性约束时，才值得增加一个组合。以下判断有对应案例，速度、成本和模型质量尚无同题对照数据。

**研究分析师换绑记录（2026-11-25）。** 沿用原 Agent、五项岗位 Skill 和既有独立决策身份。角色已移除 Windows Python 的 stdio 覆盖，改用已分配的工作区 `decision-service-agent`。CLOU-73 用两条相反的访谈反馈验证研究方法，并分别检查历史决定读回和项目记忆召回。配置已读回；新会话结果待原卡验收。[迁移验收原卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-73)

## 两端实际登记的运行时

2026-11-18 17:55 从 Multica CLI 读回运行时、启动入口和角色绑定。下表七个组合当时均为 `online`。截至 11 月 20 日，mac-work Kimi、win-work Kimi 和 win-work Hermes 均有新的 Multica ACP Run，模型、档位及回执见[实际推理档位](#实际推理档位)。在原任务卡的 Runs、工具活动和附件可核对各次证据。

| 主机 | Harness 与版本 | Multica 启动入口 | 当前已证实的最高层级 |
|---|---|---|---|
| mac-work | Codex 0.169.0-alpha.11.1 | `codex app-server` | Multica 独立审查和返工复审，CLOU-1 至 CLOU-3 |
| mac-work | Kimi 2.6.3 | `kimi acp` | 运行时在线，本项目角色任务待验 |
| win-work | Codex 0.162.1 | `codex app-server` | 运行时在线，本项目角色任务及 Windows 沙箱待验 |
| win-work | Kimi 2.6.3（11-18），2.7.2（11-21） | `kimi acp` | Multica 研究附件、代码修改及独立测试，CLOU-6、CLOU-7 |
| win-work | OMP 18.22.2（11-18），19.0.1（11-21） | `omp (json mode)` | Multica 运维、平台技能和项目记忆，CLOU-5、CLOU-9、CLOU-10 |
| win-work | DSH 0.2.2-rc.3 | `dsh --profile multica`，stdio | Multica 文件、搜索、Bash、返工及记忆，CLOU-1 至 CLOU-3、CLOU-8；独立项目决策见 CLOU-44、45。 |
| win-work | Hermes 0.19.0（11-18 登记），0.23.2（11-20 实测），0.23.3（CLOU-43） | `hermes acp` | CLOU-16 的真实 ACP 新会话已验证首轮注入和跨库只读；故障后自动续跑待验。 |

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

**选型取舍。** 一套宿主能给研究角色配引用与附件要求，给实现角色配编辑与测试工具，模型接入和会话逻辑可复用。代价在 ACP 边界。Multica 固定启动 `kimi acp` 并应答工具授权，`cwd` 和角色指令无法强制限制提升后的 Windows 账户。当时的两位 Kimi 角色获准采用指令限定的工作区。CLOU-6 的源码引用可读回，CLOU-7 首次 Run 结束却没有产物，原卡复跑后才得到通过 7 项独立断言的修复。研究和实现可复用这条交付链，有硬隔离或逐次人工审批要求的岗位要另验宿主与客户端。[Kimi 权限决策](https://github.com/MoonshotAI/kimi-code/blob/b0de2fbd2de04d87689225aafd3912e5d193b62d/packages/agent-core-v2/src/agent/permissionGate/permissionGateService.ts#L31-L69) · [Multica 的 ACP 入口](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/pkg/agent/kimi.go#L52-L76)

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
| 团队承接的软件实现交开发团队，新的独立复审按项目路由交质量团队或具名审查人。 | 跨文件语法模式、高频符号导航、断点或变量观察是交付条件时，OMP 的 AST、LSP、DAP 能直接提供证据。 | 单文件小改且已有执行者时，可沿原卡续办。一次修复若还要再启 Advisor 和一位正式审查员，先判断第二次审阅能否发现不同类别的问题。 |
| 把符合稳定输入输出的重复步骤交给脚本或 DSH 工具，把需要判断的步骤交给模型。 | 跨任务复用同一工具、需要逐项留痕或精简工具返回时，DSH 专用 profile 的维护成本容易摊薄。 | 一次性文件操作可复用现有角色和工具。安装插件、升级共享 profile 或建立常驻服务需要有持续需求或可衡量收益。 |
| 用 Hermes 做跨会话分诊、巡检交接和知识维护，平台只保留一个任务调度者。 | 任务会反复使用同一经验，或确实需要定时触发、经授权的跨渠道送达。固定采集和统计交给脚本，Hermes 解释异常和引用历史。 | 单次问答、固定格式转换或批量分类优先采用现有对话或脚本。Windows 高权限操作已有 OMP 路径，从 Hermes 再嵌套一个 OMP 会增加第二套身份、日志与取消处理。只有独立收益清楚时再考虑。 |

## 项目负责人怎么配

1. 从所属项目读回 `lead_type`、`lead_id`，与实际 Agent 和运行时核对。给 Agent 负责人增量挂载并启用同一份 `workspace-coordination`，读回原有挂载和新增项。默认装配已获准的 Decision Service MCP，核对独立身份的项目范围。验证项目 bank、原卡回件和工作区工具权限。成员负责人在本人实际客户端接入。任命和 Skill 挂载各有作用，资产写权、制作与发布许可仍查本项目的正式记录。[共同协作规范](../skills/workspace-coordination/SKILL.md)
2. Prompt 写清项目目标、验收条件、可自行决定的范围、需要谁决定的例外，以及结果回到哪里。普通进展留原卡；有约定回程时沿原委托办理。由获准的验收人签认相应范围，独立复审按项目约定执行。

**负责人在 mac-work、任务要操作 win-work 时，默认走 SSH。** 建角时写明项目现用的 SSH 目标和 Windows 工具入口，主机或账号变更后按实际配置复核。原角色在 Mac 发起操作、在 Windows 产出结果，制作和核收可由原卡关联到同一负责人。用一次获准的代表性动作验证工具、产物和回件；只读探针只能证明所查能力。共享工位上的其他项目继续使用原有绑定。[跨主机执行规则](../skills/workspace-coordination/SKILL.md#一条能执行的指令)

| 负责人要做到什么 | 建角时怎样验证 |
|---|---|
| 自主交付。阶段交付或批次核收后，用已交成果直接续办下一项已授权工作；达到整卡目标交验。建角时使用[项目负责人 prompt 约定](role-library.md#角色创建指引)。 | 隔离卡给出目标、输入、权限和验收条件，其中首批结果是下一项工作的输入。核对负责人自己交出首项产物后能否直接用它完成下一项。如样本明确止于首项，则核对负责人是否按约停下并交清余项、决定人和恢复条件。 |
| 按需委派。短时并行分析可用同一 Run 的子智能体。需要专长或独立复审时按小队派工规则交适配小队或具名角色，说明交付物和标准。负责人据结果决定集成或退回具体缺项。 | 检查接收方、实际执行者、原卡产物和负责人核收。父 Run 收到子结果只验证会话内分工。 |
| 排查阻塞。先查原件和已有解法，用最小验证定位原因，修复后复验。缺许可只暂停受影响的动作，继续可做支路。 | 给一个可修故障和一个需授权的动作，分别看修复前后证据，以及有权人、恢复条件和已交付的独立成果。 |

用一个有代表性的样本覆盖实际岗位需要。涉及到期提醒时，再沿原检查点重放核对新增 Run 为零。项目内能办的由负责人推进，需协调跨项目资源或找不到有权人时才找协调员。一般交付由指定验收人直接在原卡核收，无需另行唤醒协调员。

2026-11-23 用凡人负责人的 win-work DSH 新会话验收：负责人读到挂载正文，交付的 28 字节清单经独立复算一致。Mike 具名决定暂停模拟导出，并记录收到对应许可后由负责人续办。用单卡账本发出一次原生到期提醒，在途及完成后重放，两次新增 Run 均为零。[CLOU-59 发起者验收](http://10.207.56.3:3000/cloud-work/issues/01a20668-d298-7b00-a405-dd00ec03963f#comment-01a2066f-a593-767c-9fb4-9cbae875be10)

2026-11-24 的 CLOU-62 验证了换绑 mac-work Codex 后的凡人负责人：负责人从合成清单排除作废样本，直接委派 win-work 质量审查员独立复算，再在原线程核收。发起方下载两份附件，两者均与预期的 14 字节逐字节相同，随后在原卡验收。此例覆盖独立修复、跨角色委派和核收。[CLOU-62 验收回执](http://10.207.56.3:3000/cloud-work/issues/01a20c6c-d305-719f-af27-e94cc8701ba9#comment-01a20c84-74a3-7171-92f9-8552f72cd46b)

## 建一个可以验收的角色

项目决策使用已获准的 Agent 服务身份和对应 MCP。若需复用 win-work 的 GitHub OAuth，可按下表核对同一 harness 的共享入口。先从服务端核实该共享身份在真实项目 UUID 下允许的操作，再安排业务调用。历史接入样本验证的是指定身份和会话的只读查询。2026-11-21 服务端核对时，共享 OAuth 仅有 `decision-service-smoke`；当前两个 Multica 项目的决策访问使用角色专属身份。按运行时查看 [Kimi 与 OMP](#win-work-的-kimi-与-omp-独立决策身份) 或 [DSH 与 Hermes](#win-work-的-dsh-与-hermes-独立决策身份)。

| win-work 运行时 | 共享 OAuth 条目 | 已验证的只读查询 |
|---|---|---|
| Kimi | `decision-service` | Kimi 2.7.2 首次加载可能晚于模型工具清单的生成。确认运行时已发现工具后，恢复原会话并实际查询。[CLOU-31](http://10.207.56.3:3000/cloud-work/issues/CLOU-31) |
| DSH | `decision-service-dsh` | 此前未挂载决策 MCP 的验证角色，在首次查询时复用了现有登录。[接入说明](../deployment/decision-access/dsh/README.md) · [CLOU-35](http://10.207.56.3:3000/cloud-work/issues/CLOU-35) |
| Hermes | `decision-service-hermes` | 知识管理员和新建角色各自完成新会话只读查询。[接入说明](../deployment/decision-access/hermes/README.md) · [CLOU-37](http://10.207.56.3:3000/cloud-work/issues/CLOU-37) |

1. **选职责与样本。** 先核对 Multica 工作区已有岗位，再依项目原任务定义角色职责、输入、允许的动作、交付物、回报位置和验收人。例如，软件实现工程师在指定仓库修正一个边界条件，交付差异和可重复的断言，由独立审查员在原卡复核。[Multica 岗位与交办规范](../skills/workspace-coordination/SKILL.md#谁负责什么)
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
5. **让决策能力随角色配置。** 新建或调整已启用决策 MCP 的角色时，核对实际调用身份、目标项目服务端权限和岗位采纳权，挂载 `decision-service` Skill。在自定义 prompt 写明下一步明确时直接做、缺事实先查、有实质取舍主动调用、超出职责沿原卡转交。审查和研究等岗位按职责提供取舍建议及证据，由指定负责人决定采纳，独立验收仍按原约定执行。读回 prompt、MCP、Skill 及授权，对已取得目标项目业务权限的执行角色，再在该项目的新会话做两个小样本。对限于建议或仅获测试授权的角色，按本职验收建议、转交和授权边界。查看明确路径样本的工具轨迹和交付验证，查看实质取舍样本的一条决定、所选动作与反馈。换入口或撤销时同步检查提示词和真实权限。[主动推进与按需决策](../skills/workspace-coordination/SKILL.md#主动推进与按需决策)
6. **留下可追溯的结论。** 记录日期、主机、版本、Issue/Run、可复核产物及待验项。工具可用、Run 结束、角色能力通过、业务结果获负责人接受分开记录。角色调用范围用 `private` 或 `public_to` 表达。已有管理员允许整个工作区调用，是该角色经确认的例外。

win-work 的 Kimi 2.7.2 会话可在任务目录 `.kimi/skills/<名称>/SKILL.md` 读取 Multica 挂载的岗位 Skill。在原 Kimi 验收中，研究员和工程师都从这里读到了各自的三项正文；这些名称未列入它们的原生 `Skill` 菜单。共享记忆位于 `~/.kimi-code/skills/hindsight-memory`。配置新角色时可分别验收任务挂载和宿主入口。[研究员回执](http://10.207.56.3:3000/cloud-work/issues/CLOU-30) · [工程师回执](http://10.207.56.3:3000/cloud-work/issues/CLOU-29)

## win-work 同一 Run 内的原生子智能体

2026-11-23 在 win-work（Multica daemon 0.11.1）验证了四个 harness。新角色需要临时分工时，绑定对应的 win-work runtime，启用岗位所需工具，沿用该角色的工作区权限。父角色负责把每个子任务的结果带回本次 Run。可在岗位指令中写：「按子任务名称或 ID 核对收到的结果，收齐后汇总。超时或缺项时，说明哪一项待回。」单步任务由角色直接完成即可。

| Harness | 新角色怎么配、怎么收结果 | 实测原件（北京时间） |
|---|---|---|
| OMP 19.0.1 | 绑定 win-work OMP。现有配置提供原生 `task` 和 `wait`。批量调用的 `context` 要写实际上下文，空值会在启动前被拒绝。异步派发后按返回的作业 ID 调用 `wait`，读取完成状态和输出。 | 运维工程师的 `OmpProbe23` 经 `wait` 交回 `OMP-CHECK=714`，父 Run 于 09:39:38 完成。[验收会话](http://10.207.56.3:3000/cloud-work/chat?session=01a2060e-a28c-7809-b24f-259328a22381) |
| DSH 0.2.2-rc.3 | 绑定 win-work DeepSeek Harness，沿用 `dsh --profile multica --stdio`。现有 profile 暴露 `subagent`、`wait_agent`。给每个子任务起不同名称，等待各自的完成消息；一次等待返回可能只收到一份结果。 | 凡人项目负责人在 `fanren-work` 的隔离会话启动 `defer-alpha` 和 `defer-beta`。父会话的 `agent/inbox/spliced` 第 28、34 条先后收到 beta、alpha 的原文，第 42 条汇总两份结果。父 Run 于 09:47:49 完成。[负责人双子任务验收](http://10.207.56.3:3000/cloud-work/chat?session=01a20615-de33-7bbd-a767-79ad217bb956) |
| Kimi 2.7.2 | 绑定 win-work Kimi，沿用 `kimi acp`。同一 Run 需要收回结果时，调用原生 `Agent` 并设 `run_in_background=false`。按调用 ID 配对工具请求与响应，核对子智能体 ID、`completed` 和返回内容。 | 软件实现工程师调用 `explore` 子智能体 `agent-0`，工具返回 `KIMI-NATIVE-CHECK=146`，父 Run 于 09:39:15 回传并完成。[验收会话](http://10.207.56.3:3000/cloud-work/chat?session=01a2060e-24cf-71ce-926b-ceae7c4d68d9) |
| Hermes 0.23.3 | 绑定 win-work Hermes，在**角色环境变量**中增量加入 `HERMES_MULTICA_DELEGATION_MODE=inline`，保留原有变量，再开新会话。该变量由 win-work 的宿主配置读取。Hermes 的 `config.yaml` 已将原生 `delegation.gateway_mode` 配为 `"${HERMES_MULTICA_DELEGATION_MODE}"`，供 Multica 派生会话配置。父角色用 `delegate_task`，直接从本次工具响应读取子结果。 | 知识管理员首测只收到 `dispatched/background`，父 Run 随即结束。启用 inline 后，新 Run 的 `delegate_task` 返回子任务 `completed` 和 `JADE-223`，父角色原样回传，09:47:34 完成。[首测](http://10.207.56.3:3000/cloud-work/chat?session=01a2060e-43c2-743f-99c3-9cfa9813f548) · [通过的复验](http://10.207.56.3:3000/cloud-work/chat?session=01a20615-735f-7d96-91f3-64c09e9c632f) |

**新角色首验或升级复验。** 用目标角色在所属项目开隔离聊天，给每个子任务一份可独立核对的输入与输出标记。读回项目、实际角色、runtime 和父 Run ID，以 `multica issue run-messages <父Run-ID> --output json` 查看工具轨迹。按子名、作业 ID 或调用 ID 逐项对应**派发、子结果、父侧收到的内容**，再核父回复覆盖全部预期项且 Run 为 `completed`。工具只返回启动回执、等待超时，或父 Run 已结束但缺少任一份结果时，该项记为待核。DSH 的 `timedOut:false` 只说明等待返回；工具轨迹未展示子正文时，可核对该父会话原生收件事件与对应子会话的最终输出。

凡人负责人的双子用例验证了乱序收齐，其余三项各验一个子智能体。以上结果覆盖当次绑定和明确调用，跨 Run 后台续跑、取消恢复及最大并发仍待专项验证。OMP、DSH、Kimi 直接复用已有配置，只有 Hermes 知识管理员新增了角色级 inline 设置。四项均沿用运行中的 daemon。Hindsight bank `multica-4-dot` 可按文档 ID `multica-win-work-native-subagents-20261123` 查验收记录。

## win-work 的 Kimi 与 OMP 独立决策身份

**决策 MCP 优先级：低（研究分析师、运维工程师、Multica 系统管理员）。** 三个岗位优先交付本职任务。已有依据和明确步骤时直接执行；职责内有多个可行方案，且选择会明显影响交付或风险时，才按需调用。涉及项目方向或跨团队资源取舍时，沿原卡把证据和建议交给项目负责人或工作区协调员。后续适配和专项复验优先保障负责人、协调员；这三个岗位遇到实际任务受阻时再跟进。

以下为 2026-11-21 的 Windows 验收记录。研究分析师（当时使用 Kimi 2.7.2）、运维工程师和 Multica 系统管理员（OMP 19.0.1）的工作区均启用 `decision-service-agent`，三个角色各有一个服务端 `multica-agent-<Agent UUID>`。2026-11-21 核实三者的项目清单均含「Multica 运行时验证」与 `fanren-work`，独立决策身份的检索 bank 数为 0。以下实单只在验证项目执行，使用 `recall=skip`。平台账号和原生 MCP 的调用身份分别核对。[角色与项目授权](workflow-reporting.md#决策服务的项目与-agent-授权)

**OMP。** 两个岗位都在首个新会话直接使用已启用的工作区 HTTP 条目。OMP 的工具轨迹可能显示为 `read`、`write` 或 `eval`。先通过 `xd://` 查决策工具及 schema，再由动态工具调用 `get_decision`、`evaluate_decision` 和 `record_decision_feedback`。验收时核目标工具、实际请求号和服务端 caller。两个角色均沿用原运行时配置。

**Kimi。** 软件实现工程师曾在角色的独立 HTTP 入口实际收到 401。研究分析师与其使用同一 win-work 运行时，验收前将研究员的同名角色配置切到已验证的 stdio 适配器，仅保存 `command`、`args`，由子进程读取研究员自己的 Run 环境。新会话要同时看 MCP 的工具发现记录、模型工具表和原生返回。首轮工具缺席时，在原卡记录请求号和未执行项。查明既有决定和会话状态后，再从干净上下文续验。[固定步骤 CLOU-41](http://10.207.56.3:3000/cloud-work/issues/01a1fbec-00cc-7383-9df7-e49a4cac8a27) · [Kimi HTTP 修复与恢复 CLOU-42](http://10.207.56.3:3000/cloud-work/issues/01a1fbec-0372-72d0-84b8-b62bf7ebf92d)

研究员的反馈参数出现两类实测错误。修订号多次以负整数发出，证据引用数组被填成字符串。该角色的 stdio 适配器仅为 `record_decision_feedback` 提供一个 `event_json` 字符串参数。参数中写完整的 v1 事件，保留整数修订号和数组。适配器解析、检查修订号范围并以原字段转发，决定、身份和事件 ID 均沿原记录。参数格式变更后要开新 Kimi 会话，核对模型实际使用的 schema。验收只给决策工具时，可把完整合成输入随触发评论传入，由发起端读取 Run 的最终正文。[研究员适配器](../deployment/decision-access/kimi/decision_agent_stdio.py) · [转换与转发测试](../deployment/decision-access/kimi/test_decision_agent_stdio.py)

| 岗位与原卡 | 合成任务中的实测 | 接入或反馈的维护要点 |
|---|---|---|
| [Multica 系统管理员 · CLOU-46](http://10.207.56.3:3000/cloud-work/issues/01a1fc35-d479-71b3-ae06-0dc09362a804) | 采用 `drift-first`，核出 scheduler 期望 7、实测 6，inbox 为 4/4，audit 缺测并保留 `unknown`。 | 两次状态观察时间相同，首次统计为未知。沿原事件补一次有验收时间的结果修订 `rev2`，结果覆盖 1/1。业务执行与模型评估各一次。 |
| [运维工程师 · CLOU-47](http://10.207.56.3:3000/cloud-work/issues/01a1fc35-f72a-738a-8b5d-ba187965bd4f) | 采用 `queue-first`。先查得 reader-a 队列深度 88 超过阈值 60，再查得 reader-b 错误率 6.4% 超过阈值 5%。 | 采用与结果各有一条有效回执。结果主体漏了 `unit_id`，历史覆盖汇总为已收 0/应收 1。原件与附件已独立核对，原卡保留这一差异。 |
| [研究分析师 · CLOU-48](http://10.207.56.3:3000/cloud-work/issues/01a1fc36-1ef1-7d6d-aae3-d704032f796d) | 采用 `conflict-triage-first`，先列三个窗口，再核对正式修订 10:30 替代 09:00，保留转述的 09:30 和负责人归属待核。 | 冷启动首轮缺决策工具。在临时只开放三个决策工具的 Kimi 会话中，恢复会话并随评论传入样本后完成取证。反馈适配修复后，原决定的采用和结果各收一条，覆盖 1/1。验收结束后恢复日常工具配置，保留角色 stdio 入口。 |

两个 OMP 角色的提示词和协作 Skill 的反馈参考现已明确，首次回填固定主体单元、覆盖观察与原执行引用。读回时同时核有效事件明细和单元覆盖。已有回执且身份字段不可修订时，沿原卡说明差异，避免重复提交业务。[反馈字段与覆盖读回](../skills/workspace-coordination/references/decision-feedback.md)

## win-work 的 DSH 与 Hermes 独立决策身份

在 Multica v0.11.0，角色的工作区 MCP 分配、服务端项目权限、模型实际拿到的工具分属三层。新建角色时按下面顺序配置。2026-11-21 验收覆盖 `cloud-work` 的三位角色。两项授权项目为「Multica 运行时验证」和 `fanren-work`，新会话的合成样本均在前者执行。共享 GitHub OAuth 当天仅覆盖 `decision-service-smoke`。

### 新角色先领身份，再接运行时

1. 取新 Agent、工作区和目标项目的原生 UUID。在角色上启用工作区条目 `decision-service-agent`，挂载 `decision-service` Skill。管理员从能列全项目的身份预览授权同步范围，再按批准范围应用。服务端应读回唯一 `multica-agent-<Agent UUID>`、完整项目 UUID 清单和该身份的 bank 权限（本批为 0）。`DECISION_AGENT_TOKEN` 随本角色的 Run 注入。新增项目按项目登记流程再同步。配置与交接材料只写变量引用。[授权同步与撤销](workflow-reporting.md#决策服务的项目与-agent-授权)
2. 在自定义 prompt 写明岗位可以决定什么。质量审查员可选补测顺序，按原件判定质量。辩证复核专员交建议和异议，由负责人决定采纳。知识管理员可选索引编排，冲突事实与正式合并由有权者裁定。直做、查证、按需决策及反馈遵循同一协作规则。[岗位决策规则](../skills/workspace-coordination/SKILL.md#主动推进与按需决策)
3. 按相应 harness 完成下方接入，保留该角色其余 MCP、模型和记忆配置。迁移的角色停用自己的旧 `decision-service-dsh` 或 `decision-service-hermes`。读回 workspace 分配、角色同名配置和 prompt，再以该角色启动新会话验收。

### DSH 的角色与目标地址

DSH `0.2.2-rc.3` 的 stdio 子进程会过滤令牌类环境变量。`multica` profile 的 `@multica-ai/dsh-runtime 0.2.0-private.1` 默认也未启用 HTTP 凭据模板展开。已部署的 `mcpConfig()` 适配只在 Agent UUID、服务名、HTTPS 地址、传输方式和唯一请求头全部匹配时启用 DSH 原生 `expandTemplates`，由本次 Run 的凭据提供者解析引用。

负责人批准后，把新 Agent 的 UUID 加入该适配的允许清单，用下述匹配测试核对新增角色与其他角色的行为，再在角色 `mcp_config.mcpServers` 增量合入以下条目。将占位地址换成已批准且与宿主规则完全一致的 HTTPS MCP URL。Multica 把 `type=http` 映射为 `streamable-http`。现有清单只含质量审查员 `ebe008e0-c3bf-455a-856c-453dcd34d0bd` 和辩证复核专员 `31cb4631-b558-4683-9e8b-64925d70b3b9`。

```json
{
  "decision-service-agent": {
    "type": "http",
    "url": "<已批准的 HTTPS MCP URL>",
    "headers": { "Authorization": "Bearer ${credential:DECISION_AGENT_TOKEN}" }
  }
}
```

**升级或回退。** win-work 的 `%USERPROFILE%\.multica\integrations\dsh\decision-agent-template-20261121.md` 保存了包外 diff、完整 SHA-256 和备份位置。先核包版本及 `%USERPROFILE%\.dsh\profiles\multica\node_modules\@multica-ai\dsh-runtime\dist\index.js` 的摘要，再查新版是否已原生支持等价约束。仍需适配时，在新版本候选文件上做 Node 语法检查，再验证匹配条件。获准角色走指定入口时应成功展开。换成未获准角色、其他服务名或 URL、stdio、缺少或多出请求头、错误模板时，均应跳过展开。原版 18 项检查使用的是当时的 `mcpConfig()`，升级时测试须针对新版实现。

只撤一位时，等其在途 Run 结束，停用该角色的独立 MCP 分配并移除同名角色配置，保留其他条目。退任时按授权同步流程撤销该身份并更新 prompt。全量回退同版宿主补丁时，先确认受影响角色均已空闲，比对现文件和备份的完整摘要，再恢复同目录 `index.js.before-two-role-decision-20261121.bak`。若包已升级，按新版本回退路径处理。回退后用新会话核对哪些角色已失去该项目能力、哪些仍可调用，并验证原有 Hindsight 工具。

### Hermes 的任务私有配置

知识管理员首次在 editor MCP 的 stdio 环境中传 `${DECISION_AGENT_TOKEN}`。Hermes `0.23.3` 的编辑器会话作用域无法解析该引用，新会话未得到决策工具，也没有产生决定。修复后，岗位专属启动器在任务前台网关启动前，用 daemon 注入的 CLI 与本 Run 身份核对实际 MCP 分配。经角色、工作区、任务身份及私有 `HERMES_HOME` 校验后，它在任务的 `config.yaml` 注册一个原生 stdio 条目，通过已有 Python/FastMCP 适配器 `decision-agent-stdio.py` 调用决策服务。配置中仅保留变量引用，实际值由该 Run 注入子进程。分配已停用或读取失败时，启动器移除其管理的条目，角色可继续其他工作。

新建 Hermes 角色时，先记录原 `command_name` 和固定参数，为新角色准备专属 runtime profile。用包外源码与检查程序为新 Agent、工作区 UUID 和任务目录生成专属启动器，校验后把新 profile 的 `command_name` 指向该程序。固定参数、上游 Hermes、模型和记忆沿新角色原配置核对。现有 `KnowledgeHermes.exe` 固定绑定知识管理员。其他角色经过它时只会启动原 Hermes。在 v0.11.0 的已验组合中，工作区 `decision-service-agent` 保持启用，角色级 `mcpServers["decision-service-agent"]` 设为 `{}`，使 ACP 跳过重复 editor 条目。验收时模型应得到一套决策工具。

**升级或回退。** win-work 的 `%USERPROFILE%\.multica\integrations\hermes\knowledge-decision\` 保存启动器、源码、检查程序和 `README.md`。知识管理员的 runtime profile 为 `5e3fe5af-f04c-4238-be35-a2e1f8cd0aae`。升级 Hermes、Multica daemon 或 stdio 适配器后，先核实际命令和版本，在该目录用 PowerShell 运行 `.\KnowledgeHermesCheck.exe .\KnowledgeHermes.exe` 检查候选启动器，再做下表的新会话验证。重点检查错误角色或任务目录、缺少凭据或撤销分配、重复注册、移除后原 YAML 内容，以及原有 Hindsight 与 `node_repl` 工具。

回退知识管理员时，等在途 Run 结束，在 win-work 用以下 PowerShell 命令把该 profile 指回原受管程序（原固定参数为空）。读回命令和参数，用新会话验证原 Hermes 与原有工具。其他角色按自己的原 profile 记录恢复。若同时退任，另按授权流程撤销对应 caller、角色环境与 MCP 分配，复核角色级覆盖的实际效果。

```powershell
multica runtime profile update 5e3fe5af-f04c-4238-be35-a2e1f8cd0aae --command-name "$env:LOCALAPPDATA\hermes\bin\hermes.exe"
```

### 升级后用什么任务复验

在「Multica 运行时验证」项目为受影响角色开合成验收卡，读回 `project_id` 并使用新会话。独立复验采用新的稳定 `request_id`。同一次验收的恢复和重试沿用原号与候选。先查原号，确认无记录后再 `evaluate_decision`（真实项目 UUID、`recall=skip`），用 `get_decision` 读回 `complete/suggested`。发起端核对服务端 caller、唯一决定、Run 工具轨迹、岗位产物与反馈。`not_found` 只证明该身份能查询该请求号。配置恢复后也按相同边界复验。下表记录接入当日的合成实测，生产整包升级与整包回退留待实际维护窗口验证。

| 原卡与岗位 | 可复用的验收标准 | 原卡实测 |
|---|---|---|
| [CLOU-43 · 知识管理员](http://10.207.56.3:3000/cloud-work/issues/01a1fc09-04c6-74e2-817a-e85f3f8c2dec) | 选一种索引编排，比较附件与宿主原件，保留冲突及有权裁定人。 | `source_first`。三份带版本来源、10:00 / 11:00 冲突和负责人缺口均保留。修复后的新 Run 产生一条决定，采用与结果反馈各一条。 |
| [CLOU-44 · 质量审查员](http://10.207.56.3:3000/cloud-work/issues/01a1fc0d-f318-7190-a075-14dea774a654) | 让工具选检查顺序，由审查员实际核对夹具的值和完整性。 | `duplicates-first`。观察到的三个值匹配，A 重复、C 缺失，完整性判定失败。接入验收通过，采用与结果反馈各一条。 |
| [CLOU-45 · 辩证复核专员](http://10.207.56.3:3000/cloud-work/issues/01a1fc0d-f7bd-7684-8f6b-703a5ca1887e) | 要求比较两条路线、说明推荐与改选条件，把采纳权留给负责人。 | 建议 `minimal-replay-first`，列清转查依赖的条件。`expects_application=false`，只回填建议交付的 `result`。 |

反馈格式错误时，先查同一决定。两张 DSH 卡首次把执行终态写成 `succeeded` 被拒，沿原事件改成 `completed` 后成功。已收事件保留原主体，后续质量变更沿同一事件递增修订。三卡的 `result` 入库时均为 `quality_status=pending`，最终验收另有发起端原卡回执。[反馈字段与修订](../skills/workspace-coordination/references/decision-feedback.md)

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
| 2026-11-21 | 将按需决策纳入现有和新增角色的 prompt 配置与新会话验收，补入服务端项目授权读回。 |
| 2026-11-21 | 据 CLOU-43～45 补录 DSH、Hermes 独立决策身份的配置、升级复验、回退与岗位验收。 |
| 2026-11-21 | 补入 CLOU-46～48 的 Kimi、OMP 角色独立身份实测、研究员 stdio 修复与两种反馈覆盖问题。 |
| 2026-11-22 | 新增角色库入口和 CLOU-40 知识管理员案例复用验收，补明正文摘要的核验方法。 |
| 2026-11-23 | 补入 win-work 四种原生子智能体的建角配置、父 Run 收齐结果的验收方法及隔离会话回执。 |
