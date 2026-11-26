# Multica Project Rules

项目进度、负责人、复审和验收结论统一以所属 Multica 项目看板和原 Issue 为准。创建 Multica 任务时遵循后端 Skill 的[任务项目归属规范](skills/multica-backend/SKILL.md#任务项目归属)。

G8 下发已授权任务、查询与回收反馈、从全局提出方案或受托起草 ADR，以及 Multica 内找人、解阻与决策时均遵循[职责与协作规范](skills/workspace-coordination/SKILL.md)。新工作区按现任协调员登记接入。

## Multica 升级规范

每次升级锁定一个已获准的官方 tag 和完整提交，按服务端、CLI／Daemon、Skill、MCP 逐项核对。服务端前后端与本轮升级的宿主以同一 Multica 版本为目标。分批升级时记录各处实际版本、兼容证据和补齐计划。MCP 记录自己的发布版本或提交，以及通过验收的 Multica 服务端版本。

1. **服务端**。按[腾讯云升级手册](docs/tencent-upgrade.md)使用 `/opt/upgrade-multica.sh`。先核官方 tag、目标平台和已准备镜像的官方摘要。停服前核对在途 Run，强制切换须得到明确授权。备份并校验数据库、附件和配置，完成隔离恢复与迁移演练，再检查实际镜像、数据库与迁移状态、API readiness 和 Web 入口。
2. **CLI 与 Daemon**。沿用宿主原安装方式。macOS Homebrew 使用[本地 CLI 升级脚本](scripts/upgrade-multica-cli.sh)。分别读回 CLI 和运行中 Daemon 的版本。重启前确认该运行时空闲，重启后核对工作区和新心跳。有实际领单验收授权时，沿既有验证卡核对 Run 终态、真实输出和回传。按[后端 Skill](skills/multica-backend/SKILL.md)操作。
3. **Skill**。更新仓库里的部署基线、CLI 差异和现行引用，保留历史实测。按[平台同步步骤](skills/multica-backend/references/access.md#管理员挂载技能)用原 Skill ID 更新目标 Multica 工作区中的同名 Skill。读回线上版本、正文、所需参考文件和既有 Agent 挂载，再确认这项完成。
4. **MCP**。对照目标版的 API 和授权差异，跑本仓库契约测试，并通过已部署 MCP 读回项目、Issue 和 Run。需要修改契约或封装已获准的新能力时，先隔离验证受影响的写入和回执，再按 [MCP 部署手册](deployment/multica-backend/README.md)发布到原部署主机。
5. **回执**。在原升级记录写明各项目标版本、实际版本、检查结果和证据链接，分别记录仓库 Skill 与平台 Skill 的同步结果。腾讯云服务端回执统一追加到[升级手册](docs/tencent-upgrade.md#升级回执)，其他入口引用这份记录。

## unblock 版本兼容

**unblock 复用宿主当前 Multica CLI，以所需能力和实际回执判定兼容。** 发布提交、实测版本仅用于追溯和回退。禁止以版本号、构建提交或版本白名单作为启动门槛，或为此另装旧版 CLI。升级时复验关键能力；发现接口变化，修复对应适配并保留缺项诊断。公子于 2026-11-21 确认。[复验步骤](docs/unblock-operations.md)

## Runtime and Agent Defaults

- 公子于 2026-11-16 明确确认：后续配置 Multica 智能体及运行时，默认启用工具，执行权限限定为工作区（`workspace-write` 或运行时的等价模式）。
- 保留读取任务、执行工作区内操作和回传结果所需的工具能力；不要自行增加“禁止工具、命令、文件操作”等默认限制。
- 工具可用性与文件系统权限分别配置和验证。默认仍为工作区权限，不无条件改为全盘权限。
- 公子随后明确补充“可以提权”：在已授权任务需要时，允许运行时申请并使用更高权限，不统一设置为拒绝提权。权限提升应限于所需操作，不扩展到无关工作。
- 公子针对具体任务明确要求禁用工具、只读、禁止提权或其他权限时，遵循该任务的要求。更改默认权限后，应使用新会话验证，避免旧会话固定的权限覆盖新默认。
- 新建或调整智能体后，读回实际指令与运行时权限。验证任务必须同时检查 Run 终态和实际结果，不能仅凭 `completed` 判定通过。
