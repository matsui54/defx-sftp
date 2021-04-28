## About
Defx-sftp is a defx source for sftp.
Warning: This plugin is under development.

## Features
- View and operate remote files via SFTP.
- Exchange files between remote and local.

## Requirements
For basic requirements, please follow the [instruction of defx.nvim](https://github.com/Shougo/defx.nvim#requirements).
Additionally, defx-sftp requires [paramiko](http://www.paramiko.org/).
You can install it with pip:

    pip3 install --user paramiko

## Usage
For now, defx-sftp only supports RSA authentication.
Private key path can be specified with `g:defx_sftp#key_path` (default is ~/.ssh/id_rsa).

Remote files can be accessed like this.
``` vim
Defx sftp://user@hostname
```
