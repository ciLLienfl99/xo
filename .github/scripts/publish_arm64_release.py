#!/usr/bin/env python3
"""Publish only already verified Actions output; resume our own partial draft safely."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, urlopen

repo = os.environ['GH_REPO']
tag = os.environ['RELEASE_TAG']
sha = os.environ['BUILD_SHA']
if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+-custom-arm64-build\.[0-9]+', tag):
    raise RuntimeError('Invalid release tag')
if not re.fullmatch(r'[0-9a-f]{40}', sha):
    raise RuntimeError('Invalid build SHA')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return 'sha256:' + result.hexdigest()


def api(path, method='GET', payload=None):
    command = ['gh', 'api', 'repos/' + repo + '/' + path, '--method', method]
    options = {'text': True}
    if payload is not None:
        command += ['--input', '-']
        options['input'] = json.dumps(payload)
    output = subprocess.check_output(command, **options)
    return json.loads(output) if output.strip() else None


root = Path('release-files')
usage = root / '使用与升级说明.md'
if usage.exists():
    usage.rename(root / 'USAGE-AND-UPGRADE.md')
files = sorted(path for path in root.iterdir() if path.name != 'SHA256SUMS.txt')
(root / 'SHA256SUMS.txt').write_text(''.join(digest(path).split(':', 1)[1] + '  ' + path.name + '\n' for path in files))
files = sorted(root.iterdir())
expected = {path.name: digest(path) for path in files}

# The /releases/tags endpoint does not resolve an unpublished draft's tag.
# Enumerate authenticated releases and then address the immutable release ID.
releases = api('releases?per_page=100')
matches = [release for release in releases if release['tag_name'] == tag]
if len(matches) > 1:
    raise RuntimeError('More than one release has this tag')
if matches:
    metadata = matches[0]
else:
    metadata = api('releases', 'POST', {
        'tag_name': tag, 'target_commitish': sha, 'draft': True, 'prerelease': False,
        'name': 'OxideTerm ' + os.environ['APP_VERSION'] + ' · Mac ARM64 包内便携版',
        'body': Path('release-notes.md').read_text(),
    })
if metadata['target_commitish'] != sha or metadata['author']['login'] != 'github-actions[bot]':
    raise RuntimeError('Refusing to modify a release from another commit or author')
release_id = metadata['id']
assets = {asset['name']: asset for asset in metadata['assets']}
if len(assets) != len(metadata['assets']):
    raise RuntimeError('Duplicate asset names')

# Recover the documentation asset GitHub renamed during the first draft upload.
if 'default.md' in assets:
    old = assets['default.md']
    if (not metadata['draft'] or 'USAGE-AND-UPGRADE.md' in assets
            or old.get('digest') != expected['USAGE-AND-UPGRADE.md']):
        raise RuntimeError('Unexpected legacy documentation asset; no changes made')
    changed = api('releases/assets/' + str(old['id']), 'PATCH',
                  {'name': 'USAGE-AND-UPGRADE.md', 'label': '使用与升级说明（中文）'})
    del assets['default.md']
    assets[changed['name']] = changed
if set(assets) - set(expected):
    raise RuntimeError('Unexpected assets exist; refusing to remove them')

upload = metadata['upload_url'].split('{', 1)[0]
if upload != 'https://uploads.github.com/repos/' + repo + '/releases/' + str(release_id) + '/assets':
    raise RuntimeError('Unexpected asset upload endpoint')
for path in files:
    asset = assets.get(path.name)
    if asset and asset.get('digest') == expected[path.name] and asset['size'] == path.stat().st_size and asset['state'] == 'uploaded':
        continue
    if not metadata['draft']:
        raise RuntimeError('Published assets are immutable to this workflow: ' + path.name)
    if asset:
        # Only the generated checksum index can change to reflect the ASCII filename.
        if path.name != 'SHA256SUMS.txt' or asset['uploader']['login'] != 'github-actions[bot]':
            raise RuntimeError('Existing asset does not match verified build: ' + path.name)
        api('releases/assets/' + str(asset['id']), 'DELETE')
    request = Request(upload + '?' + urlencode({'name': path.name}), data=path.read_bytes(),
                      headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                               'Accept': 'application/vnd.github+json',
                               'Content-Type': 'application/octet-stream',
                               'User-Agent': 'oxideterm-verified-release'}, method='POST')
    with urlopen(request, timeout=180) as response:
        uploaded = json.load(response)
    if uploaded.get('digest') != expected[path.name]:
        raise RuntimeError('New release asset digest mismatch: ' + path.name)


def verify_uploaded(value):
    remote = {asset['name']: asset for asset in value['assets']}
    if set(remote) != set(expected):
        raise RuntimeError('Release upload is incomplete')
    for path in files:
        asset = remote[path.name]
        if asset['state'] != 'uploaded' or asset['size'] != path.stat().st_size or asset.get('digest') != expected[path.name]:
            raise RuntimeError('Release upload verification failed: ' + path.name)


metadata = api('releases/' + str(release_id))
verify_uploaded(metadata)
if metadata['draft']:
    metadata = api('releases/' + str(release_id), 'PATCH', {'draft': False, 'make_latest': 'true'})
metadata = api('releases/' + str(release_id))
verify_uploaded(metadata)
if metadata['draft'] or metadata['tag_name'] != tag:
    raise RuntimeError('Release was not published')
print('Published and verified: ' + metadata['html_url'])
for asset in metadata['assets']:
    print(asset['name'] + '  ' + asset['digest'])
with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
    summary.write('## Mac ARM64 应用已发布\n\n[打开 GitHub 下载页面](' + metadata['html_url'] + ')\n\n')
    summary.write('原始 Actions 编译产物、同一应用的启动结果及全部发布附件的 SHA256 校验通过。\n')
