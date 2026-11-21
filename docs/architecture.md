# 架构与决策 · v0.1

状态：提案，未部署、未进行线上验证。本文是可公开版本；机器身份、地址、凭据及项目原始数据另行受控管理。

当前项目进度与验收入口见[工作区协调规范](../skills/workspace-coordination/SKILL.md#谁负责什么)。历次后端接入方案见[设计记录](backend-integration.md)。

2026-11-20 更新。工作流转向 Multica、Mac 协调桥退役范围和跨端汇报的候选设计见[工作流、通知与跨端汇报方案](workflow-reporting.md)。下文保留 v0.1 的提案背景。

## 目标与非目标

让云端 Dot 能有边界地查看 Multica Issue 和 Run，之后在授权范围内做单次派发与收件。保留现有 Task Mailbox 和协调层，能追溯、能对账、能撤回。首期不迁移生产任务，不自动同步两套看板，不开放原始日志，不开通实时事件或写操作。

## 推荐拓扑

| 角色 | 建议落点 | 职责 |
|---|---|---|
| 控制面 | 腾讯云 VPS | Multica Web、API 和独立 PostgreSQL 17；保管 Issue、Run、上传文件 |
| 执行面 | mac-work 优先候选，win-work 可替换 | Multica Daemon 领取 Run，同机调用 Codex 或 Kimi CLI；用专用用户/隔离目录 |
| MCP 接入与回执中转 | Vultr VPS | 复用已授权的 Task Mailbox 入口；如需 G8 脱离本地工作机后稳定查询，再加独立窄接口 Multica MCP |
| 上游协调 | 云端 Dot（G8） | 下达获授权的目标、查原始状态、核对回执；不默认替代项目协调员 |
| 项目记忆 | Hindsight 项目 bank | 保留架构、决策和已验证经验；不是队列、去重表或业务验收来源 |

日常人工入口是 Web；能访问同一 API 的官方管理 CLI 或支持自托管的 Desktop 也是入口。Multica CLI 是管理/连接工具，Daemon 是领取任务和驱动本机执行的进程，Codex/Kimi CLI 才是执行器。不把三者装在腾讯云只是为了「方便」，也不假定现有登录、PATH、MCP 能力自动继承。[自托管快速入门](https://multica.ai/docs/self-host-quickstart) · [运行时](https://multica.ai/docs/daemon-runtimes) · [CLI](https://multica.ai/docs/cli) · [Desktop](https://multica.ai/docs/desktop-app)

- **管理链路**：首个只读验证，G8 经已授权工作机的 Multica CLI 查询；若需无人值守，再走 G8 → Vultr MCP（保持已认证的外部 HTTPS 入口）→ EasyTier → 腾讯云私网 HTTP → Multica API。
- **执行链路**：Multica API ↔ Daemon（工作机主动连接）→ 同机 Agent CLI。模型与工具外联发生在实际运行组件上；腾讯云不能访问的站点不默认经 Vultr 代理。部署镜像获取和所用外部集成须分别验证。
- **回执链路**：协调 Agent 通过受限 MCP 报告到原 Task Mailbox 任务，G8 现有巡检读取。若 Run 已失败或终止仍无回执，桥接器可作为后续方案读取原 Run 补报「观察到的异常」，不冒充 Agent、不代为验收。回执写入资格和游标是否涵盖相应事件必须在样本验证。
- **可选唤醒**：需要即时收到时，可评估由桥接器在回执持久化后发送专用 Slack 频道信号（只含非敏感引用），G8 被唤醒后回信箱读取。频道权限、机器人消息支持、去重和降级均未验证；不做双向机器人互相触发。Autopilot webhook 是入站；Multica 插件事件钩子可另验版本、验签与投递语义，只当状态信号，不能当完整业务结果或 Dot 的直接入口。[Autopilots](https://multica.ai/docs/autopilots) · [上游插件类型](https://github.com/multica-ai/multica/blob/main/packages/core/types/plugin.ts) · [回调能力记录](https://github.com/multica-ai/multica/issues/8913) · [OpenAI 事件触发](https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt)

## 决策与反证

| 提案 | 价值 | 反证、切换条件 |
|---|---|---|
| A. 腾讯云 Web/API/PG17 同机，工作机执行 | 移动部件少，数据库无跨机 RTT，不耦合生产信箱 | 2 核 2 GB 仅作为轻试点假设；镜像获取、持续负载或磁盘演练不过，先扩容或评估同域独立 PG |
| B. Web/API 腾讯云，PG 装 win-work | VPS 更省内存、可独立给 DB 扩容 | 每次跨机查询都受网络影响，连接池、迁移、备份、容灾变复杂；现有信箱 PG 实例不可共用，PG18 未验证；可选另一套专用 PG17，不是首选 |
| C. 两个公网 VPS 直接对接 | 路径短、容易做来源白名单 | 白名单只管可达性，不加密 HTTP；若不走 EasyTier，选 SSH 转发或经过正常验证的 HTTPS，不在公网传明文凭据 |
| D. EasyTier 中跑 HTTP | 私网受控并加密时，无需给腾讯云内部 Multica 做证书发行 | 只允许需要的节点，验证加密和中继信任，实测容器路由；若路由、身份或加密不可证，不能放宽到公网明文 |
| E. 仅用现有 CLI，暂不上云端 MCP | 实施最小，最适合验证 API/权限 | 依赖已连接且已获授权的管理环境；有明确无工作机依赖需求再加 Vultr MCP |
| F. 一开始就直接事件驱动 | 结果更快送达 | 增加新权限、重试/验签、漏报对账和通知负担；先持久回传，事件只做加速，不替换真相来源 |

## 网络、数据库、凭据

- API 初期只在 EasyTier 虚拟网卡上经反代开放指定端口（例如 18080），上游指向回环绑定的 API；腾讯云公网不映射 Multica Web/API/PG 端口。主机策略按虚拟地址限制 Vultr，工作机如需访问另列；API 独立认证。明确区分安全组和主机网卡访问控制，实际从容器和非授权节点分别验证。EasyTier 互通不等于流量加密和可信中继；受控网络优先，公网共享中继需核对身份约束。[EasyTier 安全模式](https://easytier.rs/en/guide/network/secure-mode.html)
- Web 若也走私网 HTTP，按官方同源反代设置浏览器访问源、相对 API 路径、`/ws` Upgrade 透传；单 IP 访问时不填 `COOKIE_DOMAIN`。按实际版本核对登录、会话、浏览器和 Daemon 的长连接。API 健康检查不能替代它们。[反代与 Cookie](https://github.com/multica-ai/multica/blob/main/SELF_HOSTING_ADVANCED.md#cookies)
- 要求 PostgreSQL 17，硬依赖 `pgcrypto` / `pg_trgm`，不需要向量化。捆绑镜像历史名称含 pgvector，不代表业务依赖。可选的 `pg_bigm`、`pg_cron` 不作为首期条件。若外置 PG，按锁定版本核对实际容器 DSN、Compose 依赖、迁移权限、TLS 或私网路径，并演练恢复 DB 与上传卷。[数据库设置](https://github.com/multica-ai/multica/blob/main/SELF_HOSTING_ADVANCED.md#database-setup) · [上游 Compose](https://github.com/multica-ai/multica/blob/main/docker-compose.selfhost.yml)
- PAT 跟随账户权限，不等于只读。最小权限隔离账号 + MCP 服务端工具白名单 + 对象授权共同约束；秘密只到执行该 API 的服务，不注入模型提示、通用 Agent 配置或日志。业务对象内容是不可信数据，不能引发自动派发或扩权。[认证与令牌](https://multica.ai/docs/auth-tokens) · [自托管安全模型](https://multica.ai/docs/security-model)
- 已知证据只有管理工作机曾可达腾讯云公网 ICMP；不是 Vultr EasyTier、容器 HTTP、模型网络或稳定承载能力的实测。未连接真实实例，不将文档支持当作本地部署确认。
