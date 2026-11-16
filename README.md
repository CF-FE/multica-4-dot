# multica-4-dot

将 Multica 接入云端 Dot 的插件项目。Multica 负责执行与运行记录，Task Mailbox 负责持久回执，Dot 负责协调、核对与汇报。当前有设计文档与后端操作 Skill，尚无已部署的 MCP 或插件服务。

| 文档 | 内容 |
|---|---|
| [架构与决策](docs/architecture.md) | 组件分工、部署拓扑、备选方案、网络和凭据边界 |
| [插件能力清单](docs/plugin-inventory.md) | MCP、Skills、权限、数据契约与未来目录 |
| [分阶段验证方案](docs/validation-plan.md) | 验收门槛、故障注入、回滚与待决事项 |
| [后端接入决策](docs/backend-integration.md) | REST、CLI、Decision MCP 与 GitHub Projects 的边界 |
| [后端操作 Skill](skills/multica-backend/SKILL.md) | [认证与调用](skills/multica-backend/references/access.md) · [v0.9.0 全量 CLI 命令](skills/multica-backend/references/cli-v0.9.0.md) |

状态：基础 v0.1，后端接入 v0.2 提案（2026-11-16）。评审通过不等于授权部署。本库不存真实地址、任务内容、凭据或运行配置。
