from __future__ import absolute_import

import subprocess


def install(package):
    cmd = "ansible-galaxy install {0}".format(package)
    retcode = subprocess.call(cmd,
                              shell=True)

    return retcode == 0


def get_role_paths():
    """
    Returns a list of all the roles paths which Ansible-galaxy uses when
    searching for roles

    In the future, we should read the ansible.cfg and combine it with
    linchpin.conf, since this data is set in ansible.cfg.
    """
    paths = []

    cmd = "ansible-galaxy list"
    proc = subprocess.Popen(cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    proc.wait()

    for line in proc.stdout:
        if line.startswith(b'#'):
            path = line[2:].strip()
            paths.append(path.decode('utf-8'))

    for line in proc.stderr:
        if line.strip().startswith(b'[WARNING]: - the configured path'):
            before = b'the configured path '
            start_idx = line.index(before) + len(before) - 1
            path = line[start_idx:].strip()
            end_idx = path.index(b' ')
            path = path[:end_idx].strip()
            paths.append(path.decode('utf-8'))

    return paths
