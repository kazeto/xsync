#! /usr/bin/python3
# -*- coding: utf-8 -*-

import os, subprocess, argparse, re, collections, logging
from functools import partial

DESCRIPTION = 'Syncs directory in local-machine and remote-servers.'

parser = argparse.ArgumentParser(description=DESCRIPTION)
parser.add_argument('src', action='store', nargs=1, type=str, help='Directory to sync in local machine.')
parser.add_argument('dests', action='store', nargs='+', type=str, help='Directories to sync in remote machines.')
parser.add_argument('--dry-run', action='store_true', help='Activates dry-run option of rsync.')
parser.add_argument('--no-color', action='store_true', help='Disables ANSI color sequences in logs.')
parser.add_argument('--coding', action='store', type=str, default='utf-8', help='Coding system of your prompt.')
opts = parser.parse_args()


def ansi_color(code, text, is_bold=False):
    if is_bold:
        code = ('1;' + code)
    return '\033[%sm%s\033[0m' % (code, text)

ansi_red    = partial(ansi_color, '31')
ansi_green  = partial(ansi_color, '32')
ansi_yellow = partial(ansi_color, '33')
ansi_blue   = partial(ansi_color, '34')
ansi_pink   = partial(ansi_color, '35')
ansi_cyan   = partial(ansi_color, '36')
ansi_silver = partial(ansi_color, '37')
ansi_gray   = partial(ansi_color, '90')


def make_logger(level):
    global opts

    if opts.no_color:
        fmt = '[%(name)s] %(levelname)s: %(message)s'
    else:
        fmt = ansi_pink('[%(name)s] ') + ansi_cyan('%(levelname)s: %(message)s')
    
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter(fmt))

    logger = logging.getLogger(__name__)
    logger.addHandler(_sh)
    logger.setLevel(level)
    return logger

logger = make_logger(logging.DEBUG)


is_local = lambda host: (host == 'local')


## Target of sync.
class Target:
    def __init__(self, host, path):
        self.host = host
        self.path = path

    def __str__(self):
        if self.is_local():
            return self.path
        else:
            return '%s:%s' % (self.host, self.path)

    def is_local(self):
        return self.host == 'local'

    @staticmethod
    def str2target(s):
        i = s.find(':')
        if i >= 0:
            return Target('local', s)
        else:
            return Target(s[:i], s[i+1:])


## Executes unix-command given and returns its output.
## @param cmd Command to execute.
## @return String returned by the command.
def run_command(cmd, dry_run = False):
    global opts

    if dry_run:
        logger.info('run(dry): %s' % cmd)
    else:
        logger.info('run: %s' % cmd)
    
    if dry_run:
        return ''
    else:
        out = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE).stdout
        return out.decode(opts.coding)


## Lists up files of the name given in the target directory.
## @param target Target instance.
## @param name   Snipet for find command.
def find_files(target, name):
    if target.is_local():
        cmd = 'find "%s" -name "%s"' % (target.path, name)
    else:
        cmd = 'ssh %s find "%s" -name "%s"' % (target.host, target.path, name)
        
    return run_command(cmd).split()
    

## Reads configuration file at given path.
def read_syncconf(path = '.sync.conf'):
    logger.info('read syncconf at "%s"' % path)
    
    set_only   = set()
    set_ignore = set()
    
    with open(path) as fi:
        for line in fi:
            line = line.strip()
            
            if line.startswith('#'):
                continue # Comment lines
            
            spl = line.split()
            
            if spl[0] == 'only':
                assert(':' in spl[1])
                host, snipet = spl[1].split(':', 1)
                assert(host == 'local' or host == 'remote')
                set_only.add((host, snipet))
                logger.debug('only: %s:%s' % (host, snipet))
                
            elif spl[0] == 'ignore':
                snipet = spl[1]
                set_ignore.add(snipet)
                logger.debug('ignore: %s' % snipet)

    SyncConf = collections.namedtuple('SyncConf', ('only', 'ignore'))
    return SyncConf(set_only, set_ignore)


## Reads .syncignore files in the directory given and returns snipets to be ignored.
## @param target Target of sync.
## @return Snipets to exclude from sync.
def read_syncignore(target):
    logger.info('read syncignore in %s' % target)
    
    out = []
    paths = find_files(target, '.syncignore')

    for path in paths:
        logger.debug('read %s:%s' % (target.host, path))
        
        if target.is_local():
            ignored = run_command('cat "%s"' % path).split('\n')
        else:
            ignored = run_command('ssh %s cat "%s"' % (host, path)).split('\n')
            
        reldir = os.path.dirname(path)[len(target.path):].strip('/')
        ignored = ['%s/%s' % (reldir, x.strip()) for x in ignored]
        
        out += ignored
        logger.debug('ignore: [%s]' % ', '.join(ignored))
            
    return out


## Removes files which another host should manage.
## @param target Target instance.
## @param conf   Return value of read_syncconf().
def clear(target, conf):
    global opts
    
    logger.info('clear: %s)' % target)
    
    removed = []

    # Enumerate files to remove
    for host, snipet in conf.only:
        if host != target.host:
            removed += ['"%s"' % x.strip() for x in find_files(target, snipet).split('\n')]

    logger.debug('removed = %s' % str(removed))

    # Remove files
    if target.is_local():
        run_command(' '.join(['rm'] + removed), opts.dry_run)
    else:
        run_command(' '.join(['ssh', target.host, 'rm'] + removed), opts.dry_run)


## Executes rsync.
## @param src Source of sync.
## @param dest Destination of sync.
## @param conf Return value of read_syncconf().
def rsync(src, dest, conf):
    global opts

    logger.info('rsync: %s -> %s)' % (src, dest))
    assert(src.is_local() or dest.is_local())

    ignored = read_syncignore(src) + list(conf.ignore)

    for host, snipet in conf.only:
        if host == src.host:
            ignored.append(snipet)
            
    logger.debug('ignored = %s' % str(ignored))
    logger.debug('dry-run = %s' % opts.dry_run)

    cmd = ' '.join(
        ['rsync', '-ahvz', '--update'] +
        (['--dry-run'] if opts.dry_run else []) +
        ['--exclude="%s"' % e for e in ignored] +
        [str(src), str(dest)])

    run_command(cmd, args.coding)


## Main procedure.
## Reads command line and executes rsync in the mode specified.
def main():
    global opts

    conf = read_syncconf('./.sync.conf')

    src = Target.str2target(opts.src)
    dests = [Target.str2target(d) for d in opts.dests]

    logger.debug('src = %s' % (src))
    logger.debug('dests = [%s]' % ', '.join(map(str, dests)))

    assert(src.is_local())
    assert(not any(Target.is_local, dests)) # dests are remotes

    # [sync] remotes -> local
    for dest in dests:
        rsync(src, dest)
        
    # [sync] local -> remotes
    for dest in dests:
        rsync(dest, src)

    # remove redundant files
    for t in [src] + dests:
        clear(t, conf)
    

if __name__=='__main__':
    main()
