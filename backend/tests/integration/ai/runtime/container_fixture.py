"""Credential-free bounded OS resource fixture, piped to an already accepted local image.

Not a pytest test: Docker/native runtime acceptance is an explicit coordinated operation,
not an implicit dependency of every backend test collection. Never mounts credentials.
"""

RESOURCE_PROBE = r"""
import errno, json, os, pathlib, signal, subprocess, sys
assert os.getuid() == 10001
root = pathlib.Path('/sys/fs/cgroup')
limits = {name: (root / name).read_text().strip() for name in ('pids.max', 'memory.max', 'cpu.max')}
assert limits['pids.max'] == '32'
assert limits['memory.max'] == '67108864'
assert limits['cpu.max'] == '25000 100000'
try:
    pathlib.Path('/app/proof-write-must-fail').write_text('synthetic')
except OSError:
    pass
else:
    raise AssertionError('Root filesystem writable')
children = []
denied = False
try:
    for _ in range(40):
        try:
            child = os.fork()
        except OSError as error:
            assert error.errno == errno.EAGAIN
            denied = True
            break
        if child == 0:
            signal.pause()
            os._exit(0)
        children.append(child)
    assert denied
finally:
    for child in children:
        os.kill(child, signal.SIGKILL)
    for child in children:
        os.waitpid(child, 0)
assert len(children) < 32
try:
    while True:
        os.waitpid(-1, os.WNOHANG)
except ChildProcessError:
    pass
else:
    raise AssertionError('Children remain')
quota = False
try:
    with open('/tmp/quota-probe', 'wb', buffering=0) as target:
        for _ in range(16):
            target.write(b'x' * 1048576)
except OSError as error:
    assert error.errno == errno.ENOSPC
    quota = True
finally:
    pathlib.Path('/tmp/quota-probe').unlink(missing_ok=True)
assert quota
executable = pathlib.Path('/tmp/noexec-probe')
executable.write_text('#!/bin/sh\nexit 0\n')
executable.chmod(0o700)
try:
    subprocess.run([str(executable)], check=True, timeout=1)
except PermissionError:
    pass
else:
    raise AssertionError('Tmpfs execution unexpectedly allowed')
finally:
    executable.unlink()
print(json.dumps({'limits':limits,'fork_limit_denied':True,'all_fixture_children_reaped':True,
 'tmp_quota_denied':True,'tmp_noexec_denied':True,'readonly_root':True,
 'native_cli_resource_fit_proven':False,'production_enabled':False}))
"""
