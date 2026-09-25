#!/usr/bin/env python3
"""Make a sealed desktop distribution from a pinned, Actions-compiled application.

This is a distinct installed-mode variant; never mutates an installed portable app.
An ad-hoc build is NOT notarized and is never reported as Gatekeeper accepted.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import secrets
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import time
import zipfile

VERSION = '2.0.31'
BUILD_RUN = 36162224513
BUILD_SHA = 'a9475f209049a920ae58b0771472e514a5c2e91c'
APP_SHA = 'c9cd86b2d04a83638b30685cf373e34af6b0140123839d37483fdda9c333360c'
SOURCE_SHA = '454365edc01f8c6b56835da9c259d1ff88a467cf2d3ad47e5b13377057de2d1b'
APP_NAME = 'OxideTerm Desktop.app'
ROOT = Path.cwd()
OUT = ROOT / 'desktop-output'
DIAG = ROOT / 'desktop-diagnostics'
REPORT = {'status': 'not_run', 'variant': 'standard-installed', 'target': 'aarch64-apple-darwin',
          'binary_build_run': BUILD_RUN, 'binary_build_commit': BUILD_SHA,
          'packaging_commit': os.environ.get('GITHUB_SHA', 'local'),
          'gatekeeper_accepted': False, 'notarized': False,
          'data_directory': '~/.oxideterm', 'portable_data_migrated': False}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(*args, check=True, timeout=300, quiet=False):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    if not quiet:
        print(result.stdout, end='', flush=True)
        print(result.stderr, end='', flush=True)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed with exit {result.returncode}' +
                           ('' if quiet else ': ' + result.stderr[-3000:]))
    return result


def snapshot(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def validate_archive(archive):
    with zipfile.ZipFile(archive) as z:
        names = set()
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            require(p.parts and p.parts[0] == 'OxideTerm.app' and not p.is_absolute()
                    and '..' not in p.parts and '\\' not in item.filename, 'Unsafe app archive path')
            require(item.filename not in names, 'Duplicate archive entry')
            names.add(item.filename)
            require(stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK, 'Linked archive entry')
        require('OxideTerm.app/Contents/portable-update.json' in names, 'Unexpected source package')
        require(not any('/UserData/' in n or '/_CodeSignature/' in n for n in names), 'Unexpected mutable/sealed source')


def sign(path, identity, entitlements=None):
    args = ['/usr/bin/codesign', '--force', '--sign', identity]
    args += ['--timestamp=none'] if identity == '-' else ['--options', 'runtime', '--timestamp']
    if entitlements:
        args += ['--entitlements', str(entitlements)]
    run(*args, path)


def verify_bundle(app):
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2', app)
    require((app / 'Contents/_CodeSignature/CodeResources').is_file(), 'Missing complete resource seal')
    for unwanted in ('UserData', 'portable-update.json', 'portable', 'portable.json', 'data'):
        require(not (app / 'Contents' / unwanted).exists(), 'Portable state inside installed app')


def setup_signing(temp):
    keys = ('MACOS_CERTIFICATE_P12_BASE64', 'MACOS_CERTIFICATE_PASSWORD', 'MACOS_SIGNING_IDENTITY',
            'APPLE_API_KEY_BASE64', 'APPLE_API_KEY_ID', 'APPLE_API_ISSUER_ID')
    configured = [bool(os.environ.get(k)) for k in keys]
    require(not any(configured) or all(configured), 'Incomplete Apple signing credentials; refusing silent fallback')
    if not any(configured):
        REPORT['signature_kind'] = 'ad-hoc-complete-bundle'
        REPORT['apple_signing_credentials_available'] = False
        return '-', None
    REPORT['apple_signing_credentials_available'] = True
    cert = temp / 'certificate.p12'
    cert.write_bytes(base64.b64decode(os.environ[keys[0]], validate=True)); cert.chmod(0o600)
    keychain = temp / 'signing.keychain-db'
    password = secrets.token_urlsafe(32)
    run('security', 'create-keychain', '-p', password, keychain, quiet=True)
    run('security', 'set-keychain-settings', '-lut', '3600', keychain, quiet=True)
    run('security', 'unlock-keychain', '-p', password, keychain, quiet=True)
    run('security', 'import', cert, '-k', keychain, '-P', os.environ[keys[1]],
        '-T', '/usr/bin/codesign', '-T', '/usr/bin/security', quiet=True)
    run('security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:', '-s', '-k', password, keychain, quiet=True)
    original = run('security', 'list-keychains', '-d', 'user', quiet=True).stdout
    original_paths = [line.strip().strip('"') for line in original.splitlines() if line.strip()]
    run('security', 'list-keychains', '-d', 'user', '-s', keychain, *original_paths, quiet=True)
    identity = os.environ[keys[2]]
    require(identity.startswith('Developer ID Application:'), 'A Developer ID Application identity is required')
    api_key = temp / ('AuthKey_' + os.environ[keys[4]] + '.p8')
    api_key.write_bytes(base64.b64decode(os.environ[keys[3]], validate=True)); api_key.chmod(0o600)
    REPORT['signature_kind'] = 'Developer ID Application'
    return identity, (keychain, original_paths, api_key)


def notarize(path, credentials):
    args = ['xcrun', 'notarytool', 'submit', str(path), '--key', str(credentials[2]),
            '--key-id', os.environ['APPLE_API_KEY_ID'], '--issuer', os.environ['APPLE_API_ISSUER_ID'],
            '--wait', '--timeout', '20m', '--output-format', 'json']
    result = run(*args, timeout=1500, quiet=True)
    response = json.loads(result.stdout)
    require(response.get('status') == 'Accepted', 'Apple notarization did not accept the artifact')
    run('xcrun', 'stapler', 'staple', path)
    run('xcrun', 'stapler', 'validate', path)


def smoke(app, temp):
    install = temp / 'Installed Copy' / APP_NAME
    install.parent.mkdir()
    run('ditto', app, install)
    before = snapshot(install)
    executable = str(install / 'Contents/MacOS/oxideterm-native')
    def pids():
        listing = run('ps', '-axo', 'pid=,command=', quiet=True).stdout
        result = set()
        for line in listing.splitlines():
            fields = line.strip().split(None, 1)
            if len(fields) == 2 and fields[1].startswith(executable):
                result.add(int(fields[0]))
        return result
    tracked = set()
    # No xattr deletion, no re-signing after launch, no global security changes.
    try:
        run('open', '-n', install)
        for _ in range(15):
            tracked = pids()
            if tracked:
                break
            time.sleep(1)
        require(tracked, 'LaunchServices did not start the installed application')
        time.sleep(20)
        require(tracked & pids(), 'Application exited during startup')
        require((Path.home() / '.oxideterm').is_dir(), 'Installed-mode data directory was not created')
        verify_bundle(install)
        require(before == snapshot(install), 'Application mutated its signed bundle during startup')
        capture = run('screencapture', '-x', DIAG / 'desktop-startup.png', check=False)
        REPORT['screenshot_captured'] = capture.returncode == 0
        REPORT['initial_startup'] = 'passed'
        REPORT['signature_valid_after_startup'] = True
        REPORT['application_bundle_unchanged_after_startup'] = True
        REPORT['startup_scope'] = 'Non-quarantined CI startup; not Gatekeeper authorization or SSH/SFTP integration'
    finally:
        for pid in tracked | pids():
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def main():
    require(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'Requires a real ARM64 Mac')
    OUT.mkdir(); DIAG.mkdir()
    archive = ROOT / f'artifact/OxideTerm-{VERSION}-Mac-ARM64-Bundle.zip'
    source = ROOT / f'source-artifact/OxideTerm-{VERSION}-custom-source.tar.gz'
    require(sha(archive) == APP_SHA, 'Unexpected input app hash')
    require(sha(source) == SOURCE_SHA, 'Unexpected corresponding-source hash')
    validate_archive(archive)
    credentials = None
    policy_before = run('spctl', '--status', quiet=True).stdout.strip()
    REPORT['system_policy_before'] = policy_before
    with tempfile.TemporaryDirectory(prefix='oxideterm-desktop-') as tmp:
        temp = Path(tmp)
        try:
            stage = temp / 'stage'; stage.mkdir()
            run('ditto', '-x', '-k', archive, stage)
            app = stage / APP_NAME
            (stage / 'OxideTerm.app').rename(app)
            contents = app / 'Contents'
            (contents / 'portable-update.json').unlink()
            (contents / 'Resources/install_macos_bundle.py').unlink()
            info = plistlib.loads((contents / 'Info.plist').read_bytes())
            info['CFBundleName'] = 'OxideTerm Desktop'
            info['CFBundleDisplayName'] = 'OxideTerm Desktop'
            # Keep upstream identity and standard data/keychain compatibility.
            (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
            entitlements = temp / 'entitlements.plist'
            with tarfile.open(source, 'r:gz') as t:
                item = t.extractfile('oxideterm-custom/crates/oxideterm-gpui-app/resources/OxideTerm.entitlements')
                require(item is not None, 'Source entitlements missing')
                entitlements.write_bytes(item.read())
            identity, credentials = setup_signing(temp)
            binaries = []
            for path in sorted(contents.rglob('*')):
                if path.is_file() and run('file', '-b', path, quiet=True).stdout.startswith('Mach-O'):
                    require('arm64' in run('lipo', '-archs', path, quiet=True).stdout, 'Non-ARM64 executable')
                    binaries.append(path)
            require(len(binaries) == 5, 'Unexpected native executable count')
            main_binary = contents / 'MacOS/oxideterm-native'
            for binary in binaries:
                if binary != main_binary:
                    sign(binary, identity, entitlements)
            sign(app, identity, entitlements)
            verify_bundle(app)
            REPORT['whole_bundle_signature'] = 'passed'
            if credentials:
                submit = temp / 'notarization.zip'
                run('ditto', '-c', '-k', '--keepParent', app, submit)
                # Notarize ZIP, staple ticket to app (ZIP itself cannot be stapled).
                response = run('xcrun', 'notarytool', 'submit', submit, '--key', credentials[2],
                               '--key-id', os.environ['APPLE_API_KEY_ID'], '--issuer', os.environ['APPLE_API_ISSUER_ID'],
                               '--wait', '--timeout', '20m', '--output-format', 'json', timeout=1500, quiet=True)
                require(json.loads(response.stdout).get('status') == 'Accepted', 'Application notarization rejected')
                run('xcrun', 'stapler', 'staple', app)
                run('xcrun', 'stapler', 'validate', app)
                REPORT['notarized'] = True
            # Assess a quarantined COPY; do not suppress or misreport rejection.
            assessed = temp / 'quarantine-test' / APP_NAME
            assessed.parent.mkdir()
            run('ditto', app, assessed)
            run('/usr/bin/xattr', '-w', 'com.apple.quarantine', f'0083;{int(time.time()):x};DesktopPackageTest;', assessed)
            verify_bundle(assessed)
            gate = run('spctl', '--assess', '--type', 'execute', '--verbose=4', assessed, check=False, timeout=90)
            REPORT['gatekeeper_accepted'] = gate.returncode == 0
            REPORT['gatekeeper_result'] = (gate.stdout + gate.stderr).strip()
            if credentials:
                require(gate.returncode == 0, 'Notarized app failed Gatekeeper')
            else:
                require('code has no resources' not in gate.stderr, 'Old malformed resource seal still present')
            smoke(app, temp)
            install_text = (
                '# OxideTerm Desktop — Mac ARM64 安装版\n\n'
                '打开 DMG，把 OxideTerm Desktop.app 拖到 Applications。无需终端或修复脚本。\n\n'
                '这是标准安装版，不是包内便携版：用户数据采用原程序的 ~/.oxideterm 隐藏目录，'
                '或设置中原有的自定义目录。替换应用不会覆盖这些数据。\n'
                '保留活动会话右键菜单和独立字号。旧 OxideTerm.app 不会被同名覆盖；'
                '旧 Contents/UserData 不会自动迁移，先保留旧应用和备份。\n\n'
                + ('此版本已通过 Developer ID 签名、公证和 Gatekeeper 检查。\n' if REPORT['notarized'] else
                   '此版本只有完整的 ad-hoc 本地签名，没有 Developer ID 公证。签名完整不等于苹果认可。'
                   '首次打开仍可能被拦截：确认信任此定制版后，可在系统设置 → 隐私与安全性 → 仍要打开中授权。'
                   '不是“无安全提示安装版”，不要关闭全局 Gatekeeper。\n')
                + '\n自动化测试覆盖包完整性与初始启动，不包括真实 SSH/SFTP 会话或旧数据迁移。'
                  '这是个人定制版；安装未经定制的官方更新会丢失界面修改。\n')
            (OUT / 'INSTALLATION.md').write_text(install_text)
            (stage / 'INSTALLATION.txt').write_text(install_text)
            (stage / 'Applications').symlink_to('/Applications')
            dmg = OUT / f'OxideTerm-{VERSION}-Mac-ARM64-Desktop.dmg'
            run('hdiutil', 'create', '-volname', 'OxideTerm Desktop', '-srcfolder', stage,
                '-ov', '-format', 'UDZO', dmg, timeout=300)
            if credentials:
                sign(dmg, identity)
                notarize(dmg, credentials)
            run('hdiutil', 'verify', dmg)
            mounted = temp / 'mounted'; mounted.mkdir()
            run('hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mounted, dmg)
            try:
                verify_bundle(mounted / APP_NAME)
                require(snapshot(app) == snapshot(mounted / APP_NAME), 'DMG changed application bytes')
            finally:
                run('hdiutil', 'detach', mounted)
            REPORT['disk_image_verification'] = 'passed'
            app_zip = OUT / f'OxideTerm-{VERSION}-Mac-ARM64-Desktop.app.zip'
            run('ditto', '-c', '-k', '--keepParent', app, app_zip)
            shutil.copy2(source, OUT / source.name)
            with tarfile.open(OUT / 'Desktop-Packaging-Source.tar.gz', 'w:gz') as t:
                for p in (Path(__file__), ROOT / '.github/workflows/mac-arm64-desktop.yml'):
                    t.add(p, arcname=str(p.relative_to(ROOT)))
            policy_after = run('spctl', '--status', quiet=True).stdout.strip()
            require(policy_before == policy_after, 'Global Gatekeeper policy changed')
            REPORT['global_policy_unchanged'] = True
            REPORT['dmg_sha256'] = sha(dmg)
            REPORT['zip_sha256'] = sha(app_zip)
            REPORT['status'] = 'passed'
            REPORT['limitations'] = 'Not a portable bundle; no automatic old-data migration; no interactive SSH/SFTP test'
            (OUT / 'VERIFICATION.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + '\n')
            (OUT / 'SHA256SUMS.txt').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in sorted(OUT.iterdir())))
        finally:
            if credentials:
                run('security', 'list-keychains', '-d', 'user', '-s', *credentials[1], check=False, quiet=True)
                run('security', 'delete-keychain', credentials[0], check=False, quiet=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        REPORT['status'] = 'failed'
        REPORT['error'] = str(error)
        raise
    finally:
        DIAG.mkdir(exist_ok=True)
        (DIAG / 'verification.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(REPORT, ensure_ascii=False, indent=2), flush=True)
