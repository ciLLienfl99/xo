#!/usr/bin/env python3
"""Validate existing Actions output without compiling or executing untrusted code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

repo = os.environ['GH_REPO']
root = Path.cwd()
release = root / 'release-files'
release.mkdir()
temp = Path(os.environ['RUNNER_TEMP']) / ('verified-release-' + os.environ['GITHUB_RUN_ID'])
temp.mkdir()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + repo + '/' + path], text=True))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def trusted_run(run, workflow):
    return (run.get('conclusion') == 'success'
            and run.get('status') == 'completed'
            and run.get('path', '').split('@')[0] == workflow
            and run.get('head_branch') == 'main'
            and run.get('head_repository', {}).get('full_name') == repo
            and run.get('repository', {}).get('full_name') == repo)


def build_inputs(sha):
    tree = api('git/trees/' + sha + '?recursive=1')
    require(not tree.get('truncated'), 'Cannot compare a truncated source tree')
    return {entry['path']: entry['sha'] for entry in tree['tree']
            if entry['type'] == 'blob' and
            (entry['path'].startswith('build/') or entry['path'] in
             ('.github/workflows/mac-arm64.yml', '.github/workflows/mac-arm64-smoke.yml'))}


requested = os.environ.get('REQUESTED_BUILD', '').strip()
if requested:
    require(re.fullmatch(r'[0-9]+', requested), 'Invalid build run ID')
    build = api('actions/runs/' + requested)
else:
    runs = api('actions/runs?branch=main&status=success&per_page=100')['workflow_runs']
    candidates = [run for run in runs if trusted_run(run, '.github/workflows/mac-arm64.yml')]
    require(candidates, 'No successful ARM64 build exists; run Build Mac ARM64 Bundle first')
    build = max(candidates, key=lambda run: (run['run_number'], run['run_attempt']))
require(trusted_run(build, '.github/workflows/mac-arm64.yml'), 'Build did not pass on this repository main branch')
require(re.fullmatch(r'[0-9a-f]{40}', build['head_sha']), 'Invalid build commit')
current_inputs = build_inputs(os.environ['GITHUB_SHA'])
require(current_inputs and current_inputs == build_inputs(build['head_sha']),
        'Build configuration changed since this artifact was compiled; a new full build is required')
jobs = api('actions/runs/' + str(build['id']) + '/jobs?per_page=100')['jobs']
completed = {step['name'] for job in jobs for step in job['steps'] if step['conclusion'] == 'success'}
require({'Build native application and packages', 'Verify native packages',
         'Prepare single-app download', 'Upload Mac ARM64 application',
         'Test native portable runtime and updater'} <= completed,
        'Required compilation, verification, or test step did not pass')


def download_artifact(run_id, name, destination):
    items = api('actions/runs/' + str(run_id) + '/artifacts?per_page=100')['artifacts']
    matches = [item for item in items if item['name'] == name and not item['expired']]
    require(len(matches) == 1, 'Missing, duplicate, or expired artifact: ' + name)
    item = matches[0]
    expected = item.get('digest', '')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', expected), 'Missing artifact SHA256: ' + name)
    archive = temp / (str(item['id']) + '.zip')
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', 'repos/' + repo + '/actions/artifacts/' + str(item['id']) + '/zip'], stdout=stream, check=True)
    require('sha256:' + sha256(archive) == expected, 'Artifact digest mismatch: ' + name)
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        names = set()
        for info in bundle.infolist():
            path = PurePosixPath(info.filename)
            require(len(path.parts) == 1 and path.name not in ('.', '..')
                    and '\\' not in info.filename and not info.is_dir(), 'Unexpected artifact path')
            require(path.name not in names and (info.external_attr >> 16) & 0o170000 != 0o120000,
                    'Duplicate or linked artifact entry')
            names.add(path.name)
            require(info.file_size <= 512 * 1024 * 1024, 'Artifact entry exceeds size limit')
            (destination / path.name).write_bytes(bundle.read(info))
    return item


app_artifact = download_artifact(build['id'], 'OxideTerm-Mac-ARM64-Bundle', release)
checksum = (release / 'SHA256.txt').read_text().strip().split()
require(len(checksum) == 2 and re.fullmatch(r'[0-9a-f]{64}', checksum[0]), 'Invalid application checksum')
match = re.fullmatch(r'OxideTerm-([0-9]+\.[0-9]+\.[0-9]+)-Mac-ARM64-Bundle\.zip', checksum[1])
require(match, 'Unexpected application filename')
version = match.group(1)
app = release / checksum[1]
require(sha256(app) == checksum[0], 'Application checksum mismatch')
require({p.name for p in release.iterdir()} == {app.name, 'SHA256.txt', '使用与升级说明.md'},
        'Unexpected application artifact contents')
with zipfile.ZipFile(app) as bundle:
    for info in bundle.infolist():
        path = PurePosixPath(info.filename)
        require(path.parts and path.parts[0] == 'OxideTerm.app'
                and not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename,
                'Application must be one safe .app bundle')
        require((info.external_attr >> 16) & 0o170000 != 0o120000, 'Application contains a symbolic link')
        if len(path.parts) >= 3:
            require(path.parts[1] == 'Contents', 'Files outside app Contents')
            require(path.parts[2].lower() not in ('userdata', 'data', 'portable', 'portable.json', '_codesignature'),
                    'Application contains user data, external markers, or an outer signature')
    manifest = json.loads(bundle.read('OxideTerm.app/Contents/portable-update.json'))
    require(manifest == {'formatVersion': 2, 'appExecutable': 'MacOS/oxideterm-native',
            'updateHelper': 'MacOS/oxideterm-update-helper',
            'managedEntries': ['Info.plist', 'MacOS', 'Resources', 'portable-update.json']},
            'Unexpected portable updater replacement scope')

smoke_id = os.environ.get('TRIGGER_SMOKE', '').strip()
if smoke_id:
    require(re.fullmatch(r'[0-9]+', smoke_id), 'Invalid startup-check ID')
    smoke = api('actions/runs/' + smoke_id)
else:
    runs = api('actions/runs?branch=main&status=success&per_page=100')['workflow_runs']
    candidates = [run for run in runs if trusted_run(run, '.github/workflows/mac-arm64-smoke.yml')
                  and run['created_at'] >= build['created_at']]
    require(candidates, 'No successful startup check exists for this build')
    smoke = max(candidates, key=lambda run: run['id'])
require(trusted_run(smoke, '.github/workflows/mac-arm64-smoke.yml'), 'Startup check did not succeed')
smoke_dir = temp / 'startup'
download_artifact(smoke['id'], 'OxideTerm-ARM64-Startup-Check', smoke_dir)
report = json.loads((smoke_dir / 'startup-check.json').read_text())
require(report.get('startup') == 'passed' and report.get('application_sha256') == checksum[0],
        'Startup result does not match this exact application')
require(report.get('data_directory') == 'OxideTerm.app/Contents/UserData', 'Startup used a different data directory')

source_dir = temp / 'source'
download_artifact(build['id'], 'OxideTerm-Corresponding-Source', source_dir)
source_name = 'OxideTerm-' + version + '-custom-source.tar.gz'
require({p.name for p in source_dir.iterdir()} == {source_name}, 'Unexpected corresponding-source filename')
source = source_dir / source_name
with tarfile.open(source, 'r:gz') as archive:
    require('oxideterm-custom/Cargo.toml' in archive.getnames()
            and 'oxideterm-custom/LICENSE' in archive.getnames(), 'Corresponding source or license is missing')
source.rename(release / source_name)
provenance = {'build_run_id': build['id'], 'build_run_url': build['html_url'],
    'build_commit': build['head_sha'], 'upstream_commit': '4d5933c9914ab5c5efc4ff4124bdf255f6ba619d',
    'startup_run_id': smoke['id'], 'startup_run_url': smoke['html_url'],
    'version': version,
    'target': 'aarch64-apple-darwin', 'application_sha256': checksum[0],
    'original_actions_artifact_digest': app_artifact['digest'],
    'scope': 'Automated compilation, package verification, native tests and initial startup; not interactive SSH/SFTP or Gatekeeper/notarization approval'}
(release / 'BUILD-PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')
files = sorted(release.iterdir())
(release / 'SHA256SUMS.txt').write_text(''.join(sha256(path) + '  ' + path.name + '\n' for path in files))
tag = 'v' + version + '-custom-arm64-build.' + str(build['run_number'])
notes = ('## Mac ARM64 包内便携定制版\n\n'
    + '下载 **' + app.name + '**，解压后就是 `OxideTerm.app`。\n\n'
    + '包含活动会话右键菜单、独立字号和 `Contents/UserData` 包内便携存储。\n\n'
    + '**由 GitHub Actions 编译，不是官方未修改版本，也不是重新上传的本地产物。**\n\n'
    + '- [完整编译、原生测试与包校验](' + build['html_url'] + ')\n'
    + '- [独立 Mac 初始启动检查](' + smoke['html_url'] + ')\n'
    + '- 修复代码提交：`' + build['head_sha'] + '`\n\n'
    + '这是未公证的个人定制构建；初始启动检查不等于交互式 SSH/SFTP、解锁或 Gatekeeper 已验证。\n\n'
    + '**已有包内数据时，不要在 Finder 直接整包替换，也不要先删除旧应用。** '
    + '先备份，使用包内升级脚本或兼容更新器保留 UserData；详见使用与升级说明。\n\n'
    + '完整对应源码与许可证另附 `' + source_name + '`。'
    + '`Source code (zip)` 是 GitHub 自动生成的构建配置快照，不代替上述完整对应源码。\n')
(root / 'release-notes.md').write_text(notes)
with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
    output.write('tag=' + tag + '\nsha=' + build['head_sha'] + '\nversion=' + version + '\n')
print(json.dumps(provenance, indent=2))
