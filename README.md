# multica-4-dot

将 Multica 接入云端 Dot 的插件项目。Multica 保存任务与运行记录，Task Mailbox 保存跨端回执，云端 Dot 下发已获准的委托、回收进展与反馈，并从跨项目证据提出长期改进建议。Vultr 已部署独立 MCP，提供 OAuth、按实例读取、项目和 Issue 操作，以及持久派发对账。公网和原生客户端的各项验收见[工程任务](docs/multica-backend-tasks.md)。

[mcp/](mcp/README.md) 存放服务端实现和契约测试，[plugin/](plugin/) 存放云端 Dot 的装配素材。上游发行跟踪与版本适配共用同一套[兼容约定](docs/decisions/005-upstream-compatibility.md)。

| 文档 | 内容 |
|---|---|
| [项目交付与解阻方案图解](docs/share-doc/README.md) | 一张总图看架构与交付全程，一张详图看遇阻后由谁续办，附隔离验收证据。 |
| [Multica 角色库](docs/role-library.md) | 工作区负责人按交付物选用岗位模板，核对已有角色、职责和首单验收。 |
| [工作区 PowerShell 签名流水线](deployment/workspace-signing/README.md) | cloud-work 各项目在原卡申请内部签名，腾讯签发，win-work 以当前运行账号验签。 |
| [Multica Backend MCP 部署、配置与升级手册](deployment/multica-backend/README.md) | 首次部署、查看现网、改后端地址、新增实例、换 PAT、MCP 换版回退，以及跟进腾讯云 Multica 升级。 |
| [Multica Backend MCP 决策与任务](docs/backend-integration.md) | Dot 直连的五项 ADR、并行任务、版本跟踪及能力验收。 |
| [Multica 与云端 Dot 协作规范](skills/workspace-coordination/SKILL.md) | [云端 Dot 的提案职责](skills/workspace-coordination/SKILL.md#g8-如何提出值得采纳的建议)，以及各工作区的交办、接手、解阻和验收分工。 |
| [项目解阻闭环](docs/project-unblock-loop.md) · [操作手册](docs/unblock-operations.md) · [ADR-006](docs/decisions/006-project-unblock-loop.md) | 原卡摘要、具名追证、单次核收、恢复与范围验收。 |
| [unblock 版本兼容规范](AGENTS.md#unblock-版本兼容) | **跟随宿主 CLI，按能力复验。** |
| [工作流、通知与跨端汇报方案](docs/workflow-reporting.md) | Multica 原生编排、给公子和云端 Dot 的汇报、Mac 协调桥退役与试点判定。另见[腾讯云异常补报实测](docs/tencent-run-reporter.md)。 |
| [角色创建与 Harness 选型指南](docs/harness-role-guide.md) | 找人可直达[工作区协调员 Mike](docs/harness-role-guide.md#工作区协调员-mike)。按岗位和主机选型可查[架构比较](docs/harness-role-guide.md#架构比较)、[速度与 Token](docs/harness-role-guide.md#速度与-token)及[资料索引](docs/harness-role-guide.md#资料索引)。 |
| [架构与决策](docs/architecture.md) | 组件分工、部署拓扑、备选方案、网络和凭据边界 |
| [插件能力清单](docs/plugin-inventory.md) | MCP、Skills、权限、数据契约与未来目录 |
| [分阶段验证方案](docs/validation-plan.md) | 验收门槛、故障注入、回滚与待决事项 |
| [win-work 项目记忆接入](docs/win-work-hindsight.md) | OMP、DSH 与 Hermes 的 Hindsight 项目绑定、召回、留存和验证 |
| [本地 Multica CLI 升级](#本地-multica-cli-升级) | macOS 上的 Homebrew CLI 版本检查与升级 |
| [腾讯云升级手册](docs/tencent-upgrade.md) | Compose 版本更新、数据库与附件备份、验收、旧镜像清理和迁移后的回退 |
| [腾讯云 Multica Go 与 iPhone IKEv2 运维手册](docs/tencent-multica-go-ikev2.md) | iPhone 私网接入、从零重建、真机验收、证书轮换和回退 |
| [后端操作 Skill](skills/multica-backend/SKILL.md) | [认证与调用](skills/multica-backend/references/access.md) · [v0.12.1 CLI 差异与实测](skills/multica-backend/references/cli-v0.12.1.md) · [v0.11.0 CLI 总表](skills/multica-backend/references/cli-v0.11.0.md) · [v0.10.0 历史参考](skills/multica-backend/references/cli-v0.10.0.md) · [v0.9.0 历史参考](skills/multica-backend/references/cli-v0.9.0.md) |

基础架构与后端接入保留 v0.1、v0.2 的历史提案。2026-11-20 已采纳的工作流、通知和跨端汇报决策见[实施核对](docs/workflow-reporting.md)。本库不存真实地址、任务内容、凭据或私有运行配置。

## 本地 Multica CLI 升级

适用于 macOS 上通过 Homebrew 安装的 Multica CLI。在仓库根目录运行以下命令。[升级脚本](scripts/upgrade-multica-cli.sh)

```bash
# 只读检查当前 CLI 版本、官方 tap 同步状态和本地配方版本
./scripts/upgrade-multica-cli.sh --check

# 更新 Multica tap、升级 CLI 并显示升级后的版本
./scripts/upgrade-multica-cli.sh
```

脚本保留旧版 CLI。系统启用静态 PAC 时，脚本使用其首选路由。使用按域名分流的 PAC 时，可通过 `MULTICA_UPGRADE_PROXY` 指定本次运行的代理地址。
