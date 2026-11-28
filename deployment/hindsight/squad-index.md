# 从业务原卡维护小队索引

win-work 的开发和质量队长可以从有项目归属的 Multica 原 Run 更新中央索引。每次调用通过 Daemon 注入的 Multica CLI 读回线上任命、原卡和活动 Run。正常入口只接受下列固定映射，由服务端原卡备注证明是哪位 Agent、哪笔 Run 提交了这次增量。

| 参数 | 小队 | Git 仓库中的文件 | multica-4-dot 原文档 |
|---|---|---|---|
| `dev` | 开发团队 | `docs/development-reuse.md` | `dev-squad-cross-project-engineering-reuse` |
| `qa` | 质量团队 | `docs/quality-review-methods.md` | `quality-squad-review-methods` |

1. 在原业务卡上核对实际采用的新增经验。用独立 checkout 更新本队索引，查看单文件差异，以本 Run 的 Git 身份正常快进推送至 `CF-FE/multica-4-dot` 的 main。若远端前移，读取变化并整合后再推。保存实际提交的完整 SHA。
2. 在同一 Run 的 PowerShell 终端按下例读回原文与正文摘要，确认是否已有这条经验。已有覆盖就引用原 ID。脚本由操作者部署在 win-work 的 `~/.multica/integrations/hindsight/`，使用 Hindsight 现有 Python 运行环境。

   ```powershell
   $py = 'D:/Hindsight/app/.venv/Scripts/python.exe'
   $entry = "$env:USERPROFILE/.multica/integrations/hindsight/squad_index.py"
   & $py -I -B $entry dev <原卡UUID>
   ```

3. 确有增量时，在原线程用本 Run 身份回复如下静默备注。替换队别、摘要、提交号和新增正文。备注只放可留存的脱敏经验；一条备注对应一次确定的更新意图。

   ```text
   /note

   squad-index-update/v1 dev
   {"base_sha256":"写前正文SHA-256","commit":"远端已包含的40位提交号","addition":"实际采用的方法、适用边界与原卡证据"}
   ```

4. 在上述命令末尾加 `--note <该备注UUID>`。入口按原卡与本 Run 核实作者、当前任命和适用的既有文档，仅追加正文并保留既有标签、上下文及来源元数据。成功回执含原 ID、operation_id 和新摘要，再以读命令核原文和本次增量。Git 推送采用共享 Windows Git 凭据；原卡作者、Run、提交和Hindsight 操作号共同标明实际执行者。

提交响应未知时，沿同一备注查服务端原操作号。入口用 Hindsight 原生 append 及固定操作号保存增量；下次调用先查原操作，已完成就读回正文。后续 Run 可接续同一位现任队长在同一原卡的原备注。调用结果未知或原文、元数据摘要不一致时保留原操作对账。此入口无需在沙箱外写本地账本。


维护源码见 [squad_index.py](squad_index.py)，隔离回归见 [test_squad_index.py](../../tests/test_squad_index.py)。这项限制由正常工具入口执行；共享 Windows 管理员账号的宿主权限沿工作区既有决定。
