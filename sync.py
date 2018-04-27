#! /usr/bin/python3
# -*- coding: utf-8 -*-

import os, subprocess, argparse, re, collections

DESCRIPTION = 'Syncs directory in local-machine and remote-servers.'

parser = argparse.ArgumentParser(description=DESCRIPTION)
parser.add_argument('src', action='store', nargs=1, type=str, help='Directory to sync in local machine.')
parser.add_argument('dests', action='store', nargs='+', type=str, help='Directories to sync in remote machines.')
parser.add_argument('--dry-run', action='store_true', help='Activates dry-run option of rsync.')
parser.add_argument('--coding', action='store', type=str, default='utf-8', help='Coding system of your prompt.')
args = parser.parse_args()

OPTS = ['-ahvz'] + ['--exclude=%s' % e for e in EXCLUSION]

is_local = lambda host: (host == 'local')


## Target of sync.
class Target:
    def __init__(self, host, path):
        self.host = host
        self.path = path

    def __str__(self):
        if self.is_local():
            return self.path
        else
            return '%s:%s' % (self.host, self.path)

    def is_local(self):
        return self.host == 'local'


def find_files(target, name):
    if target.is_local():
        return run_command('find %s -name %s' % target.path, name).split()
    else:
        return run_command('ssh %s find %s -name %s' % (target.host, target.path, name)).split()
    

## Reads configuration file at given path.
def read_syncconf(path = '.sync.conf'):
    set_only   = set()
    set_ignore = set()
    
    with open(path) as fi:
        for line in fi:
            line = line.strip()
            
            if line.startswith('#'):
                continue # Comment lines
            
            spl = line.split(maxsplit = 1)
            
            if spl[0] == 'only':
                set_only.add(tuple(spl[1].split(':', 1)))
            elif spl[0] == 'ignore':
                set_ignore.add(spl[1])

    SyncConf = collections.namedtuple('SyncConf', ('only', 'ignore'))
    return SyncConf(set_only, set_ignore)


## Reads .syncignore files in the directory given and returns snipets to be ignored.
## @param target Target of sync.
def read_syncignore(target):
    out = []
    paths = find_files(target, '.syncignore')

    for path in paths:
        if target.is_local():
            ignored = run_command('cat %s' % path).split('\n')
        else:
            ignored = run_command('ssh %s cat %s' % (host, path)).split('\n')
            
        reldir = os.path.dirname(path)[len(target.path):].strip('/')
        out += ['%s/%s' % (reldir, x.strip()) for x in ignored]
            
    return out


## Executes unix-command given and returns its output.
## @param cmd Command to execute.
def run_command(cmd, coding):
    print('> ' + cmd)
    out = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE).stdout
    return out.decode(coding)


## Removes files which another host should manage.
def clear(target, conf):
    removed = []

    # Enumerate files to remove
    for host, snipet in conf.only:
        if host != target.host:
            removed += [x.strip() for x in find_files(target, snipet).split('\n')]

    # Remove files
    if target.is_local():
        pass
    else:
        pass

## Executes rsync.
## @param src Source of sync.
## @param dest Destination of sync.
## @param args Parsing result of command options.
def rsync(src, dest, args):
    assert(src.is_local() or dest.is_local())

    ignored = read_syncignore(src)

    cmd = ' '.join(
        ['rsync', '-ahvz'] +
        (['--dry-run'] if args.dry_run else []) +
        ['--exclude=%s' % e for e in ignored] +
        [str(src), str(dest)])

    run_command(cmd, args.coding)


## Executes rsync in update-mode.
def update(target):
    opts = OPTS + ['--update']

    for remote in get_remotes():
        print_job(target, remote, LOCAL, 'update')
        rsync(target, remote, LOCAL, opts)

    opts += ['--exclude=%s' % e for e in ENCRYPTED]

    for remote in get_remotes():
        print_job(target, LOCAL, remote, 'update')
        rsync(target, LOCAL, remote, opts)


## Executes rsync in delete-mode.
def delete(target):
    opts = OPTS + ['--delete'] + ['--exclude=%s' % e for e in ENCRYPTED]

    for remote in get_remotes():
        print_job(target, LOCAL, remote, 'delete')
        rsync(target, LOCAL, remote, opts)


## Main procedure.
## Reads command line and executes rsync in the mode specified.
def main():
    global is_dry_run, do_target_daiba

    description = '\n'.join([
        'This script to sync working directories in local and remote-servers.',
        'Update mode copies all files in all workspaces to all workspaces.',
        'Delete mode deletes files which do not exist in local workspace.'])
    
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('mode', action='store', nargs=1, type=str, choices=['delete', 'update'], help='Execution mode.')
    parser.add_argument('--dry-run', action='store_true', help='Activates dry-run option of rsync.')
    parser.add_argument('--daiba', action='store_true', help='Syncs with remote-servers in daiba cluster.')

    args = parser.parse_args()
    mode = args.mode[0]
    is_dry_run = args.dry_run
    do_target_daiba = args.daiba

    if mode == 'update':
        for t in TARGETS:
            update(t)

    if mode == 'delete':
        for t in TARGETS:
            delete(t)


if __name__=='__main__':
    main()
