#!/usr/bin/env python

import glob
import progressbar
import os
import sys
import humanize
from subprocess import run


def cksum(fname):
    ret = run(['cksum', fname], capture_output=True)
    ck, size, *_ = ret.stdout.decode().strip().split()
    return (ck, size, fname)


def find_files(path):
    """Find all files at and below path.

    Returns list of (name, size) tuples.

    Do not traverse links."""
    allfiles = progressbar.progressbar(glob.iglob(path + '/**', recursive=True),
        widgets=['Counting files: ', progressbar.AnimatedMarker()])
    return [(f, os.path.getsize(f)) for f in allfiles if os.path.isfile(f)]


if __name__ == '__main__':
    path = sys.argv[1]
    files = find_files(path)
    totalsize = sum([sz for _, sz in files])
    print(f'Found {len(files)} files in "{path}", with a total size of {humanize.naturalsize(totalsize, binary=True)}')

    filehash = {}
    duplicates = []
    # Calculate checksum for each file and put in dictionary
    bar = progressbar.ProgressBar(redirect_stdout=True)
    for f, sz in bar(files):
        print(f'{f} ({humanize.naturalsize(os.path.getsize(f), binary=True)})', flush=True)
        ck, size, filename = cksum(f)
        if ck in filehash:
#            print(f'Duplicate: "{f}" and "{filehash[ck][2]}"')
            duplicates.append((ck, size, filename))
        else:
            filehash[ck] = (size, filename)

    print(f'Found {len(filehash)} unique files ({len(duplicates)} duplicates).')
    