# 单文件副本校验

`unblock.artifact.verify_copy(source_root, source_relative, target_root, target_relative, expected_bytes, expected_sha256)` 使用 Python 3.11 及以上版本的标准库，返回可序列化为 JSON 的字典。来源和目标根目录由调用方指定，均为已存在的绝对目录。调用时传入原件提供的预期字节数和 64 位十六进制 SHA-256。摘要接受大写输入，证据统一用小写。

相对路径接受 `/` 或 `\` 分隔符。目录链从文件系统根开始检查，遇到软链接、Windows 重解析点、非普通文件、同一文件或硬链接即拒绝。请传入实际目录路径，例如 macOS 上的 `/private/tmp/...`。Windows 支持本地盘符绝对路径，UNC 和设备命名空间留待核实。

校验器以只读句柄分块读取文件。两边读取完毕后再次打开路径，对比目录链与文件身份，并复核原句柄的大小、修改时间等稳定性信息。`match_existing` 表示在这次检查中看到了字节一致的既存副本。产物由谁创建、何时创建，以及业务授权、整批和原卡最终验收，仍由相应原件和指定验收人确认。结果覆盖观察窗口内的单个文件，文件系统的时间精度、挂载语义及窗口外的变化仍会影响判断。

| `status` | 含义 |
|---|---|
| `match_existing` | 来源与既存目标的字节数和 SHA-256 都符合预期。 |
| `not_copied` | 来源符合预期，目标相对路径在两次观察时均缺失。 |
| `size_mismatch` | 来源符合预期，目标字节数有差异。 |
| `digest_mismatch` | 来源符合预期，目标字节数相同但 SHA-256 有差异。 |
| `source_missing` | 来源根目录可核实，来源相对路径缺失。 |
| `source_mismatch` | 来源字节数或 SHA-256 有差异。 |
| `unsafe_path` | 路径、文件类型、链接或双方身份触发拒绝。 |
| `changed` | 两次观察之间的路径、文件身份或内容稳定性检查发现变化。 |
| `unknown` | 根目录缺失、访问失败、平台不支持所需检查或文件系统未提供身份信息。 |
| `invalid_input` | 预期字节数、摘要格式或根目录参数类型无效。 |

`evidence.source` 和 `evidence.target` 各包含已通过语法检查的 `relative_path`。两边路径观察稳定后，存在的文件还会附观察到的 `bytes` 和 `sha256`。检查中止时只保留已通过检查的相对路径。诊断可附 `subject`、固定 `reason` 和系统数字 `error_code`。绝对根目录、文件正文、文件系统身份值和原始异常不进入结果。附原卡前，调用方需核对相对路径是否适合披露。

合成夹具测试可从仓库根目录运行。

```sh
python3 -B -m unittest discover -s tests -p test_unblock_artifact.py
```

Windows 路径处理使用 `CreateFileW` 的重解析点标志打开各组件，然后检查句柄属性。在打开期间保留目录句柄，且文件句柄限制共享写入与删除。系统不能提供稳定性检查时，保留 `unknown`。 [Microsoft `CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) · [Python `os` 文档](https://docs.python.org/3.11/library/os.html)
