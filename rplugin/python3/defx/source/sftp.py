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
        self.path_head: str = ''

        self.vars = {
            'root': None,
        }

    def init_client(self, hostname, username) -> None:
        transport = Transport((hostname))
        rsa_private_key = RSAKey.from_private_key_file(KEY_PATH)
        transport.connect(username=username, pkey=rsa_private_key)
        self.client = SFTPClient.from_transport(transport)

    def get_root_candidate(
            self, context: Context, path: Path
    ) -> typing.Dict[str, typing.Any]:
        self.vim.call('defx#util#print_message', str(path))
        path_str = self._parse_arg(str(path))
        path = SFTPPath(self.client, path_str)
        word = str(path)
        self.vim.call('defx#util#print_message', str(path))
        if word[-1:] != '/':
            word += '/'
        if self.vars['root']:
            word = self.vim.call(self.vars['root'], str(path))
        word = word.replace('\n', '\\n')
        return {
            'word': word,
            'is_directory': True,
            'action__path': path,
        }

    def gather_candidates(
            self, context: Context, path: Path
    ) -> typing.List[typing.Dict[str, typing.Any]]:
        path_str = self._parse_arg(str(path))
        path = SFTPPath(self.client, path_str)

        candidates = []
        for f in path.iterdir():
            candidates.append({
                'word': f.name,
                'is_directory': f.is_dir(),
                'action__path': f,
            })
        return candidates

    def _parse_arg(self, path: str) -> str:
        head, rmt_path = SFTPPath.parse_path(path)
        if head is None:
            return path
        m = re.match('//(.+)@(.+)', head)  # include username?
        if m:
            username, hostname = m.groups()
        else:
            hostname = re.match('//(.+)', head).groups()[0]
            username = ''
        if (username != self.username or
                hostname != self.hostname):
            # TODO: error handling(cannot connect)
            self.init_client(hostname, username)
            self.username = username
            self.hostname = hostname
        if rmt_path == '':
            rmt_path = '.'
        return self.client.normalize(rmt_path)
