# multica-4-dot

将 Multica 接入云端 Dot 的插件项目。Multica 保存任务与运行记录，Task Mailbox 保存跨端回执，Dot 负责协调、核对与汇报。Vultr 已部署独立 MCP，提供 OAuth、按实例读取、项目和 Issue 操作，以及持久派发对账。公网和原生客户端的各项验收见[工程任务](docs/multica-backend-tasks.md)。

[mcp/](mcp/README.md) 存放服务端实现和契约测试，[plugin/](plugin/) 存放云端 Dot 的装配素材。上游发行跟踪与版本适配共用同一套[兼容约定](docs/decisions/005-upstream-compatibility.md)。

| 文档 | 内容 |
|---|---|
| [Multica Backend MCP 部署、配置与升级手册](deployment/multica-backend/README.md) | 首次部署、查看现网、改后端地址、新增实例、换 PAT、MCP 换版回退，以及跟进腾讯云 Multica 升级。 |
| [Multica Backend MCP 决策与任务](docs/backend-integration.md) | Dot 直连的五项 ADR、并行任务、版本跟踪及能力验收。 |
| [G8 与工作区协调员职责和协作规范](skills/workspace-coordination/SKILL.md) | 适用于所有工作区的权限、找人、决策、下令和回报约定。 |
| [工作流、通知与跨端汇报方案](docs/workflow-reporting.md) | Multica 原生编排、给公子和云端 Dot 的汇报、Mac 协调桥退役与试点判定。另见[腾讯云异常补报实测](docs/tencent-run-reporter.md)。 |
| [角色创建与 Harness 选型指南](docs/harness-role-guide.md) | 找人可直达[工作区协调员 Mike](docs/harness-role-guide.md#工作区协调员-mike)。按岗位和主机选型可查[架构比较](docs/harness-role-guide.md#架构比较)、[速度与 Token](docs/harness-role-guide.md#速度与-token)及[资料索引](docs/harness-role-guide.md#资料索引)。 |
| [架构与决策](docs/architecture.md) | 组件分工、部署拓扑、备选方案、网络和凭据边界 |
| [插件能力清单](docs/plugin-inventory.md) | MCP、Skills、权限、数据契约与未来目录 |
| [分阶段验证方案](docs/validation-plan.md) | 验收门槛、故障注入、回滚与待决事项 |
| [win-work 项目记忆接入](docs/win-work-hindsight.md) | OMP、DSH 与 Hermes 的 Hindsight 项目绑定、召回、留存和验证 |
| [腾讯云升级手册](docs/tencent-upgrade.md) | Compose 版本更新、数据库与附件备份、验收、旧镜像清理和迁移后的回退 |
| [后端操作 Skill](skills/multica-backend/SKILL.md) | [认证与调用](skills/multica-backend/references/access.md) · [v0.11.0 CLI 命令](skills/multica-backend/references/cli-v0.11.0.md) · [v0.10.0 历史参考](skills/multica-backend/references/cli-v0.10.0.md) · [v0.9.0 历史参考](skills/multica-backend/references/cli-v0.9.0.md) |

基础架构与后端接入保留 v0.1、v0.2 的历史提案。2026-11-20 已采纳的工作流、通知和跨端汇报决策见[实施核对](docs/workflow-reporting.md)。本库不存真实地址、任务内容、凭据或私有运行配置。
