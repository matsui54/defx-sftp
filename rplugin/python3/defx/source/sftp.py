from pynvim import Nvim
import typing
import site
from pathlib import Path
import re
from paramiko import Transport, SFTPClient, RSAKey

from defx.base.source import Base
from defx.context import Context
from defx.util import error

site.addsitedir(str(Path(__file__).parent.parent))
from source.sftp_path import SFTPPath

KEY_PATH = str(Path.home().joinpath('.ssh/id_rsa'))


class Source(Base):
    def __init__(self, vim: Nvim) -> None:
        super().__init__(vim)
        self.name = 'sftp'

        from kind.sftp import Kind
        self.kind: Kind = Kind(self.vim)

        self.client: SFTPClient = None

    def init_client(self, path: str):
        (hostname, username) = self._parse_arg(path)
        transport = Transport((hostname))
        rsa_private_key = RSAKey.from_private_key_file(KEY_PATH)
        transport.connect(username=username, pkey=rsa_private_key)
        self.client = SFTPClient.from_transport(transport)

    def get_root_candidate(
            self, context: Context, path: Path
    ) -> typing.Dict[str, typing.Any]:
        self.vim.call('defx#util#print_message', str(path))
        path = str(path)
        if not self.client:
            self.init_client(path)
            path = '.'

        return {
            'word': 'sftp://' + str(path),
            'is_directory': True,
            'action__path': path,
        }

    def gather_candidates(
            self, context: Context, path: Path
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        self.vim.call('defx#util#print_message', str(path))
        path = str(path)
        if not self.client:
            self.init_client(path)
            path = ''
        path = '.'

        self.vim.call('defx#util#print_message', str(path))
        candidates = []
        for f in path.iterdir():
            candidates.append({
                'word': f.name,
                'is_directory': f.is_dir(),
                'action__path': f,
            })
        return candidates

    def _parse_arg(self, path: str) -> typing.List[str]:
        username, hostname = re.search('\/\/(.+)@(.+)', path).groups()
        self.vim.call('defx#util#print_message', str(username + hostname))
        return (hostname, username)

    def _get_path(self, path: Path) -> SFTPPath:
        is_root = (str(path) == self.vim.call('getcwd'))
        if is_root:
            path = SFTPPath(self.client, '/')
        else:
            path = SFTPPath(self.client, str(path))
        return path
