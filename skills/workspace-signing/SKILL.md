---
name: workspace-signing
description: 在 cloud-work 原 Issue 申请 Windows PowerShell 脚本签名，并核对签发回执。
metadata:
  version: "1.0.0"
---

# 工作区脚本签名

cloud-work 现有及新建项目共用此入口。首批格式为 Windows PowerShell 5.1 的 `.ps1`。签名请求沿所属项目原 Issue 办理，业务执行、发布与验收沿该任务原授权。

1. 固定未经签名的候选版本。在原卡用静默备注写明项目和 Issue 的 UUID、文件名、获准的源文件或提交引用、原始文件 SHA-256、审阅人、签发用途。源码与凭据留在项目批准的位置。
2. 交给持有腾讯签发端操作权限的发布操作者。操作者从获准来源独立取得已审稿，核对摘要后调用 `deployment/workspace-signing/approve_release.py`。签发端核对原卡所属项目和工作区，仅处理本次批准的签名数据。项目 Agent 可申请和验签，签发私钥由腾讯端保管。
3. 在 win-work 的独立输出位置取得签名副本。核对 `Get-AuthenticodeSignature` 返回 `Valid`、发布者证书指纹、签名前后两个文件摘要，再在原卡回执。Windows 加入签名块后文件摘要会变化。脚本或启动器若绑定原始版本、文件名、目录或摘要，实际使用时须核签后准确文件及对应授权。
4. 同卡、同一原始文件摘要再次办理时沿原签发记录对账。内容改动先重新审阅。签名本身只证明发布者签认这些字节；能否实际运行、操作生产或发布，由原任务的授权人决定。
