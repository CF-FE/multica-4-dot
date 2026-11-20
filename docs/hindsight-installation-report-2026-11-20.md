# Multica 两台工作机的 Hindsight 安装与验收报告

2026-11-18 至 11-20（北京时间），win-work 的 OMP、DSH、Hermes、Kimi，以及 mac-work 的 Kimi，均已在真实 Multica 任务中验证了**首轮自动召回**和**读取获准的其他项目 bank**。Hermes 和两端 Kimi 均有当前项目脱敏经验的实际写入及原 ID 读回回执。OMP 和 DSH 的验收只做了读取。公子已决定暂缓 mac-work Kimi 的后续处理。[项目总卡 CLOU-11](http://10.207.56.3:3000/cloud-work/issues/CLOU-11)

## 五个运行端的实测结果

本次验收的当前项目 bank 为 `multica-4-dot`，获准跨读的 bank 为 `cf-fe-herdr-4-codexcloud`。表中分别列出新会话自动载入的记忆和随后主动查询的结果。召回条数只描述当次查询。

| 运行端与验收日期 | 安装及生效入口 | 首轮自动召回 | 双库读取与按需留存 |
|---|---|---|---|
| win-work · OMP v18.22.2 · 11-18 | 内置 Hindsight 后端按项目绑定。跨库查询走 Windows 共享只读桥。 | 首个工具结果前已载入 3,345 字符。随后原生 `xd://recall` 返回 11 条。 | 两库均按 ID 读回指定文档，跨库显式召回 5 条。已配置本库手动留存，真实写入未验。[CLOU-10](http://10.207.56.3:3000/cloud-work/issues/CLOU-10) |
| win-work · DSH 0.2.2-rc.3 · 11-18 | 在 `multica` profile 固定官方插件 `@vectorize-io/hindsight-coding-agents@0.8.7`，保留凭据加载兼容补丁。跨库共用只读桥。 | 启动日志记录 `inject_recall count=13`、`inject_ok`。 | 两库指定文档均读回，独立复核分别含 27、6 个记忆单元。已配置本库手动留存，真实写入未验。[CLOU-8](http://10.207.56.3:3000/cloud-work/issues/CLOU-8) |
| win-work · Hermes 0.23.2 · 11-20 | 受管 Python 环境加载 Hindsight 插件 1.2.4、客户端 1.2.3。修复后，ACP 从实际任务目录识别项目，Hermes 使用专用只读入口。 | 模型收到的首条用户消息含 21 条记忆，早于首个业务工具。 | 两库指定文档均命中，显式召回各 7 条。本库留存操作完成，按原 ID 复核正文摘要一致。验收卡已完成。[CLOU-16](http://10.207.56.3:3000/cloud-work/issues/CLOU-16) |
| win-work · Kimi 2.6.3 · 11-20 | `UserPromptSubmit` hook 负责自动召回。`kimi-project-memory` Skill 从任务目录调用已配置的受限 stdio 代理。 | 新会话首轮注入 3 条，和宿主回执一致。 | 经 Skill 读回两库指定文档，显式召回各 10 条。本库留存操作完成，按原 ID 读回。真实会话首轮原生 MCP 工具未出现。[CLOU-18](http://10.207.56.3:3000/cloud-work/issues/CLOU-18) |
| mac-work · Kimi 2.6.3 · 11-20 | 首轮走 `UserPromptSubmit`。显式查询由同一 Skill 通过 Mac 上的项目受限 stdio 代理发起。 | 14:06–14:11 的独立新会话在首个业务工具前注入 2 条。 | 经 Skill 读回两库指定文档，显式召回分别为 47、54 条。本库脱敏经验已在上午写入，下午按原 ID 读回。首轮原生 MCP 直调未通过，后续处理已暂缓。[CLOU-17](http://10.207.56.3:3000/cloud-work/issues/CLOU-17) |

## 权限与验收边界

- **项目路由。** Multica 会话依据 Daemon 托管标记、workspace 和项目 ID 确认当前 bank。五个入口均关闭整段会话自动留存。Hermes 和两端 Kimi 的未绑定场景验证了禁用自动召回及写入，跨库写探针在本地被拒。真实写入仅针对本项目的脱敏经验。[Hermes 实施卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-12) · [Windows Kimi 实施卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-14) · [Mac Kimi 实施卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-13)
- **Kimi 的两条调用路径。** 两端在真实 Multica 首轮均能靠 hook 取得项目记忆。模型工具表缺少 `mcp__hindsight__*` 时，已验证的显式读取入口是 `kimi-project-memory`。Windows 验收时从 Multica 取回同版 Skill 脚本，从原任务目录启动，以保留项目绑定。[Windows 验收卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-18) · [Mac 验收卡](http://10.207.56.3:3000/cloud-work/issues/CLOU-17)
- **两次容易误判的结果。** 11-18 的 Hermes 回执来自本机 CLI，11-20 的 CLOU-16 才证实 Multica 派发的真实 ACP 路径。Mac Kimi 在 13:00 唤醒时复用了上午的会话，去重机制跳过自动注入。14:06 使用 `--fresh` 后，会话 ID、去重标记和首轮回执均为新值。首次召回也可能漏掉具体案例细节，精确结论应核对原文档。[历史接入与验收](win-work-hindsight.md#验收) · [CLOU-17](http://10.207.56.3:3000/cloud-work/issues/CLOU-17)

## 原始回执索引

| 验收卡 | 关键 Multica Run | 当前项目已读回的留存文档 ID |
|---|---|---|
| CLOU-10 · OMP | `01a1ee00-4f54-7b9c-9633-336c98f7628b` | 本轮未写 |
| CLOU-8 · DSH | `01a1edf4-a769-7e88-b038-c11912e2dba8` | 本轮未写 |
| CLOU-16 · Hermes | `01a1f6e9-96be-735c-b31a-fdf0255eec92` | `multica-hindsight-verified-20261120-hm` |
| CLOU-18 · win-work Kimi | `01a1f711-af0a-70b4-af79-9328dc069799` | `multica-hindsight-verified-20261120-wk` |
| CLOU-17 · mac-work Kimi | `01a1f78f-d850-7b9f-b4ed-6f9da7d5bdc0` | `multica-hindsight-verified-20261120-mk` |
