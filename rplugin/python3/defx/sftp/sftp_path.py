from __future__ import annotations
import typing
from pathlib import PurePosixPath
import stat
import re
from paramiko import SFTPClient, SFTPFile, SFTPAttributes


def _get_real_path(path):
    m = re.search('//.+@(.*)', path)
    if m:
        m_path = re.search('[^/]*/(.*)', m.groups()[0])
        if m_path:
            return m_path.groups()[0]
        else:
            return '.'
    else:
        return path


class SFTPPath(PurePosixPath):
    def __new__(cls, sftp: SFTPClient, path: str, stat: SFTPAttributes = None):
        self = super().__new__(cls, path)
        self.sftp: SFTPClient = sftp
        # self.path: str = _get_real_path(path)
        self.path: str = path
        self._stat: SFTPAttributes = stat
        return self

    def __eq__(self, other):
        return self.__str__() == str(other)

    def __str__(self):
        return self.path

    def iterdir(self) -> typing.Iterable(SFTPPath):
        for f in self.sftp.listdir_attr(self.path):
            yield self.joinpath(f.filename, f)

    def relative_to(self, other) -> SFTPPath:
        return self

    def joinpath(self, name: str, stat: SFTPAttributes = None):
        new_path = self.path + '/' + name
        return SFTPPath(self.sftp, new_path, stat)

    def exists(self):
        try:
            bool(self.stat())
        except FileNotFoundError:
            return False

    def stat(self) -> SFTPAttributes:
        if self._stat:
            return self._stat
        else:
            return self.sftp.stat(self.path)

    def is_dir(self) -> bool:
        mode = self.stat().st_mode
        return not stat.S_ISREG(mode)

    def is_symlink(self) -> bool:
        mode = self.stat().st_mode
        return stat.S_ISLNK(mode)
