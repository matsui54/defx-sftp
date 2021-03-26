from defx.util import error
from defx.context import Context
from defx.base.source import Base
from paramiko import Transport, SFTPClient, RSAKey
import re
from pathlib import Path
import site
import typing
from pynvim import Nvim

site.addsitedir(str(Path(__file__).parent.parent))
from sftp.sftp_path import SFTPPath


KEY_PATH = str(Path.home().joinpath('.ssh/id_rsa'))


class Source(Base):
    def __init__(self, vim: Nvim) -> None:
        super().__init__(vim)
        self.name = 'sftp'

        from kind.sftp import Kind
        self.kind: Kind = Kind(self.vim)

        self.client: SFTPClient = None
        self.username: str = ''
        self.hostname: str = ''

    def init_client(self, hostname, username) -> None:
        transport = Transport((hostname))
        rsa_private_key = RSAKey.from_private_key_file(KEY_PATH)
        transport.connect(username=username, pkey=rsa_private_key)
        self.client = SFTPClient.from_transport(transport)

    def get_root_candidate(
            self, context: Context, path: Path
    ) -> typing.Dict[str, typing.Any]:
        path = str(path)
        self._parse_arg(path)
        path = SFTPPath(self.client, path)

        self.vim.call('defx#util#print_message', str(path))
        return {
            'word': path.fullpath,
            'is_directory': True,
            'action__path': path,
        }

    def gather_candidates(
            self, context: Context, path: Path
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        path = str(path)
        self._parse_arg(path)
        path = SFTPPath(self.client, path)

        candidates = []
        for f in path.iterdir():
            candidates.append({
                'word': f.stat.filename,
                'is_directory': f.is_dir(),
                'action__path': f,
            })
        return candidates

    def _parse_arg(self, path: str) -> None:
        m = re.search('//(.+)@([^/]+)', path)
        if m:
            username, hostname = m.groups()
            if (username != self.username or
                    hostname != self.hostname):
                self.init_client(hostname, username)
                self.username = username
                self.hostname = hostname
