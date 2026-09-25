#!/bin/bash
# Local-use recovery for exactly ciLLienfl99/xo ARM64 build 3.
# No global policy changes, re-signing, program replacement, or UserData access.
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
EXPECTED=c9cd86b2d04a83638b30685cf373e34af6b0140123839d37483fdda9c333360c
URL=https://github.com/ciLLienfl99/xo/releases/download/v2.0.31-custom-arm64-build.3/OxideTerm-2.0.31-Mac-ARM64-Bundle.zip
MODE=check
APP=
ARCHIVE=
fail() { printf '\n停止：%s\n' "$*" >&2; exit 1; }
while [ "$#" -gt 0 ]; do
    case "$1" in
        --allow-local-use) MODE=allow; shift ;;
        --check) MODE=check; shift ;;
        --app) [ "$#" -ge 2 ] || fail '--app 缺少路径'; APP=$2; shift 2 ;;
        --archive) [ "$#" -ge 2 ] || fail '--archive 缺少路径'; ARCHIVE=$2; shift 2 ;;
        *) fail "未知参数：$1" ;;
    esac
done
[ "$(uname -s)" = Darwin ] || fail '仅适用于 macOS。'
[ "$(id -u)" -ne 0 ] || fail '请使用普通账户运行，不要使用 sudo。'
printf '%s\n' '这是未公证的个人定制版，不是 Apple 已批准的应用。' \
    '本工具先校验固定版本的发布 ZIP，并逐项比对所选应用的程序文件。' \
    '只有 --allow-local-use 才移除所选应用程序条目的下载隔离标记。' \
    '不会读取或更改 UserData，不会修改系统 Gatekeeper 设置或重新签名。'
if [ -z "$APP" ]; then
    APP=$(/usr/bin/osascript -e 'POSIX path of (choose file of type {"com.apple.application-bundle"} with prompt "选择提示损坏的 OxideTerm.app（不要选择 ZIP 文件）")') || fail '没有选择应用；未修改应用。'
fi
APP=${APP%/}
[ -d "$APP" ] && [ ! -L "$APP" ] || fail '目标必须是实际的 .app 目录，不支持符号链接。'
APP=$(cd "$APP" && pwd -P)
case "$APP" in *.app) ;; *) fail '目标不是 .app。' ;; esac
[ -d "$APP/Contents" ] && [ ! -L "$APP/Contents" ] || fail '无效的 Contents 目录。'
# Do not traverse UserData. Unexpected outer entries fail closed rather than
# being deleted or silently dequarantined.
shopt -s nullglob dotglob
for NODE in "$APP"/*; do
    case "${NODE##*/}" in Contents|.DS_Store) ;; *) fail '应用外层有未知条目；未修改。' ;; esac
done
for NODE in "$APP/Contents"/*; do
    case "${NODE##*/}" in Info.plist|MacOS|Resources|portable-update.json|UserData|.DS_Store) ;;
        *) fail 'Contents 中有未知条目或更新事务；未修改。请勿删除数据或备份。' ;;
    esac
done
shopt -u nullglob dotglob
WORK=$(mktemp -d "${TMPDIR:-/tmp}/oxideterm-first-launch.XXXXXXXX")
trap 'rm -rf -- "$WORK"' EXIT
if [ -z "$ARCHIVE" ]; then
    ARCHIVE="$WORK/release.zip"
    /usr/bin/curl --fail --location --silent --show-error --proto '=https' \
        --proto-redir '=https' --tlsv1.2 --connect-timeout 20 --max-time 300 \
        --output "$ARCHIVE" "$URL" || fail '无法获取参考 ZIP；未修改应用。'
fi
[ -f "$ARCHIVE" ] && [ ! -L "$ARCHIVE" ] || fail '参考 ZIP 不存在或是链接。'
ACTUAL=$(/usr/bin/shasum -a 256 "$ARCHIVE")
[ "${ACTUAL%% *}" = "$EXPECTED" ] || fail 'ZIP 校验值不匹配；拒绝放行。'
/usr/bin/ditto -x -k "$ARCHIVE" "$WORK/reference"
REF="$WORK/reference/OxideTerm.app/Contents"
[ -d "$REF" ] || fail '参考包结构无效。'
ENTRIES=(Info.plist MacOS Resources portable-update.json)
for ENTRY in "${ENTRIES[@]}"; do
    DEST="$APP/Contents/$ENTRY"
    [ -e "$DEST" ] && [ ! -L "$DEST" ] || fail "程序条目缺失或是链接：$ENTRY"
    /usr/bin/find "$DEST" \( -type l -o \( ! -type d ! -type f \) -o \( -type f -links +1 \) \) -print > "$WORK/unsafe"
    [ ! -s "$WORK/unsafe" ] || fail "程序条目含链接或特殊文件：$ENTRY"
    /usr/bin/diff -qr -x .DS_Store "$REF/$ENTRY" "$DEST" > "$WORK/diff" || fail "程序内容与已发布版本不同：$ENTRY。拒绝放行，不覆盖文件。"
done
# Validate each embedded Mach-O signature outside the mutable app hierarchy.
COUNT=0
/usr/bin/find "$REF/MacOS" "$REF/Resources" -type f -print0 > "$WORK/reference-files"
while IFS= read -r -d '' FILE; do
    TYPE=$(/usr/bin/file -b "$FILE")
    case "$TYPE" in
        Mach-O*)
            REL=${FILE#"$REF/"}
            [ -x "$APP/Contents/$REL" ] || fail "程序缺少执行权限：$REL"
            /bin/cp "$APP/Contents/$REL" "$WORK/verified-macho"
            /usr/bin/codesign --verify --strict "$WORK/verified-macho" || fail "内部程序签名无效：$REL"
            COUNT=$((COUNT + 1)) ;;
    esac
done < "$WORK/reference-files"
[ "$COUNT" -eq 5 ] || fail '内部 ARM64 程序数量异常。'
printf '\n已验证：ZIP SHA256、全部程序文件以及 %s 个内部程序签名。\n' "$COUNT"
printf '目标：%s\n' "$APP"
if [ "$MODE" = check ]; then
    printf '%s\n' '检查完成，未修改应用。确认信任此自用版本后，用 --allow-local-use 再次运行。'
    exit 0
fi
# Enumerate only entries present in the immutable reference; never recurse
# through UserData (which can contain separately downloaded, untrusted files).
printf '%s\0' "$APP" "$APP/Contents" > "$WORK/targets"
for ENTRY in "${ENTRIES[@]}"; do
    /usr/bin/find "$REF/$ENTRY" -print0 > "$WORK/entry-paths"
    while IFS= read -r -d '' FILE; do
        REL=${FILE#"$REF/"}
        printf '%s\0' "$APP/Contents/$REL" >> "$WORK/targets"
    done < "$WORK/entry-paths"
done
REMOVED=0
while IFS= read -r -d '' NODE; do
    [ ! -L "$NODE" ] || fail '校验后出现符号链接；已停止。'
    if /usr/bin/xattr -p com.apple.quarantine "$NODE" >/dev/null 2>&1; then
        /usr/bin/xattr -d com.apple.quarantine "$NODE" || fail '没有权限修改此应用；不要使用 sudo 或修改全局安全策略。'
        REMOVED=$((REMOVED + 1))
    fi
done < "$WORK/targets"
printf '\n已移除 %s 个程序条目的隔离标记。程序内容和 UserData 未修改。\n' "$REMOVED"
printf '%s\n' '现在可重新双击所选 OxideTerm.app。此操作不等于签名公证或 Apple 安全认证。'
