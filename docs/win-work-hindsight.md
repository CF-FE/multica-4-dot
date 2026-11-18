# win-work 上的 OMP、DSH 与 Hermes 项目记忆接入

本方案适用于 win-work 上需要使用 Hindsight 的 OMP、DSH 和 Hermes 会话。各运行端复用 Windows 本机的 Hindsight 1.2.0。项目已有 `multica-4-dot` bank，运行端通过显式项目绑定使用原库。接入状态见[验收](#验收)。

## 使用约定

| 能力 | 使用方式 |
|---|---|
| 自动召回 | 新会话进入首轮时查询当前绑定的项目 bank，按任务相关性注入背景。同一任务持续使用已确认的项目身份。 |
| 手动留存 | 有可复用经验时，由执行者选取必要内容，写入当前获准项目的 bank。记录原任务、观察时间、来源和未证实事项。使用稳定文档 ID，补写前读回对账。 |
| 跨 bank 查阅 | 在原授权范围内显式指定另一个 bank，用 `get_document` 查固定文档 ID，或用 `recall` 按问题查找。查阅期间，当前会话仍按原项目绑定召回。 |

项目绑定决定请求路由。实际权限由服务身份及其授权范围决定。默认 bank 缺失、未知或与当前任务不符时，先从项目登记核实绑定。其他 bank 的只读范围同样需要明确来源。Hindsight 用于补充上下文和保留经验，运行状态、实际产物和业务验收仍沿原任务核对。

## 连接与凭据

Windows 原生客户端使用现有 loopback REST 根地址 `http://127.0.0.1:8888`，由各客户端拼接 `/v1/default/banks/...`。Mac 的现有 LAN SSH stdio 入口和 VPS 的 HTTPS 网关各有自己的连接方式。VPS `/hindsight/api` 接收工具名与参数，和原生 Hindsight REST 路由属于不同接口。 [Win 服务与路由合同](https://github.com/CF-FE/herdr-4-codexcloud/blob/742ab342355b32b70e2bac5ab8cc64290d56e23b/mcp/hindsight-memory/CONTRACT.md) · [OMP REST 客户端](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/hindsight/client.ts#L277-L361)

从 Windows 已有的受控凭据来源，把 bearer token 仅交给相应启动进程。OMP 识别 `HINDSIGHT_API_TOKEN`。平台的项目配置只保留 bank 路由及行为开关，凭据留在本机私有配置。避免将值写入仓库、角色提示、命令行、工具报告或工作区附件。Hindsight 内置 `ApiKeyTenantExtension` 使用 tenant key 授予配置 schema 的访问权。需要技术性限定到单 bank 时应由服务或受限入口执行校验，仅设置默认 bank 只会影响客户端路由。 [Hindsight 1.2.0 认证逻辑](https://github.com/vectorize-io/hindsight/blob/34a138684a899b6ec34175f7a2b633860466d289/hindsight-api-slim/hindsight_api/extensions/builtin/tenant.py#L44-L79)

## OMP 原生后端

win-work 的 OMP v18.22.2 用 `~/.omp/agent/config.yml` 启用内置 `memory.backend: hindsight`。`~/.omp/agent/extensions/hindsight-project-binding.ts` 在会话启动时解析项目，应用 loopback 地址、当前 bank 和运行行为。`~/.multica/integrations/hindsight/omp-project-banks.json` 集中登记项目绑定。Multica Run 先用 `.multica/daemon_task_context.json` 的 `managed_by=multica-daemon-task` 确认运行来源，再用 `.multica/project/resources.json` 的 `project_id` 按 workspace 和项目 ID 精确匹配。普通 Git checkout 按登记的规范化 origin 匹配。匹配失败时关闭自动召回，原生连接保持无 API 地址、无 token，仍可走只读桥显式查已获准的 bank。在新 OMP 会话用 `/hindsight-project` 核对生效项目和 bank。

```json
{
  "multicaWorkspaces": {
    "<workspace-directory-key>": {
      "<project-uuid>": "multica-4-dot"
    }
  },
  "githubOrigins": {
    "cf-fe/multica-4-dot": "multica-4-dot"
  }
}
```

用 `omp --version` 和 `omp config path` 核对实际二进制及配置目录。下面展示已绑定示例的有效字段。全局 profile 配置与项目绑定分开维护。 [OMP 配置加载顺序](https://github.com/can1357/oh-my-pi/blob/v18.22.2/docs/settings.md#precedence)

```yaml
memory:
  backend: hindsight
hindsight:
  apiUrl: http://127.0.0.1:8888
  bankId: multica-4-dot
  scoping: global
  globalScope: false
  autoRecall: true
  autoRetain: false
  mentalModelsEnabled: false
  mentalModelAutoSeed: false
```

`scoping: global` 在 OMP 中表示使用指定 bank 名称，不按当前目录改名或加筛选标签。为此应保持 `bankIdPrefix` 为空，并核对可能覆盖配置的 `HINDSIGHT_BANK_ID` 和 `HINDSIGHT_SCOPING`。`autoRecall` 在新会话的首轮读取。`autoRetain: false` 关闭按对话轮次自动留存。两项 mental model 开关同时关闭，因为启动加载可能先向 bank 发起 PUT，默认自动种子也能新增远端对象。 [OMP 项目作用域](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/hindsight/bank.ts#L58-L113) · [OMP 启动与 mental model 行为](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/hindsight/state.ts#L510-L598)

原生 `recall` 使用当前绑定 bank。手动 `retain` 用于本项目授权的脱敏经验，调用前确认绑定，因为原生代码会先尝试确保 bank 存在。保持 `bankMission` 和 `retainMission` 未设，避免手动留存时附带配置更新。跨 bank 读取使用下述只读桥。 [OMP 原生 recall](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/tools/memory-recall.ts#L73-L99) · [OMP bank 初始化行为](https://github.com/can1357/oh-my-pi/blob/v18.22.2/packages/coding-agent/src/hindsight/bank.ts#L125-L166)

`~/.omp/agent/mcp.json` 的已有 Hindsight 条目指向共享只读桥，供按需跨库查询。该条目与 OMP 首轮自动召回走不同入口。2026-11-18 的项目绑定扩展 SHA-256 为 `be1897bfad13b442a25f2c1088c3a194ded95b33e28589f27262b431a6ee64cc`。

## DSH 原生后端

win-work 的 DSH `0.2.2-rc.3`（Node `24.18.0`）通过插件管理器将官方包 `@vectorize-io/hindsight-coding-agents@0.8.7` 固定在 `~/.dsh/profiles/multica`。重建时用 `dsh plugin --profile multica add @vectorize-io/hindsight-coding-agents@0.8.7 --save-exact --ignore-scripts`，核对 profile 锁文件和下述本机兼容改动。官方一键安装会影响共享配置，本接入采用指定 profile 的包管理方式。 [Hindsight 官方 DSH 集成](https://hindsight.vectorize.io/sdks/integrations/coding-agents#deepseek-harness) · [0.8.7 发布包](https://www.npmjs.com/package/@vectorize-io/hindsight-coding-agents/v/0.8.7)

私有目录 `~/.multica/integrations/dsh` 中的 `dsh-multica-workspace.cmd` 启动 Multica 专用 profile。预加载 `hindsight-project-binding.cjs` 先确认运行使用 `--profile multica` 且当前目录属于已确认的 Multica 工作区，再读取当次 `.multica/project/resources.json` 的 `project_id`。命中已确认项目使用 `hindsight-multica-4-dot.json`。未绑定或读取失败时使用 `hindsight-disabled.json`，DSH 任务继续，原生自动召回和写入均停用。绑定配置将 `bankId` 固定为 `multica-4-dot`，关闭 `dynamicBankId` 与 `resolveWorktrees`，避免随 Run 目录或 worktree 派生新库。

用 `autoInject: recall` 启用首轮召回。用 `retainSessions: false`、`autoSeed: false`、`codebaseSurvey: false`、`gitIngest: none` 和 `manageBankConfig: false` 关闭相关自动写入。禁用默认知识页及 `autoUpdate`，避免启动时修改共享知识配置或改变已核版本。公子明确要求保存经验时，可用 `hindsight_ingest_document` 向当前项目 bank 提交脱敏记录，按返回的文档 ID 读回。已安装的 `dsh-ops 0.5.5` 和 `workspace-write` 规则仍适用。

profile 用 `pnpm patchedDependencies` 固定兼容改动。补丁只修改该包的 `dist/dsh.js`，让加载器在本机 DSH 进程内利用既有凭据来源初始化客户端，并跳过首次会话往共享 skills 目录安装 Companion。补丁后文件 SHA-256 为 `830499e4cdfba10dc67ebd4ff88fef0ce7a4d7390d05913b83172c635649732f`。升级后先核上游是否已支持相同的凭据加载与安装行为，再处理补丁兼容性。

## Hermes 原生后端

复用 win-work 已安装的 Hermes Agent v0.19.0 及随安装提供的 Hindsight provider。仅在 Hermes 自己的 Python 虚拟环境补装 `hindsight-client==0.6.1` 和 `aiohttp-retry==2.9.1`。该 provider 支持 `local_external`，可连接现有的 Windows loopback REST 服务。 [Hermes v0.19.0 发布说明](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.20) · [随版本发布的 Hindsight provider](https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/plugins/memory/hindsight/__init__.py#L884-L923)

该主机的安装目录有 Git 元数据，但 `git rev-parse HEAD` 无法解析。上游 `v2026.7.20` 对应 commit `3ef6bbd201263d354fd83ec55b3c306ded2eb72a`，仅作为发布版本参照。本机 provider 的 Git blob 为 `00b6d7a8f8eaa462eb69f7238212144001bf2012`，SHA-256 为 `506fed3a78c0abe5f5d0dacc9927ac96eb8ff0e55e3af821dca5f9f3da3151af`。本机与发布标签的同路径文件不同，升级时按实际文件重新核对接口。

`$HERMES_HOME/config.yaml` 选用 `memory.provider: hindsight-multica`。本机扩展 `$HERMES_HOME/plugins/hindsight-multica/__init__.py` 复用原生 provider，只有确认工作目录属于 win-work 的 Multica 工作区且 `.multica/project/resources.json` 的 `project_id` 命中登记项目，才加载当前项目 bank，并在进程内读取本机凭据。其他目录或项目没有原生召回和原生记忆工具，仍可通过只读桥显式查阅。扩展 SHA-256 为 `6d7c2ec23228f19d9928b998983e04fe7ff4bf6702c4fafdbda9b03043d9aa73`。 [Hermes 本机插件加载](https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/hermes_cli/plugins.py#L1203-L1245)

项目命中后，`$HERMES_HOME/hindsight/config.json` 的有效配置包括以下字段。混合模式 `hybrid` 同时支持自动注入和显式工具，自动留存关闭。

```json
{
  "mode": "local_external",
  "api_url": "http://127.0.0.1:8888",
  "bank_id": "multica-4-dot",
  "memory_mode": "hybrid",
  "auto_recall": true,
  "auto_retain": false,
  "recall_prefetch_method": "recall"
}
```

若公子要求一条留存有稳定文档 ID 和读回回执，使用已获授权、能指定 `document_id` 的 Hindsight 写入入口。该版本的原生 `hindsight_retain` 只接收内容、上下文和标签，返回简短成功文本。 [Hermes 手动留存工具](https://github.com/NousResearch/hermes-agent/blob/v2026.7.20/plugins/memory/hindsight/__init__.py#L1560-L1588)

## 跨 bank 只读桥

OMP 的 Hindsight MCP 条目、DSH 的 `project-memory` 和 Hermes 的 `mcp_servers.hindsight` 共用 Windows 本机 stdio 入口 `~/.multica/integrations/hindsight/read-only-memory.py`。它只暴露 `get_document` 和 `recall`，要求显式传入已获准的 `bank_id`，拒绝 `default` 和写入调用。`get_document` 同时传稳定的 `document_id`，`recall` 传具体问题。桥读到的其他库证据按来源引用，当前原生后端仍写入原绑定项目。2026-11-18 桥 SHA-256 为 `c6e65640bc9f258f566e1869035d4a0f318956ab903dc72c867b86344615ed38`。

## 验收

1. 记录实际启动的工具版本、profile、工作目录和 bank。对比当前配置与环境覆盖，只回传必要字段。验证环境凭据存在时使用布尔结果。
2. 开一条新的隔离会话，询问已存的项目案例，例如 `CLOU-3 自动返工的次数和最终状态`。使用工具活动或启动日志确认实际 Hindsight 请求命中了 `multica-4-dot`，对照已知文档 `multica-dsh-review-rework-cases-20261117`。另查测试前后没有新增自动留存文档，仅凭会话答对或 `Run completed` 不能证明使用了记忆。
3. 查询另一个获准 bank 时固定 `bank_id`。`get_document` 需同时固定 `document_id`，例如在 `cf-fe-herdr-4-codexcloud` 读 `herdr-issue13-vps-bank-authorization-20261106`。`recall` 需固定查询问题。检查返回的来源属于目标 bank，并确认下一轮自动召回仍沿原项目。
4. 按授权留存一条可复用经验时，记录内容摘要和稳定 `document_id`。异步结果如返回 `operation_id`，查该操作结束后再按原文档 ID 读回。保存提交成功、内容读回和摘要校验三类证据。遇到未知写结果沿原 ID 对账。

首轮召回适合提供背景。已有回执需要精确数据时，对当前项目发起带任务编号的显式召回，然后按固定文档 ID 核对。

验收观察于 2026-11-18（Asia/Shanghai）。

| 运行端 | 已取得的证据 | 验收边界 |
|---|---|---|
| DSH | CLOU-8，Run `01a1edf4-a769-7e88-b038-c11912e2dba8` 17:21 完成。原生诊断确认 DSH、bank 和认证可用，日志记录 `session_start`、`inject_recall count=13` 和 `inject_ok`。自动注入未覆盖所问 CLOU-3 细节，后续显式召回找到相关条目。共享桥从 `multica-4-dot` 与 `cf-fe-herdr-4-codexcloud` 读回固定文档，独立 stdio 复测分别返回 27 和 6 条记忆单元。 | 本轮手动写入未实测。平台工具输出有 8192 字节截断，较大的结果用独立只读回执对照。桥拒绝写入调用和 `default` bank。 |
| OMP | CLOU-10，Run `01a1ee00-4f54-7b9c-9633-336c98f7628b` 17:35 完成。宿主会话记录 `memory_recall` 的 backend 为 Hindsight、bank 为 `multica-4-dot`，首个工具结果前已注入 3345 个字符。原生 `xd://recall` 返回 11 条，找到 CLOU-3 返工一轮的证据。共享桥两库的 `get_document` 均读回已知文档，随后对 Herdr bank 的 `recall` 返回 5 条，命中已知来源。 | 自动宽查未包含返工次数，由显式召回补足。本轮手动写入未实测。 |
| Hermes | win-work 新 CLI 会话 `20261118_175002_97f291` 退出码为 0，首轮发往模型的消息含 15 条 `<memory-context>` 记忆。模型无工具调用，正确回答 CLOU-3 的最终状态为 `done`、审查使用 Codex。Hermes 正式工具入口从两库读回已知文档，显式召回分别返回 52 和 57 条。默认 bank 读取被拒绝，两种未绑定对照均未暴露原生工具。 | 首次验证已注入记忆，模型回答称未召回；以新会话复测并检查发往模型的记录。手动留存只用本机替身验证路由，未写入共享 bank。本轮验证走 Windows 本机 Hermes CLI，Multica 派发待验。 |

## 回滚

保留改动前的私有配置或文件备份。OMP 的原文件备份位于 Hindsight 集成私有目录下的 `backups/omp-native-20261118T173102`，按文件恢复原 `config.yml`、既有 MCP 条目和项目映射。只撤掉本轮新增扩展，保留同时发生的其他设置变更。关闭旧会话后用新会话复核有效配置、当前 bank 和工具可用性。

DSH 备份位于集成私有目录下的 `backups/hindsight-20261118-171556`。按备份恢复 launcher 和 profile 的包清单、锁文件及 Cordis 配置，并移除本轮在 DSH 智能体增加的 `project-memory` 条目。必要时在恢复后的配置上使用 `dsh plugin --profile multica install --frozen-lockfile --ignore-scripts`，再用新进程核对插件版本。共享只读桥仍被其他客户端引用时继续保留。回滚目标为客户端接入，原记忆文档仍由共享服务与维护者管理。

Hermes 在 `$HERMES_HOME/config.yaml.pre-hindsight-20261118-174512.bak` 留存改动前版本。停止受影响的会话后，从备份只恢复 `memory.provider` 和 `mcp_servers.hindsight`，移除本轮新增的 `plugins/hindsight-multica` 与 `hindsight/config.json`。用新 Hermes 会话核对当前 provider 和工具列表；若本轮新增 Python 包已被其他扩展使用，保留依赖。
