# cloud-work 内部 PowerShell 签名

所有属于 `cloud-work` 的现有及新建项目可在自己的 Multica 原 Issue 提交签名请求。腾讯签发端每次查原生项目和 Issue 的归属，无须登记项目白名单。当前交付的格式是 win-work 上 Windows PowerShell 5.1 使用的 `.ps1`，最大 1 MiB，支持 ASCII、带 BOM 的 UTF-8 或 UTF-16LE。

## 办一笔签发

1. 申请人在项目原卡写明候选文件名、已审源文件的 SHA-256、来源引用、用途和验收人。示例可见 [workspace-signing Skill](../../skills/workspace-signing/SKILL.md)。审批针对这份确切内容。
2. 发布操作者从获准来源独立获取已审原件。在可 SSH 访问 win-work 和腾讯签发端的受信操作机上，使用本仓的 `approve_release.py`。准备好已存在的签后输出目录，指定独立输出路径。在操作者自己的进程环境中加载可读目标原卡的 `MULTICA_TOKEN`，避免在命令参数、工单或日志中传令牌。

   ```sh
   python3 -E -s -B deployment/workspace-signing/approve_release.py \
     --project "$PROJECT_UUID" --issue "$ISSUE_UUID" \
     --reviewed-file "$REVIEWED_LOCAL_COPY" --approved-sha256 "$APPROVED_SHA256" \
     --win-host "$WIN_SSH_TARGET" --sign-host tencent \
     --source "$WINDOWS_UNSIGNED_FILE" --output "$WINDOWS_SIGNED_FILE"
   ```

3. 操作机独立对已审字节和 Windows 提取的 PowerShell 签名摘要进行比对。腾讯只接收项目、Issue、摘要及固定格式的签名数据，向本机 Multica 核对归属后签发。API 读令牌随这一笔 SSH 连接传入，不入签发账本。高权限 Windows Agent 不能凭一份自报摘要取得腾讯签名；腾讯运维权限和操作机的 SSH 身份应只交发布操作者保管。
4. 签名回到 win-work 后，客户端检查签名块之前的字节与原文件逐字节一致，并要求系统 `Get-AuthenticodeSignature` 返回 `Valid`、内嵌 Authenticode 类型及对应发布者证书摘要。通过后才交付独立文件。把原始 SHA-256、签后 SHA-256、发布者指纹和签名副本位置记回原卡。程序不启动该脚本。脚本自检、部署和执行许可按签后版本核对。

相同项目、Issue、原文摘要及签名数据重放时，签发端返回账本中同一签名。已有同字节输出可安全核收，异内容输出保留。签发成功但附件或客户端验签失败，先用原请求重试。源码变动需重新审阅。审批者的受信原件、操作机和腾讯 SSH 发布权限共同构成签发边界。Windows 的发布者信任按账户生效，所有由该证书签发的代码都可能被该账户信任；项目隔离发生在签发前。

## 部署和信任

| 位置 | 安装与作用 |
|---|---|
| 腾讯 VPS | `/usr/local/lib/multica-workspace-signing/sign_release.py` 由 root 调用，经回环只读 Multica。签发私钥、证书及 SQLite 账本在 root 专有的 `/var/lib/multica-workspace-signing`。复用现有管理 SSH，不单设公网监听或常驻签名服务。 |
| win-work | `C:\Program Files\Multica Workspace Signing` 存放客户端 `workspace_sign.py`、公钥证书 `publisher.cer`、配置 `client.json` 和 `bin\osslsigncode.exe`。配置的 `python` 是本机已有 Python 3 的绝对路径。程序安装目录应由管理员维护。 |
| 操作机 | 在完整签名工具目录中运行 `approve_release.py`。它复用同目录的摘要、签名块与数据校验代码，并独立复算交付摘要。源码复核副本须在项目已授权的审阅范围内。 |

经授权的其他发布操作者可通过既有 SSH 从腾讯 `/usr/local/lib/multica-workspace-signing/` 取回这套工具和说明。该目录只存程序和文档。工作区 Skill 目录中的申请入口为 `workspace-signing`（ID `444d677a-01ce-4417-b0dc-395414697d38`）。

干净安装时，在两端从官方发行版选支持 PowerShell 分离签名的 osslsigncode 并核对发行资产 SHA-256。部署验收用 2.16，Linux amd64 压缩包为 `109c711ac07fc2ce1e3756d6247d92bbf23e55c4aa809a4b34cca3c4f2913fc6`，Windows amd64 为 `125903750deb7b633c57a81fe3c6ae945a271c30e382b9413a2af4e4d6248ee3`。将腾讯二进制装为 root 拥有的普通文件 `/usr/local/bin/osslsigncode`。需要升级时复验摘要提取、附签、篡改拒绝和 Windows 原生验证。[官方发行版](https://github.com/mtrojnar/osslsigncode/releases/tag/2.16) · [PowerShell 签名说明](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_signing?view=powershell-5.1)

腾讯首次安装时以 root 运行 [init-signer.sh](init-signer.sh)，只向运行主机分发 `publisher.cer`。私钥为 RSA 3072、文件权限 0600；自签证书只含代码签名用途、`CA:FALSE`，有效期一年。确认 Windows 当前用户 SID 与目标运行账号一致，核对证书 SHA-256 后，在该账号的 Windows 桌面执行：

```powershell
$cert = 'C:\Program Files\Multica Workspace Signing\publisher.cer'
Get-FileHash -Algorithm SHA256 -LiteralPath $cert
certutil.exe -user -addstore TrustedPublisher $cert
certutil.exe -user -addstore Root $cert
```

工作区此次发布者公钥证书 SHA-256 为 `90a24030b21daf858682570380f04964aa9f9b684156cbfb33bd64a98e41336c`，Windows 指纹为 `638A0F7007E1116C158996E6FE06CB9190CF6D55`，有效期至 2027-11-23 09:00 UTC。Windows 可能要求交互确认当前用户根信任，SSH Session 0 返回 `0x80070032` 时改由该账号的已登录桌面完成同一导入。回读 CurrentUser 的 Root、TrustedPublisher 及 LocalMachine 对应位置，确认授权范围。各项目继续使用原执行策略。

## 维护与回退

- 首次签发时间、项目、Issue、原始摘要、签名数据摘要、证书摘要、签名字节及 API 操作者 ID 存入 `releases.sqlite3`。这份回执证明签发，业务部署及运行看原任务。签发端停用时先收回调用入口，保留受控备份及账本以便对账。
- 本期使用内部证书，签名未加受信时间戳。证书到期前安排轮换。新密钥、新指纹和新账本应作为独立一代受控部署并重新登记账号信任，避免老账本重放旧签名。已签文件保留原件与摘要，是否重新签发由发布操作者决定。
- 撤销此账号的工作区信任时，核对上述精确指纹，再对 `TrustedPublisher` 和 `Root` 分别执行 `certutil.exe -user -delstore <store> <已核实指纹>` 并读回。这会影响该发布者以前签过的文件。不要删除其他发布者或修改整机信任。
- 复验用两个不同项目各一张隔离卡及正文仅输出验证标识的样本。逐项验证正常加载、错配项目被拒、错误源摘要被拒、签后修改被 Windows 判为 `HashMismatch`、原申请重放产生同一签名。只有此类无业务副作用的隔离样本用于加载测试。

## 2026-11-23 现场回执

| 所属项目 | 验收范围 |
|---|---|
| Multica 运行时验证 | 在原生 Windows PowerShell 5.1 的 `RemoteSigned` 策略下加载合成样本并输出约定标识。改动一个字节后验签为 `HashMismatch`。重放前后签后摘要和原签发时间均一致。[CLOU-60](http://10.207.56.3:3000/cloud-work/issues/01a2079e-8dc8-7103-b959-eacb92e6e04b#comment-01a207b2-64b0-71d2-89a9-d97518095cd2) |
| fanren-work | 另一项目的合成样本通过同一条签发和原生加载路径。错配项目与原卡在腾讯被拒，错误原文摘要在操作端被拒。[CLOU-61](http://10.207.56.3:3000/cloud-work/issues/01a2079e-9018-706d-914a-87b8daa38db9#comment-01a207b2-6898-72a0-b91d-97e4e4630729) |

公子另行批准签发的 r4.1 已作为独立副本通过原生 Authenticode 验签。原启动路径的未签文件摘要保持原值；未运行 Huihui 或替代生产现场验收。[CLOU-40 签名回执](http://10.207.56.3:3000/cloud-work/issues/01a1f9b0-ab24-7cf1-b748-8b5dc2c4e966#comment-01a207b2-6dcc-78ac-b4ee-bb58c2cba17e)
