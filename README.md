# OxideTerm：Mac ARM64 包内便携定制版

面向 Apple Silicon，编译目标 `aarch64-apple-darwin`。这是个人定制构建，不是上游官方发行版。

## 直接下载应用

**[下载 OxideTerm-2.0.31-Mac-ARM64-Bundle.zip](https://github.com/ciLLienfl99/xo/releases/download/v2.0.31-custom-arm64-build.3/OxideTerm-2.0.31-Mac-ARM64-Bundle.zip)**

解压后就是单个 `OxideTerm.app`，不需要编译源码。

[GitHub 最新发布页](https://github.com/ciLLienfl99/xo/releases/latest)提供应用、完整对应源码、中文使用与升级说明、SHA256 校验值和构建来源记录。完整对应源码是 `OxideTerm-2.0.31-custom-source.tar.gz`，包含上游许可证和第三方说明；GitHub 自动生成的 `Source code (zip)` 只是本仓库构建配置，不代替完整对应源码。

当前发布版本为 `v2.0.31-custom-arm64-build.3`，使用修复后的代码 `a9475f209049a920ae58b0771472e514a5c2e91c`。应用 ZIP 的 SHA256：

```text
c9cd86b2d04a83638b30685cf373e34af6b0140123839d37483fdda9c333360c
```

## 已完成的 GitHub Actions 记录

| 阶段 | 已通过的任务 |
|---|---|
| Mac ARM64 完整编译、原生测试、打包与校验 | [Mac ARM64 bundle · 3](https://github.com/ciLLienfl99/xo/actions/runs/36162224513) |
| 独立 Mac 初始启动及包内数据目录检查 | [Check Mac ARM64 Startup](https://github.com/ciLLienfl99/xo/actions/runs/36167841824) |
| 构建来源、产物哈希复核及 Releases 发布 | [Publish verified Mac ARM64 · 2](https://github.com/ciLLienfl99/xo/actions/runs/36178399464) |

此应用由 GitHub Actions 编译。发布工作流直接使用经过验证的 Actions 原始产物，不重新上传本地编译文件；发布前核对构建输入、包结构、启动报告及全部附件的 SHA256。

旧的失败记录仍保留在 Actions 历史中。不要重跑旧的失败任务来获取修复版；需要重新完整编译时，打开 [Build Mac ARM64 Bundle](https://github.com/ciLLienfl99/xo/actions/workflows/mac-arm64.yml)，选择 **Run workflow → main**。

构建配置或 `build/` 中的定制内容推送至 `main` 后，完整编译流程自动运行。后续流程为 **完整构建 → 独立启动检查 → 验证并发布 Releases**；失败的构建或不匹配的启动结果不会发布。Actions 中仍保留原始应用和对应源码产物，保留期 30 天；Releases 提供独立下载入口。

## 定制内容

- 活动会话操作收进右键菜单，根据连接状态显示连接、SFTP、终端等操作。
- 设置 → 外观 → 布局：独立调整活动会话字号，默认 14 像素，范围 10–24。
- 便携运行数据自动保存在 `OxideTerm.app/Contents/UserData`，无需在应用旁边建立 portable 标记或 data 文件夹。

## 首次使用与升级

把整个应用移动到自己有写入权限的位置，再打开。第一次使用设置主密码，之后以主密码解锁包内加密密钥库。旧版本的数据不会被自动迁移或删除；先备份，再通过原有迁移功能导入并核对。

**不能通过 Finder 整包“替换”，也不能先删除含数据的旧应用。** 包内数据会跟随旧应用一起被移走或删除。升级必须使用兼容的定制更新器，或新包内的本地升级脚本：

```bash
python3 "/新版本目录/OxideTerm.app/Contents/Resources/install_macos_bundle.py" \
  --target "/原使用目录/OxideTerm.app"
```

先退出旧应用，把新版本解压在另一个位置，再执行以上命令。脚本仅替换程序条目，不替换 UserData。后续版本仍须包含本仓库定制修改；未修改的官方安装包不能代替此包内便携版本。

这个自用包仅对内部程序做签名校验，外层可写应用未做公证。初始启动检查已通过，但不等于交互式主密码解锁、SSH/SFTP、Gatekeeper 或真实用户数据升级已经验证。首次使用及升级前应保留数据备份。

## 可复现来源

源代码固定为 [AnalyseDeCircuit/oxideterm](https://github.com/AnalyseDeCircuit/oxideterm) 的提交 `4d5933c9914ab5c5efc4ff4124bdf255f6ba619d`，即上传源码包对应版本 2.0.31。不是构建时随意抓取最新 main。

构建流程校验并应用定制补丁，运行打包回归、语言包检查和原生便携/更新器测试，编译主程序及辅助程序，再检查最终应用架构、签名和不包含用户数据的单 .app 布局。完整编译日志保存在每次 Actions 运行中。

上游版权、GPL-3.0-only 许可证及第三方声明保留在对应源码和应用资源中。代码区保存源码补丁和构建配置，Releases 保存编译产物、完整对应源码及说明；不保存连接资料、密码、令牌、私钥或 UserData。
