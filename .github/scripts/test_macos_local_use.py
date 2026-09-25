"""Test a hash-gated LOCAL-USE override, NOT notarization acceptance."""
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path.cwd()
OUT = ROOT / 'local-use-results'
OUT.mkdir(exist_ok=True)
SCRIPT = ROOT / 'support/OxideTerm-First-Launch.command'
ARCHIVE = ROOT / 'reference.zip'
SHA = 'c9cd86b2d04a83638b30685cf373e34af6b0140123839d37483fdda9c333360c'
URL = 'https://github.com/ciLLienfl99/xo/releases/download/v2.0.31-custom-arm64-build.3/OxideTerm-2.0.31-Mac-ARM64-Bundle.zip'
report = {'status': 'not_run', 'scope': 'Explicit per-app local-use override; NOT Gatekeeper acceptance, notarization, or SSH/SFTP testing'}
tracked = set()

def run(args, check=True, timeout=90):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            encoding='utf-8', errors='backslashreplace', timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stdout[-3000:]} {result.stderr[-3000:]}')
    return result

def set_xattr(path, name, value):
    run(['/usr/bin/xattr', '-w', name, value.decode('utf-8'), path])

def get_xattr(path, name):
    return run(['/usr/bin/xattr', '-p', name, path]).stdout.rstrip('\n').encode('utf-8')

def list_xattrs(path):
    return run(['/usr/bin/xattr', path]).stdout.splitlines()

def require(value, message):
    if not value:
        raise RuntimeError(message)

def filehash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def pids(executable):
    found = set()
    for line in run(['/bin/ps', '-axo', 'pid=,command=']).stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and fields[1].startswith(str(executable)):
            found.add(int(fields[0]))
    return found

try:
    require(sys.platform == 'darwin', 'macOS is required')
    report['macos'] = run(['/usr/bin/sw_vers', '-productVersion']).stdout.strip()
    report['architecture'] = run(['/usr/bin/uname', '-m']).stdout.strip()
    require(report['architecture'] == 'arm64', 'ARM64 runner is required')
    policy_before = run(['/usr/sbin/spctl', '--status'], check=False)
    policy_state = (policy_before.returncode, policy_before.stdout, policy_before.stderr)
    report['system_policy_before'] = policy_before.stdout.strip()
    run(['/usr/bin/curl', '--fail', '--location', '--silent', '--show-error', '--proto', '=https', '--proto-redir', '=https', '--tlsv1.2', '--max-time', '300', '-o', ARCHIVE, URL], timeout=310)
    require(filehash(ARCHIVE) == SHA, 'Reference ZIP hash mismatch')
    report['application_sha256'] = SHA
    stage = ROOT / 'Local Use 测试'
    run(['/usr/bin/ditto', '-x', '-k', ARCHIVE, stage])
    app = stage / 'OxideTerm.app'
    contents = app / 'Contents'
    data = contents / 'UserData'
    require(not data.exists(), 'Release already contains UserData')
    data.mkdir()
    sentinel = data / 'preserve-test.dat'
    sentinel.write_bytes(b'CI test data: preserve all bytes and quarantine')
    sentinel_digest = filehash(sentinel)
    outside = ROOT / 'separately-downloaded-file'
    outside.write_bytes(b'outside the app: never dequarantine this')
    (data / 'untrusted-link').symlink_to(outside)
    quarantine = f'0083;{int(time.time()):x};OxideTermLocalUseTest;{uuid.uuid4()}'.encode()
    for path in [app] + list(contents.rglob('*')):
        if not path.is_symlink():
            set_xattr(path, 'com.apple.quarantine', quarantine)
    set_xattr(outside, 'com.apple.quarantine', quarantine)
    info = contents / 'Info.plist'
    info_bytes = info.read_bytes()
    prefix = ['/bin/bash', SCRIPT, '--app', app, '--archive', ARCHIVE]
    bad_zip = ROOT / 'corrupt.zip'
    bad_zip.write_bytes(b'not the published archive')
    result = run(['/bin/bash', SCRIPT, '--allow-local-use', '--app', app, '--archive', bad_zip], check=False)
    require(result.returncode != 0, 'Corrupt archive was accepted')
    require(get_xattr(app, 'com.apple.quarantine') == quarantine, 'Failed check changed quarantine')
    report['reject_wrong_archive_without_changes'] = True
    info.write_bytes(info_bytes + b'changed')
    result = run(prefix + ['--allow-local-use'], check=False)
    require(result.returncode != 0, 'Modified application was accepted')
    require(get_xattr(app, 'com.apple.quarantine') == quarantine, 'Failed content check changed quarantine')
    info.write_bytes(info_bytes)
    report['reject_modified_program_without_changes'] = True
    native = contents / 'MacOS/oxideterm-native'
    hardlink = ROOT / 'program-hardlink'
    os.link(native, hardlink)
    result = run(prefix + ['--allow-local-use'], check=False)
    require(result.returncode != 0, 'Hard-linked program was accepted')
    hardlink.unlink()
    report['reject_program_hardlinks'] = True
    result = run(prefix + ['--check'])
    (OUT / 'read-only-check.txt').write_text(result.stdout + result.stderr)
    require(get_xattr(app, 'com.apple.quarantine') == quarantine, 'Read-only check changed quarantine')
    report['read_only_check_preserves_quarantine'] = True
    signed = run(['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2', app], check=False)
    assessed = run(['/usr/sbin/spctl', '--assess', '--type', 'execute', '--verbose=2', app], check=False)
    report['whole_bundle_codesign_exit'] = signed.returncode
    report['whole_bundle_codesign_message'] = signed.stderr.strip()
    report['gatekeeper_assessment_exit'] = assessed.returncode
    report['gatekeeper_assessment_message'] = assessed.stderr.strip()
    require(assessed.returncode != 0, 'Unexpected Gatekeeper acceptance; inspect runner policy')
    report['gatekeeper_accepted'] = False
    result = run(prefix + ['--allow-local-use'])
    (OUT / 'local-use-override.txt').write_text(result.stdout + result.stderr)
    require('com.apple.quarantine' not in list_xattrs(app), 'App root remains quarantined')
    with zipfile.ZipFile(ARCHIVE) as archive:
        for entry in archive.infolist():
            target = stage / entry.filename
            require('com.apple.quarantine' not in list_xattrs(target), 'Program quarantine remains')
            if not entry.is_dir():
                require(filehash(target) == hashlib.sha256(archive.read(entry)).hexdigest(), 'Program bytes changed')
    require(filehash(sentinel) == sentinel_digest, 'UserData changed')
    require(get_xattr(sentinel, 'com.apple.quarantine') == quarantine, 'UserData quarantine was removed')
    require(get_xattr(outside, 'com.apple.quarantine') == quarantine, 'External file quarantine was removed')
    require(get_xattr(data, 'com.apple.quarantine') == quarantine, 'UserData directory metadata changed')
    run(prefix + ['--allow-local-use'])
    policy_after = run(['/usr/sbin/spctl', '--status'], check=False)
    require((policy_after.returncode, policy_after.stdout, policy_after.stderr) == policy_state, 'Global policy changed')
    report['program_bytes_unchanged'] = True
    report['userdata_bytes_and_quarantine_unchanged'] = True
    report['outside_link_quarantine_unchanged'] = True
    report['global_policy_unchanged'] = True
    report['repeated_override_idempotent'] = True
    run(['/usr/bin/open', '-n', app])
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        tracked = pids(native)
        if tracked:
            break
        time.sleep(1)
    require(tracked, 'Launch Services did not start the app after local override')
    time.sleep(20)
    require(tracked & pids(native), 'Application exited during startup observation')
    capture = run(['/usr/sbin/screencapture', '-x', OUT / 'after-local-override.png'], check=False)
    report['screenshot_captured'] = capture.returncode == 0
    report['local_startup_observation_seconds'] = 20
    report['local_startup'] = 'passed'
    report['status'] = 'passed'
except Exception as error:
    report['status'] = 'failed'
    report['error'] = str(error)
    raise
finally:
    (OUT / 'local-use-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    for pid in tracked:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
