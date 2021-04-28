# ============================================================================
# FILE: file.py
# AUTHOR: Shougo Matsushita <Shougo.Matsu at gmail.com>
# License: MIT license
# ============================================================================

from pathlib import Path
from pynvim import Nvim
import copy
import importlib
import mimetypes
import shlex
import shutil
import subprocess
import re
import time
import typing
import site
from paramiko import SFTPFile, SFTPClient

from defx.action import ActionAttr
from defx.action import ActionTable
from defx.kind.file import Kind as Base
from defx.clipboard import ClipboardAction
from defx.context import Context
from defx.defx import Defx
from defx.util import cd, cwd_input, confirm, error, Candidate
from defx.util import readable, fnamemodify
from defx.view import View

site.addsitedir(str(Path(__file__).parent.parent))
from sftp.sftp_path import SFTPPath

_action_table: typing.Dict[str, ActionTable] = {}

ACTION_FUNC = typing.Callable[[View, Defx, Context], None]


def action(name: str, attr: ActionAttr = ActionAttr.NONE
           ) -> typing.Callable[[ACTION_FUNC], ACTION_FUNC]:
    def wrapper(func: ACTION_FUNC) -> ACTION_FUNC:
        _action_table[name] = ActionTable(func=func, attr=attr)

        def inner_wrapper(view: View, defx: Defx, context: Context) -> None:
            return func(view, defx, context)
        return inner_wrapper
    return wrapper


class Kind(Base):

    def __init__(self, vim: Nvim) -> None:
        self.vim = vim
        self.name = 'sftp'

    def get_actions(self) -> typing.Dict[str, ActionTable]:
        actions = copy.copy(super().get_actions())
        actions.update(_action_table)
        return actions


def check_overwrite(view: View, dest: SFTPPath, src: SFTPPath) -> str:
    if not src.exists() or not dest.exists():
        return ''

    s_stat = src.stat()
    s_mtime = s_stat.st_mtime
    view.print_msg(f' src: {src} {s_stat.st_size} bytes')
    view.print_msg(f'      {time.strftime("%c", time.localtime(s_mtime))}')
    d_stat = dest.stat()
    d_mtime = d_stat.st_mtime
    view.print_msg(f'dest: {dest} {d_stat.st_size} bytes')
    view.print_msg(f'      {time.strftime("%c", time.localtime(d_mtime))}')

    choice: int = view._vim.call('defx#util#confirm',
                                 f'{dest} already exists.  Overwrite?',
                                 '&Force\n&No\n&Rename\n&Time\n&Underbar', 0)
    ret = ''
    if choice == 1:
        ret = str(dest)
    elif choice == 2:
        ret = ''
    elif choice == 3:
        ret = view._vim.call(
            'defx#util#input',
            f'{src} -> ', str(dest),
            ('dir' if src.is_dir() else 'file'))
    elif choice == 4 and d_mtime < s_mtime:
        ret = str(src)
    elif choice == 5:
        ret = str(dest) + '_'
    return ret


def switch(view: View) -> None:
    windows = [x for x in range(1, view._vim.call('winnr', '$') + 1)
               if view._vim.call('getwinvar', x, '&buftype') == '']

    result = view._vim.call('choosewin#start', windows,
                            {'auto_choose': True, 'hook_enable': False})
    if not result:
        # Open vertical
        view._vim.command('noautocmd rightbelow vnew')


@action(name='check_redraw', attr=ActionAttr.NO_TAGETS)
def _check_redraw(view: View, defx: Defx, context: Context) -> None:
    # slow for remote path
    pass


def copy_recursive(path: SFTPPath, dest: Path, client) -> None:
    ''' copy remote files to the local host '''
    if path.is_file():
        client.get(str(path), str(dest))
    else:
        dest.mkdir(parents=True)
        for f in path.iterdir():
            new_dest = dest.joinpath(f.name)
            copy_recursive(f, new_dest, client)


@action(name='copy')
def _copy(view: View, defx: Defx, context: Context) -> None:
    if not context.targets:
        return

    message = 'Copy to the clipboard: {}'.format(
        str(context.targets[0]['action__path'])
        if len(context.targets) == 1
        else str(len(context.targets)) + ' files')
    view.print_msg(message)

    def copy_to_local(path: str, dest: str):
        client = defx._source.client
        copy_recursive(SFTPPath(client, path), Path(dest), client)

    view._clipboard.action = ClipboardAction.COPY
    view._clipboard.candidates = context.targets
    view._clipboard.source_name = 'sftp'
    view._clipboard.paster = copy_to_local


@action(name='link')
def _link(view: View, defx: Defx, context: Context) -> None:
    if not context.targets:
        return

    message = 'Link to the clipboard: {}'.format(
        str(context.targets[0]['action__path'])
        if len(context.targets) == 1
        else str(len(context.targets)) + ' files')
    view.print_msg(message)

    view._clipboard.action = ClipboardAction.LINK
    view._clipboard.candidates = context.targets
    view._clipboard.source_name = 'sftp'


@action(name='move')
def _move(view: View, defx: Defx, context: Context) -> None:
    if not context.targets:
        return

    message = 'Move to the clipboard: {}'.format(
        str(context.targets[0]['action__path'])
        if len(context.targets) == 1
        else str(len(context.targets)) + ' files')
    view.print_msg(message)
    view._clipboard.action = ClipboardAction.MOVE
    view._clipboard.candidates = context.targets
    view._clipboard.source_name = 'sftp'


@action(name='new_directory')
def _new_directory(view: View, defx: Defx, context: Context) -> None:
    """
    Create a new directory.
    """
    candidate = view.get_cursor_candidate(context.cursor)
    if not candidate:
        return

    if candidate['is_opened_tree'] or candidate['is_root']:
        cwd = str(candidate['action__path'])
    else:
        cwd = str(Path(candidate['action__path']).parent)

    new_filename: str = str(view._vim.call(
        'defx#util#input',
        'Please input a new filename: ', '', 'file'))
    if not new_filename:
        return

    client: SFTPClient = defx._source.client
    filename = SFTPPath(client, cwd).joinpath(new_filename)

    if not filename:
        return
    if filename.exists():
        error(view._vim, f'{filename} already exists')
        return

    filename.mkdir(parents=True)
    view.redraw(True)
    view.search_recursive(filename, defx._index)


@action(name='new_file')
def _new_file(view: View, defx: Defx, context: Context) -> None:
    """
    Create a new file and it's parent directories.
    """
    candidate = view.get_cursor_candidate(context.cursor)
    if not candidate:
        return

    if candidate['is_opened_tree'] or candidate['is_root']:
        cwd = str(candidate['action__path'])
    else:
        cwd = str(Path(candidate['action__path']).parent)

    new_filename: str = str(view._vim.call(
        'defx#util#input',
        'Please input a new filename: ', '', 'file'))
    if not new_filename:
        return

    client: SFTPClient = defx._source.client
    isdir = new_filename[-1] == '/'
    filename = SFTPPath(client, cwd).joinpath(new_filename)

    if not filename:
        return
    if filename.exists():
        error(view._vim, f'{filename} already exists')
        return

    if isdir:
        filename.mkdir(parents=True)
    else:
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.touch()

    view.redraw(True)
    view.search_recursive(filename, defx._index)


@action(name='new_multiple_files')
def _new_multiple_files(view: View, defx: Defx, context: Context) -> None:
    """
    Create multiple files.
    """
    candidate = view.get_cursor_candidate(context.cursor)
    if not candidate:
        return

    if candidate['is_opened_tree'] or candidate['is_root']:
        cwd = str(candidate['action__path'])
    else:
        cwd = str(Path(candidate['action__path']).parent)

    str_filenames: str = view._vim.call(
        'input', 'Please input new filenames: ', '', 'file')

    if not str_filenames:
        return None

    client: SFTPClient = defx._source.client
    for name in shlex.split(str_filenames):
        is_dir = name[-1] == '/'

        filename = SFTPPath(client, cwd).joinpath(name)
        if filename.exists():
            error(view._vim, f'{filename} already exists')
            continue

        if is_dir:
            filename.mkdir(parents=True)
        else:
            if not filename.parent.exists():
                filename.parent.mkdir(parents=True)
            filename.touch()

    view.redraw(True)
    view.search_recursive(filename, defx._index)


def put_recursive(path: Path, dest: SFTPPath, client: SFTPClient) -> None:
    ''' copy local files to the remote host '''
    if path.is_file():
        client.put(str(path), str(dest))
    else:
        dest.mkdir()
        for f in path.iterdir():
            new_dest = dest.joinpath(f.name)
            put_recursive(f, new_dest, client)


@action(name='paste', attr=ActionAttr.NO_TAGETS)
def _paste(view: View, defx: Defx, context: Context) -> None:
    candidate = view.get_cursor_candidate(context.cursor)
    if not candidate:
        return
    client: SFTPClient = defx._source.client

    if candidate['is_opened_tree'] or candidate['is_root']:
        cwd = str(candidate['action__path'])
    else:
        cwd = str(Path(candidate['action__path']).parent)

    action = view._clipboard.action
    dest = None
    for index, candidate in enumerate(view._clipboard.candidates):
        path = candidate['action__path']
        dest = SFTPPath(client, cwd).joinpath(path.name)
        if dest.exists():
            overwrite = check_overwrite(view, dest, path)
            if overwrite == '':
                continue
            dest = SFTPPath(client, overwrite)

        if not path.exists() or path == dest:
            continue

        view.print_msg(
            f'[{index + 1}/{len(view._clipboard.candidates)}] {path}')

        if dest.exists() and action != ClipboardAction.MOVE:
            # Must remove dest before
            if not dest.is_symlink() and dest.is_dir():
                shutil.rmtree(str(dest))
            else:
                dest.unlink()

        if view._clipboard.source_name == 'file':
            if action == ClipboardAction.COPY:
                put_recursive(path, dest, client)
            elif action == ClipboardAction.MOVE:
                pass
            elif action == ClipboardAction.LINK:
                pass
            view._vim.command('redraw')
            continue

        if action == ClipboardAction.COPY:
            if path.is_dir():
                path.copy_recursive(dest)
            else:
                path.copy(dest)
        elif action == ClipboardAction.MOVE:
            path.rename(dest)

            # Check rename
            if not path.is_dir():
                view._vim.call('defx#util#buffer_rename',
                               view._vim.call('bufnr', str(path)), str(dest))
        elif action == ClipboardAction.LINK:
            # Create the symbolic link to dest
            dest.symlink_to(path, target_is_directory=path.is_dir())

        view._vim.command('redraw')
    if action == ClipboardAction.MOVE:
        # Clear clipboard after move
        view._clipboard.candidates = []
    view._vim.command('echo')

    view.redraw(True)
    if dest:
        view.search_recursive(dest, defx._index)


@action(name='remove', attr=ActionAttr.REDRAW)
def _remove(view: View, defx: Defx, context: Context) -> None:
    """
    Delete the file or directory.
    """
    if not context.targets:
        return

    force = context.args[0] == 'force' if context.args else False
    if not force:
        message = 'Are you sure you want to delete {}?'.format(
            str(context.targets[0]['action__path'])
            if len(context.targets) == 1
            else str(len(context.targets)) + ' files')
        if not confirm(view._vim, message):
            return

    for target in context.targets:
        path = target['action__path']

        if path.is_dir():
            path.rmdir_recursive()
        else:
            path.unlink()

        view._vim.call('defx#util#buffer_delete',
                       view._vim.call('bufnr', str(path)))


@action(name='remove_trash', attr=ActionAttr.REDRAW)
def _remove_trash(view: View, defx: Defx, context: Context) -> None:
    view.print_msg('remove_trash is not supported')


@action(name='rename')
def _rename(view: View, defx: Defx, context: Context) -> None:
    """
    Rename the file or directory.
    """

    if len(context.targets) > 1:
        # ex rename
        view._vim.call('defx#exrename#create_buffer',
                       [{'action__path': str(x['action__path'])}
                        for x in context.targets],
                       {'buffer_name': 'defx'})
        return

    client: SFTPClient = defx._source.client
    for target in context.targets:
        old = target['action__path']
        new_filename: str = view._vim.call(
            'input', f'Old name: {old}\nNew name: ', str(old), 'file')
        view._vim.command('redraw')
        if not new_filename:
            return
        new = SFTPPath(client, new_filename)
        if not new or new == old:
            continue
        if str(new).lower() != str(old).lower() and new.exists():
            error(view._vim, f'{new} already exists')
            continue

        if not new.parent.exists():
            new.parent.mkdir(parents=True)
        old.rename(new)

        # Check rename
        # The old is directory, the path may be matched opened file
        if not new.is_dir():
            view._vim.call('defx#util#buffer_rename',
                           view._vim.call('bufnr', str(old)), str(new))

        view.redraw(True)
        view.search_recursive(new, defx._index)
