# Mac ARM64 标准安装版

这是独立的 `OxideTerm Desktop.app` 安装版，不是旧的可写 `.app` 便携包。打开成功构建的 `OxideTerm-2.0.31-Mac-ARM64-Desktop.dmg` 后，将应用拖到 Applications。

不需要运行 `OxideTerm-First-Launch.command`、删除隔离属性或关闭全局 Gatekeeper。旧 `OxideTerm.app` 保留不动，不会被同名覆盖。

## 数据与功能

- 保留已编译的活动会话右键菜单和独立字号修改。
- 数据使用上游安装模式的 `~/.oxideterm` 隐藏目录，或之前在设置里选定的自定义数据目录；不再写入签名后的 `.app`。
- 替换安装版应用文件本身不会覆盖上述数据。仍应保留数据备份。
- **旧便携版 `Contents/UserData` 不会自动迁移。不要删除旧应用或把 UserData 手动塞进新签名包。**
- 不要用未经定制的上游官方更新替换本定制版，否则界面修改可能丢失。

## 签名状态必须看验证报告

Actions 会执行完整应用的 `codesign --verify --deep --strict`，验证实际启动后签名仍有效、应用内容未改变，以及 DMG 的完整性、只读挂载及内部应用一致性。

**这些检查不等于 Apple 公证或 Gatekeeper 接受。** 报告 `VERIFICATION.json` 分别记录 `whole_bundle_signature`、`initial_startup`、`notarized` 和 `gatekeeper_accepted`。

没有 Apple 凭证时，产物只有完整 ad-hoc 本地签名，并以未公证预发布版发布。首次启动可能仍需在 **系统设置 → 隐私与安全性 → 仍要打开** 中明确授权。仅在确认信任此版本后使用。此产物不能称为“免手动放行发行版”。

## 要生成 Developer ID 公证版本

`Package Mac ARM64 Desktop` 工作流支持以下 Repository Actions Secrets。只能在 GitHub 的 Secrets 管理页面配置，不要提交到仓库、issue、日志或聊天：

| Secret 名称 | 内容 |
|---|---|
| `MACOS_CERTIFICATE_P12_BASE64` | Developer ID Application 证书与私钥的 P12 导出文件，Base64 编码 |
| `MACOS_CERTIFICATE_PASSWORD` | P12 导出密码 |
| `MACOS_SIGNING_IDENTITY` | `Developer ID Application: ...` 完整证书标识 |
| `APPLE_API_KEY_BASE64` | 具有相应公证权限的 App Store Connect API P8 私钥，Base64 编码 |
| `APPLE_API_KEY_ID` | 上述 API key 的 Key ID |
| `APPLE_API_ISSUER_ID` | 对应 Issuer ID |

全部提供后，流程尝试 Developer ID 签名、公证、票据装订和 Gatekeeper 检查；任何一步失败都不发布。缺少部分凭证时会停止，不会悄悄降级为未公证版。这条 Apple 凭证分支尚未用实际证书执行验证。

当前安装包的主程序来自固定的 GitHub Actions 构建 `36162224513`，源提交 `a9475f209049a920ae58b0771472e514a5c2e91c`。完整对应源码与本次重新封装脚本源码一同附在 Release 中。软件交互、SSH/SFTP 联调和旧数据迁移不属于初始启动检查。
