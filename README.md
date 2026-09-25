# OxideTerm：Mac ARM64 定制版

面向 Apple Silicon，包含活动会话右键菜单和独立字号设置。这是个人定制构建，不是上游官方发行版。

## 标准安装版：DMG

**[下载 OxideTerm-2.0.31-Mac-ARM64-Desktop.dmg](https://github.com/ciLLienfl99/xo/releases/download/v2.0.31-desktop-arm64.2/OxideTerm-2.0.31-Mac-ARM64-Desktop.dmg)**

打开 DMG，把 **OxideTerm Desktop.app** 拖到 **Applications**。不需要编译、不需要运行 `.command` 修复脚本。

**重要：此版本已修复整包签名结构，但只有完整 ad-hoc 本地签名，没有 Apple Developer ID 公证。Gatekeeper 测试仍为 rejected，不能把它称为免手动放行版。** 首次打开可能仍需要在 **系统设置 → 隐私与安全性 → 仍要打开** 中授权；仅在确认信任此定制版后使用。不要关闭全局 Gatekeeper。

[完整 Release：应用、源码、校验值和验证报告](https://github.com/ciLLienfl99/xo/releases/tag/v2.0.31-desktop-arm64.2) · [成功的 Actions 打包与发布记录](https://github.com/ciLLienfl99/xo/actions/runs/36182253048)

DMG SHA256：

```text
16174249abfa4e7a0acefff5e90a927a389e3302acabda0fe6bd41cfe77c3b05
```

### 这次实际验证了什么

完整 `.app` 的 `codesign --verify --deep --strict` 通过；安装副本进入欢迎界面；初始启动后签名仍通过，包内文件哈希未改变；DMG 完整性、只读挂载和内部应用一致性通过；发布附件与公开下载的 SHA256 一致。

`VERIFICATION.json` 分别记录签名完整性、初始启动和 Gatekeeper 结果。**没有 Apple 签名凭证时，只发布未公证预发布版，不伪报安全认证通过。** 尚未验证真实 SSH/SFTP 会话和旧数据迁移。

### 数据位置与旧版不同

标准安装版使用原程序的 `~/.oxideterm` 隐藏目录，或已有的自定义数据目录。它不再向签名后的 `.app` 写入用户数据，也不在应用旁边要求创建 portable 标记或 data 文件夹。替换安装版应用文件本身不会覆盖这些外部数据。

**旧的 `OxideTerm.app/Contents/UserData` 不会自动迁移。** 新应用名为 `OxideTerm Desktop.app`，避免同名覆盖旧包。保留旧应用和备份，不要把 UserData 手动放进新签名包。

只使用对应的定制安装包更新。未经定制的上游官方更新可能覆盖右键菜单和字号修改。

[标准安装及 Developer ID 公证配置说明](docs/DESKTOP-INSTALLATION.md)

## GitHub Actions 工作流

- **Package Mac ARM64 Desktop**：将固定的 Actions 编译产物恢复为标准安装布局，完整签名，验证启动、DMG，发布安装包。可手动选择 main 运行；修改对应工作流或打包脚本也会运行。
- **Build Mac ARM64 Bundle**：保留之前的完整 Rust 编译和旧便携包构建流程。旧便携包的成功不代表 Gatekeeper 通过。

标准安装版的主程序与辅助程序来自已成功的 [Mac ARM64 bundle · 3](https://github.com/ciLLienfl99/xo/actions/runs/36162224513)，二进制源提交为 `a9475f209049a920ae58b0771472e514a5c2e91c`。此次是对该定制编译产物重新封装和签名，不是换成未修改的官方二进制。

Apple 凭证分支支持 Developer ID 签名、notarytool 提交、stapler 装订和 Gatekeeper 检查；实际证书尚未提供，因此该分支尚未实测。凭证只能放在 GitHub Actions Secrets，不要发到聊天、issue 或代码中。

## 旧包内便携版：仅为已有用户保留

旧版数据写入 `OxideTerm.app/Contents/UserData`，其外层包不是完整签名发行包，下载后可能出现 damaged/已损坏。**不作为正常双击安装的推荐产物。** 已有用户不要因为报错删除含有数据的旧应用。

旧版不能在 Finder 直接整包替换或先删除再安装；需要先备份，再使用兼容的包内升级器保留 UserData。首次打开工具只是显式的单应用本机放行手段，不是签名修复或公证；不适用于新 Desktop 安装版。

[旧版完整使用、升级与放行说明（历史快照）](https://github.com/ciLLienfl99/xo/blob/6c7fce9a0f68ae4533b77e649be8915be7ea0602/README.md)

## 源码与许可

上游固定为 [AnalyseDeCircuit/oxideterm](https://github.com/AnalyseDeCircuit/oxideterm) 的提交 `4d5933c9914ab5c5efc4ff4124bdf255f6ba619d`，对应上传源码 2.0.31，不随意获取最新 main。

完整对应源码为 Release 中的 `OxideTerm-2.0.31-custom-source.tar.gz`；新安装包的重新封装源码另附 `Desktop-Packaging-Source.tar.gz`。GitHub 自动生成的 `Source code (zip)` 仅是本仓库配置快照，不替代完整对应源码。

上游版权、GPL-3.0-only 许可证与第三方声明保留在源码和应用资源中。仓库和 Release 不存储用户的连接资料、密码、私钥或 UserData。
