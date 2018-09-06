#!/usr/bin/env python

# Usage:
# tidy.py --scan <scan dir> [-o <filename>] [-v]
#
#   Will scan `scan dir` and build a database of file checksums.
#
#       -o <filename>   write database to `filename` (optional, defaults to
#                       name of scan dir plus '.cksum')
#       -v              print names, sizes, and checksums of files checked
#
# -- OR --
#
# tidy.py --prune <prune dir> -i <filename> [-n] [-v]
#
#   Will scan `prune dir` for files matching the checksum of files found during
#   a previous '--scan' run, and delete them.
#
#       -i <filename>   use `filename` as database of checksums to test against
#       -n              dry run; do not delete files
#       -v              print names, sizes, and checksums of files checked

import argparse
import glob
import progressbar
import pickle
import os
import sys
from humanize import naturalsize
from subprocess import run


def cksum(fname):
    ret = run(['cksum', fname], capture_output=True)
    ck, size, *_ = ret.stdout.decode().strip().split()
    return (int(ck), int(size), fname)


def find_files(path):
    """Find all files at and below path.

    Returns list of (name, size) tuples.

    Do not traverse links."""
    allfiles = progressbar.progressbar(
        glob.iglob(path + '/**', recursive=True),
        widgets=['Counting files: ', progressbar.AnimatedMarker()])
    return [(f, os.path.getsize(f)) for f in allfiles if os.path.isfile(f)]


def calc_cksums(files, verbose):
    """Calculate checksums for files in `files`.

    Returns a (cksums, duplicates) tuple. `cksums` is a dictionary keyed with
    a checksum and having a (size, filename) tuple referencing the first file
    with that checksum as values. `duplicates` is a list of (checksum, filename)
    hashes for all files for which a checksum is already present in the
    `cksum` dictionary (i.e. all duplicate files)."""
    filehash = {}
    duplicates = []

    # Calculate checksum for each file and put in dictionary
    bar = progressbar.ProgressBar(redirect_stdout=True)
    for f, sz in bar(files):
        if verbose:
            print(f'{f} ({naturalsize(sz, binary=True)})', flush=True, end='')
        ck, size, filename = cksum(f)
        if verbose:
            print(f' -> {ck}', flush=True, end='')
        if ck in filehash:
            duplicates.append((ck, size, filename))
            if verbose:
                print(' (DUPLICATE)')
        else:
            filehash[ck] = (size, filename)
            if verbose:
                print('')
    return (filehash, duplicates)


def scan_files(path, verbose):
    # Get list of files
    files = find_files(path)
    totalsize = sum([sz for _, sz in files])
    print(f'Found {len(files)} files in "{path}" (' +
        f'{naturalsize(totalsize, binary=True)}).')

    # Calculate checksums
    filehash, duplicates = calc_cksums(files, verbose=verbose)
    uniquesize = sum([sz for sz, _ in filehash.values()])
    dupsize = sum([sz for _a, sz, _b in duplicates])
    print(f'Found {len(filehash)} unique files ({naturalsize(uniquesize, binary=True)}) and {len(duplicates)} duplicates ({naturalsize(dupsize, binary=True)}).')

    return filehash


def write_cksums(filehash, dbfile):
    if os.path.exists(dbfile):
        overwrite = input(f'{dbfile} exists -- overwrite (y/n)? ').lower()
        if overwrite != 'y':
            return

    with open(dbfile, 'wb') as fd:
        print(f'Writing {len(filehash)} checksums to {dbfile}.')
        pickle.dump(filehash, fd)

def read_cksums(dbfile):
    with open(dbfile, 'rb') as fd:
        filehash = pickle.load(fd)
        print(f'Read {len(filehash)} checksums from {dbfile}.')
    return filehash



def prune_files(path, filehash, dry, verbose):
    """Remove files from `path` if they're already in `filehash`.

    Args:
        path (str): Path to prune
        filehash (dict): Dictionary of checksums and files
        dry (bool): Dry run (don't delete)
        verbose (bool): Be verbose while working
    """
    # Make sure this is really what we want
    if not dry:
        go_ahead = input(f'Continue pruning files in {path} (y/n)? ').lower()
        if go_ahead != 'y':
            return
        really_go_ahead = input(f'This will irrevocably delete files. Are you sure (y/n)? ').lower()
        if really_go_ahead != 'y':
            return

    # Get a list of files in `path`
    files = find_files(path)
    totalsize = sum([sz for _, sz in files])
    print(f'Found {len(files)} files in "{path}" (' +
        f'{naturalsize(totalsize, binary=True)}).') 

    # Check files against `filehash`
    delcount = 0
    delsz = 0
    bar = progressbar.ProgressBar(redirect_stdout=True)
    for f, sz in bar(files):
        if verbose:
            print(f'{f} ({naturalsize(sz, binary=True)})', flush=True, end='')
        ck, size, filename = cksum(f)
        if verbose:
            print(f' -> {ck}', end='')
        if ck in filehash:
            if sz == filehash[ck][0]:
                if not dry:
                    os.remove(f)
                    if verbose:
                        print(f' (DELETED)')
                else:
                    if verbose:
                        print(f' (WOULD DELETE)')
                delcount += 1
                delsz += sz
                # TODO: include delcount and delsz in progress bar!
            else:
                if verbose:
                    print(f' (SIZES DO NOT MATCH, NOT DELETED)')
        else:
            if verbose:
                print('')
    if dry:
        print(f'Found {delcount} files to prune ({naturalsize(delsz, binary=True)}).')
    else:
        print(f'Deleted {delcount} files ({naturalsize(delsz, binary=True)}).')

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--scan', help='directory to scan')
    parser.add_argument('--prune', help='directory to prune')
    parser.add_argument('-f', '--file', help='checksum file')
    parser.add_argument('-v', '--verbose', help='be verbose', action='store_true')
    parser.add_argument('-n', '--dry', help='dry run', action='store_true')

    args = parser.parse_args()

    scanpath = args.scan
    prunepath = args.prune
    dbfile = args.file

    if not (scanpath or (dbfile and prunepath)):
        print('Nothing useful to do.')
        sys.exit(1)

    if scanpath:
        filehash = scan_files(scanpath, args.verbose)
        if dbfile:
            # write filehash to dbfile
            write_cksums(filehash, dbfile)
    elif dbfile:
        # read filehash from dbfile
        filehash = read_cksums(dbfile)
    if prunepath:
        # prune files based on filehash
        prune_files(prunepath, filehash, args.dry, args.verbose)

    