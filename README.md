# OxideTerm：Mac ARM64 包内便携定制版

面向 Apple Silicon，编译目标 `aarch64-apple-darwin`。这是个人定制构建，不是上游官方发行版。

## 下载

进入 [Actions → Build Mac ARM64 Bundle](https://github.com/ciLLienfl99/xo/actions/workflows/mac-arm64.yml)，打开一次**成功**的构建记录，在页面下方 Artifacts 中下载 **OxideTerm-Mac-ARM64-Bundle**。

产物里面的 `OxideTerm-2.0.31-Mac-ARM64-Bundle.zip` 才是应用压缩包；解压后得到 `OxideTerm.app`。同一产物还附带 SHA256 校验值和使用、升级说明。构建运行中或失败时不代表已经有可用应用。

完整对应源码单独保存为 **OxideTerm-Corresponding-Source**，包括上游许可证和第三方说明。请下载保存，Actions 产物保留期为 30 天。

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

这个自用包仅对内部程序做签名校验，外层可写应用未做公证。构建与自动化测试不等于交互式启动、SSH/SFTP 或真实用户数据升级已经验证。首次使用及升级前应保留数据备份。

## 可复现来源

源代码固定为 [AnalyseDeCircuit/oxideterm](https://github.com/AnalyseDeCircuit/oxideterm) 的提交 `4d5933c9914ab5c5efc4ff4124bdf255f6ba619d`，即上传源码包对应版本 2.0.31。不是构建时随意抓取最新 main。

构建流程校验并应用定制补丁，运行打包回归、语言包检查和原生便携/更新器测试，编译主程序及辅助程序，再检查最终应用架构、签名和不包含用户数据的单 .app 布局。完整编译日志保存在每次 Actions 运行中。

上游版权、GPL-3.0-only 许可证及第三方声明保留在对应源码和应用资源中。本公开仓库只保存源码补丁和构建配置，不保存连接资料、密码、令牌、私钥或 UserData。
