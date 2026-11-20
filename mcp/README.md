# Multica Backend MCP 服务端

`multica_backend/` 存放服务端 Python 代码。云端 Dot 的插件素材在 [plugin/](../plugin/)，工作区协调员使用的 CLI/REST 指南在 [multica-backend Skill](../skills/multica-backend/SKILL.md)。服务架构与进度见[决策索引](../docs/backend-integration.md)及[交付表](../docs/multica-backend-tasks.md)。

| 模块 | 用途 |
|---|---|
| [multica_api.py](multica_backend/multica_api.py) | 绑定服务端配置的实例、调用身份与目标范围，核对原生项目、Issue 和指定 Run 的读取契约 |
| [delivery.py](multica_backend/delivery.py) | 在 SQLite 中认领稳定请求，按原生关联判断派发结果及恢复方式 |

在仓库根目录运行以下命令。第一条验证服务端模块，第二条覆盖已有补报器、读取服务及上游发行检查。

```sh
PYTHONPATH=mcp python3 -B -m unittest discover -s mcp/tests -q
python3 -B -m unittest discover -s tests -q
```

版本更新时可运行 [发行检查](../scripts/check_multica_release.py)，再按[只读契约检查器](../scripts/check_multica_contract.py)的 `--help` 对明确的隔离环境取证。隔离测试使用合成凭据。单独运行这两个模块只会得到组件级证据；云端 OAuth、MCP 工具发现、写操作与回程的验证位置见交付表。
