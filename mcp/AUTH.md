# Multica Backend MCP 启动与 OAuth 接线

在独立环境中安装 `mcp/`，使用 Python 3.11 或更新版本。生产由该项目依赖中的 Uvicorn 运行单进程。服务启动时同时校验 OAuth 和 [Gateway](multica_backend/gateway.py) 配置。

```sh
python -m pip install ./mcp
python -m multica_backend.server
```

| 环境键 | 值 |
| --- | --- |
| `MULTICA_MCP_PUBLIC_BASE_URL` | HTTPS 外部基址，例如 `https://example.invalid/multica-backend`。同时为 OAuth issuer |
| `MULTICA_MCP_GITHUB_CLIENT_ID`、`MULTICA_MCP_GITHUB_CLIENT_SECRET` | 获准用于本服务的 GitHub OAuth App 客户端凭据。登记精确回调 `${MULTICA_MCP_PUBLIC_BASE_URL}/auth/callback` |
| `MULTICA_MCP_OAUTH_SIGNING_KEY` | 服务专用的独立随机签名材料，建议用 `secrets.token_urlsafe(32)` 生成并经秘密管理入口配置。轮换会使原 MCP 登录失效 |
| `MULTICA_MCP_OAUTH_STATE_DIR` | 单进程使用的绝对私有路径，目录权限 `0700`，保存加密的 OAuth 注册、会话与令牌状态。配额为 8 MiB、512 个文件，达到上限后拒绝新写入 |
| `MULTICA_MCP_GITHUB_PRINCIPALS` | JSON 对象，以 GitHub 数字用户 ID 为键。示例 `{"12345":{"scopes":["read","write"]}}`，Gateway 收到 `github:12345`。填入获准的实际数字 ID |
| `MULTICA_MCP_ALLOWED_REDIRECT_URIS` | JSON 数组，登记实际客户端的完整允许回调。HTTPS 或带显式端口的 HTTP loopback 可用。OAuth 填允许的实际 Dot 回调，GitHub App 回调填上表所列的服务回调 |
| `MULTICA_MCP_PORT` | 本地监听端口，默认 `8770`。模块只监听 `127.0.0.1` |

App 所有者可在获准共享的现有 GitHub OAuth App 下追加该回调并保留原回调，也可为 Multica 单独创建 App。GitHub 当前允许每个 OAuth App 登记最多 10 个回调。两种方式均使用独立的 MCP issuer 与资源地址、签名密钥、OAuth 状态目录和本地读写授权。向 GitHub 请求的身份作用域为 `read:user`。Dot 首次连接本 MCP 时走原生 OAuth 流程，按客户端提示完成登录和授权。[GitHub OAuth App 文档](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app) · [部署分工](../deployment/multica-backend/README.md)

## 代理路由

| 对外入口 | 转发 |
| --- | --- |
| `/multica-backend/mcp` | 本地 `/mcp` |
| `/multica-backend/{register,authorize,consent,token,revoke,auth/callback}` | 剥除 `/multica-backend` 前缀。GitHub 回调和 OAuth 浏览器跳转使用 HTTPS 公共地址 |
| `/.well-known/oauth-authorization-server/multica-backend` | 原路径透传 |
| `/.well-known/oauth-protected-resource/multica-backend/mcp` | 原路径透传 |
| 本地 `GET /health` | 进程活性，返回 `{"status":"ok"}` |

代理保留外部域名的 Host，OAuth 和 MCP 路由保留请求头、查询和 Cookie。应用关闭 HTTP access log，代理日志同样应排除 OAuth 回调查询和凭据。生产只接受为该 MCP 资源签发的 Bearer token，由 GitHub 验证后的用户 ID 和本地策略确定可见、可调用的工具。HTTP 未认证为 `401`，主体未获准为 `403`。已登录的读主体直接调用写工具时，返回 MCP 工具错误 `forbidden_scope`。上游认证失败按 Gateway 结果返回在 MCP 工具响应内。
