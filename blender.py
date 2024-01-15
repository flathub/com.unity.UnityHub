#!/usr/bin/env python3

# Modified from vscode.py
# Blender only needs to recieve the arguments supplied by Unity
# Rest of the code is to ensure Blender is installed on the host system

from __future__ import annotations

from typing import *

import asyncio
import subprocess
import sys
import webbrowser

async def aio_run(*args: str, **kw) -> subprocess.CompletedProcess:
    proc = await asyncio.create_subprocess_exec(*args, **kw)
    stdout, stderr = await proc.communicate()
    stdout_res: Optional[str] = None
    stderr_res: Optional[str] = None

    if stdout is not None:
        stdout_res = stdout.decode()
    if stderr is not None:
        stderr_res = stderr.decode()

    assert proc.returncode is not None
    return subprocess.CompletedProcess(args=args, stdout=stdout_res, stderr=stderr_res,
                                       returncode=proc.returncode)


class Flatpak:
    def __init__(self) -> None:
        pass

    async def __call__(self, *args, **kw) -> subprocess.CompletedProcess:
        return await aio_run('flatpak-spawn', '--host', 'flatpak', *args, **kw)

    async def exists(self, ref: str) -> bool:
        result = await self('info', ref, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return not result.returncode


async def not_installed(*, ref: str, title: str, text: str, branch: str,
                        available_on_web: bool) -> None:
    software_check = await aio_run('gdbus', 'introspect', '-e', '-d', 'org.gnome.Software',
                                   '-o', '/org/gnome/Software', stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    has_software = not software_check.returncode

    if has_software or available_on_web:
        zenity = await aio_run('zenity', '--no-wrap', '--question', f'--title={title}',
                               f'--text={text}\nWould you like to install it?')
        if not zenity.returncode:
            if has_software:
                await aio_run('gdbus', 'call', '-e', '-d', 'org.gnome.Software', '-o',
                              '/org/gnome/Software', '-m', 'org.gtk.Actions.Activate', 'search',
                              f'[<"{ref}">, <"{branch}">]', '[]')
            else:
                webbrowser.open(f'https://flathub.org/apps/search/{ref}')

            sys.exit()
    else:
        await aio_run('zenity', '--no-wrap', '--warning', f'--title={title}',
                      f'--text={text}\nPlease install it from Flathub.')
        

async def spawn_blender(flatpak: Flatpak, ref: str) -> NoReturn:
    res = await flatpak('run', '--command=blender', ref, *sys.argv[1:])
    sys.exit(res.returncode)


async def main() -> None:
    flatpak = Flatpak()

    ref = 'org.blender.Blender'
    installed = await flatpak.exists(ref)
    if installed:
        await spawn_blender(flatpak, ref)

    await not_installed(ref='org.blender.Blender', title='Blender is required',
                        text='Blender is required to import Blender model.', branch='',
                        available_on_web=True)


if __name__ == '__main__':
    asyncio.run(main())
