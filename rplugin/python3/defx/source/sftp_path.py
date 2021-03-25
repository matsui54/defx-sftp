from __future__ import annotations
import typing
from pathlib import PurePosixPath
import stat
import re
from paramiko import SFTPClient, SFTPFile


class SFTPPath(PurePosixPath):
    def __init__(self, sftp: SFTPClient, path: str):
        super.__init__(path)
        self.sftp: SFTPClient = sftp
        self.path: str = path

    def iterdir(self) -> typing.Iterable(SFTPPath):
        for f in self.sftp.listdir(self.path):
            yield SFTPPath(self.sftp, f)

    def is_dir(self) -> bool:
        mode = self.sftp.lstat(self.path).st_mode
        return stat.S_IFMT(mode) == stat.S_IFDIR

    def is_symlink(self) -> bool:
        mode = self.sftp.lstat(self.path).st_mode
        return stat.S_IFMT(mode) == stat.S_IFLNK
