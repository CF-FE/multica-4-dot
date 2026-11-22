# Multica 角色库

按需要交付的结果选岗位，再用[角色创建与 Harness 选型指南](harness-role-guide.md#从角色要交付的结果开始)选主机和运行时。以下 9 个条目来自 2026-11-22 的两份本地检出。当天读回 `cloud-work` 的 12 个现有 Agent：代码审查和产品研究可由已有岗位承接，其余 7 个是角色模板，均待 Multica 首单验证。

| 需要什么结果 | 选哪个条目 | 在 cloud-work 怎样用 |
|---|---|---|
| 判断一项代码变更是否可合并 | 代码审查员 | 复用现有质量审查员 |
| 为缺陷补一项能失败的测试 | 测试工程师 | 候选；适合需要独立测试产物的任务 |
| 核清代码中的权限或数据风险 | 安全审计员 | 按需启用的专项候选 |
| 查慢页面的原因并量化影响 | Web 性能审计员 | 按需启用的专项候选 |
| 核清键盘、读屏等使用障碍 | 无障碍审计员 | 按需启用的专项候选 |
| 从用户材料找出值得验证的问题 | 产品与市场研究 | 复用现有研究分析师 |
| 把问题写成有取舍、可验收的需求 | 产品经理（需求与路线图） | 产品岗位候选，向项目负责人交方案 |
| 得到可复算的留存或实验结论 | 产品数据分析师 | 产品岗位候选 |
| 确定先向谁推出产品、如何判断有效 | 上市与增长策划 | 产品岗位候选 |

## 上游明确命名的五个工程角色

来源为 `addyosmani/agent-skills` 的本地标签 `0.6.17`、提交 `8c99fa36`。下列英文名与五份 persona 文件一一对应。表中试题用于 Multica 新会话验收。上游的 `/ship`、`/review` 等命令只作工作流参考，派发与签收沿 Multica 原 Issue 办理。[上游角色索引][engineering]

| 岗位与来源 | 适用输入、职责和工具 | 首单怎样验收 |
|---|---|---|
| **代码审查员** `code-reviewer` [原定义][review] | 读固定 diff、需求和测试，按正确性、可读性、架构、安全、性能审查。以 `code-review-and-quality` 补强现有质量审查员。 | 给出合并或返工建议，每条重要发现含文件位置、影响、依据和验证方法。实现者负责修改，验收沿原卡指定人办理。 |
| **测试工程师** `test-engineer` [原定义][testing] | 从公开行为、异常输入、系统边界中找覆盖缺口，选择单元、集成或端到端测试。获得任务授权后可写独立测试文件并运行；修复实现由软件实现工程师承接。 | 给一个已知回归和未修复版本，提交能稳定失败的测试、命令和失败原因；在修复版本上复跑同一测试，保留两次结果。 |
| **安全审计员** `security-auditor` [原定义][security] | 对给定代码变更做防御性审查，核对鉴权、数据流、敏感信息处理和依赖，结合 `security-and-hardening` 提出修复建议。 | 对合成的权限变更指出受影响对象、缺失的权限检查、源码位置和修复后的防御性测试；标明哪些判断仅来自静态阅读。 |
| **Web 性能审计员** `web-performance-auditor` [原定义][perf] | 分析指定页面的加载、渲染和网络。只有源码时列潜在影响；有 Lighthouse、CrUX 或 DevTools trace 时，将指标绑定到报告、路由与采样条件。 | 给一个路由及一份测量材料，区分实验室与真实用户数据，定位一项瓶颈并给出同条件复测办法。材料未测的 LCP、INP 或 CLS 标“未测”。 |
| **无障碍审计员** `accessibility-auditor` [原定义][a11y] | 检查关键流程里的语义、表单、焦点、键盘操作和对比度。自动检查、手动键盘操作和实际读屏各自产生证据。 | 用键盘走完一次表单提交或弹窗操作，报告具体控件、受影响用户、关联的 WCAG 2.2 成功准则和修复后复查步骤。只做键盘测试时，读屏表现仍待验证。 |

一般代码改动可由质量审查员先处理。需要新增可运行的测试、独立的安全复核、浏览器测量或辅助技术实测时，再选对应专项。安全、性能和无障碍岗位给出的建议由获授权执行者实施。

## 从产品工作流归纳的四个岗位

来源为 `phuryn/pm-skills` 的本地标签 `v2.3.0`、提交 `9af7bfd0`。本地有 9 个插件目录、72 个 `SKILL.md`、42 个命令文件；其中 `pm-ai-shipping` 的 3 个技能和 5 个命令是迁移说明。下表中文岗位名由本库按交付物归纳，上游提供对应的技能和工作流。[上游目录][pm] · [迁移说明][shipping]

| 岗位 | 核心工作流与可用技能 | 首单怎样验收 |
|---|---|---|
| **产品与市场研究**（现有研究分析师方向） | 从访谈、工单、反馈或竞品材料提取用户问题及反例。现有岗位已采用 `competitor-analysis`、`summarize-interview`、`sentiment-analysis`；有新问题时可补 `survey-design`、`user-segmentation` 或 `prioritize-assumptions`。[用户研究][research] · [产品发现][discovery] | 给一组脱敏原话和一条相反证据，按用户场景归类。每项洞察回指原话，注明样本局限，交最值得先验证的假设和实验。 |
| **产品经理（需求与路线图）** | 接受研究材料和产品约束，用 `product-strategy` 明确目标、取舍，用 `create-prd`、`user-stories` 和 `outcome-roadmap` 写一份可交工程团队的方案。项目负责人决定采纳，工作区协调员协调派发。[产品策略][strategy] · [需求文档][prd] · [结果导向路线图][roadmap] | 给一条模糊需求，交一份精简 PRD，列出目标用户、问题、成功指标、交付范围、一个明确延后的需求和可观察的验收条件。缺证据的假设单列。 |
| **产品数据分析师** | 根据事件表或脱敏 CSV 定义指标，用 `sql-queries`、`cohort-analysis` 或 `ab-test-analysis` 分析。数据库查询使用任务已有的只读权限；给出字段、查询和计算口径。[留存分析][cohorts] · [实验分析][ab] | 给一份含重复事件的小数据集，交付可复算的分群留存表，说明去重键、观察窗口、分子和分母。若做 A/B，另核样本量与不确定性。 |
| **上市与增长策划** | 给定产品简报、预算和客户证据，用 `beachhead-segment`、`ideal-customer-profile`、`gtm-strategy` 和 `positioning-ideas` 确定目标人群、定位、渠道与验证指标。向项目负责人交候选计划，预算和对外发布按原授权办理。[上市计划][launch] · [营销定位][marketing] | 用一页列出首批客户、选择理由、两项优先渠道、投入约束、里程碑和一个可量化的继续或停止条件。 |

其余能力按任务复用：`pm-execution` 的 `stakeholder-map`、`sprint-plan`、`pre-mortem` 适合 Mike；`strategy-red-team` 适合辩证复核专员；`test-scenarios` 可为测试工程师提供业务场景。`pm-toolkit` 的校对、简历和文书草稿属于按件调用的工具。保密协议与隐私文本如需正式采用，沿项目既有审阅流程办理。[执行工具][execution] · [通用工具][toolkit]

## Harness 选择与换选条件

下表提供首单候选。已通过的旧岗位样本可以证明某项工具能力，新模板仍需在所选主机完成自己的验收。

| 工作方式 | 首选或已有实例 | 换选或补验的条件 |
|---|---|---|
| 独立代码审查、结构化取证 | 复用 win-work DSH 质量审查员。mac-work Codex 有按线程复审、退回和再审的历史回执。 | 工作区要独立于实现者。性能与无障碍实测还需浏览器、测量材料或辅助技术；选了 DSH 或 Codex 只解决执行入口。 |
| 写回归测试、产品研究、PRD、上市方案 | win-work Kimi 已验证研究、文件交付和代码修改，可作为首单候选。产品数据分析先给固定 CSV 和可复算脚本。 | 涉及跨文件符号、语言服务或断点调试时可选 win-work OMP；上机先验相应工具。数据库权限和外部发布各自按任务办理。 |
| Windows 环境、服务与复杂调试 | win-work OMP 有运维回执，可调用本机工具；深度代码调试要核实际 LSP、DAP 和目标语言。 | 一般本地工具链也可用 DSH；高权限取决于宿主身份。 |
| 跨会话知识维护、案例去重 | win-work Hermes 知识管理员已在 CLOU-40 历史试跑中按症状召回、按原 ID 读回并反馈。 | 核正文哈希时直接对完整结构化原文的 UTF-8 字节计算；主机中断后的自动续跑仍待单独验证。 |

按所用模型、推理档位和同一验收任务比较耗时与 Token。计入失败、重试、摘要、顾问或子代理的用量，注明缓存命中和数据来源。跨 Harness 的快慢和成本目前缺少本项目同题对照。[架构与宿主证据](harness-role-guide.md#架构比较) · [实际推理档位](harness-role-guide.md#实际推理档位) · [速度与 Token](harness-role-guide.md#速度与-token)

## 角色创建指引

工作区负责人在有实际项目交付时按需建角。G8 可将本库入口交给目标工作区的现任协调员。

1. **先查谁能交付。** 核对工作区、项目、在任角色、能力和当前任务。能用现有角色完成就沿原 Issue 交办；需要独立审查、专用工具或不同权限时，记录单设岗位的具体理由。选定库中条目、上游来源和首单样本。
2. **把职责写成可验收的 prompt。** 填写目标、输入及版本、允许的操作、输出和验收条件、验收人、原卡回报对象。按岗位写清谁执行、谁复核、谁能批准；有实质取舍且已获准决策 MCP 时才调用。解阻经验按[协作规范](../skills/workspace-coordination/SKILL.md#阻塞案例的检索沉淀与反馈)沿原卡查证。
3. **按任务选 Harness 和权限。** 对照目标主机的实测能力，核实具体 Skill、MCP 和执行身份。默认启用工具、工作区写入；提权限本次已授权动作。项目记忆绑定当前项目 bank，跨项目按已获准范围只读。调用范围、并发和模型推理档位按岗位设置并读回，示例角色的凭据或权限不随模板继承。[Harness 选型与配置步骤](harness-role-guide.md#建一个可以验收的角色)
4. **创建后用新会话验一单。** 读回 Agent ID、实际指令、运行时、工具和权限。将最小验收样本放在所属 Multica 项目，沿原 Issue 发起并读回 `project_id`。核对实际执行者、Run 终态、交付物和验收条件；证据不足的能力标待验。由指定验收人确认适用范围后，登记宿主、验证日期、Issue/Run 与产物。升级或换绑时只复验受影响能力。

**可套用的指令。** “你负责〔岗位及交付目标〕，在〔项目与授权范围〕内，依据〔输入和版本〕完成〔动作〕。在〔原 Issue〕提交〔产物、验证命令或证据〕，由〔验收人〕按〔标准〕验收。需要扩大权限或作业务取舍时，交〔有权负责人〕。”

例如，测试工程师的首单可以是：“在指定工作区为原卡所述缺陷写一个独立回归测试。先记录未修复版本的失败原因，再对修复版本复跑同一命令；把测试文件、两次结果和剩余覆盖缺口交原卡审查员。”

[engineering]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/docs/agents.md
[review]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/agents/code-reviewer.md
[testing]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/agents/test-engineer.md
[security]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/agents/security-auditor.md
[perf]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/agents/web-performance-auditor.md
[a11y]: https://github.com/addyosmani/agent-skills/blob/8c99fa36d90068c82d547f7c12a9d67a3e95f4ee/agents/accessibility-auditor.md
[pm]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/README.md
[shipping]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-ai-shipping/README.md
[research]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-market-research/commands/research-users.md
[discovery]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-product-discovery/commands/discover.md
[strategy]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-product-strategy/commands/strategy.md
[prd]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-execution/commands/write-prd.md
[roadmap]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-execution/skills/outcome-roadmap/SKILL.md
[cohorts]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-data-analytics/commands/analyze-cohorts.md
[ab]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-data-analytics/commands/analyze-test.md
[launch]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-go-to-market/commands/plan-launch.md
[marketing]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-marketing-growth/commands/market-product.md
[execution]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-execution/README.md
[toolkit]: https://github.com/phuryn/pm-skills/blob/9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef/pm-toolkit/README.md
