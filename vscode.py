#!/usr/bin/env python3

# There are two things we want as we start Visual Studio Code:
# - If VS Code, or one of the SDK extensions required to be able to work with Unity scripts,
#   is not installed, then a message should be displayed to the user, and they should be
#   redirected to the installation.
# - In order for debugging to work, the Unity Debugger VS Code extension needs to be able
#   to find Unity Editor's PID.

# The latter step is what the majority of this file is dedicated to. The Unity extension will
# try to connect to the socket found by taking the Unity PID modulo 1000 and adding 56000

# In order for debugging to work, the Unity VS Code extension needs to be able to find
# Unity Editor's PID. Furthermore, it should be relatively unique to avoid conflicts.

# The socket to connect to is found by taking the Unity PID modulo 1000 and adding 56000:
# https://github.com/Unity-Technologies/MonoDevelop.Debugger.Soft.Unity/blob/usedForVSCodeRelease/UnityProcessDiscovery.cs#L93

# However, given that VS Code and Unity are in two different sandboxes, they obviously can't
# find each others PIDs. Therefore, we need to bridge the VS Code sandbox to the Unity sandbox.
# This is done by finding the first empty socket starting at 56003 at using that to determine
# a desired PID for a process named "Unity". From inside the VS Code Flatpak, a sleep process
# is run named "Unity", with the PID of [our socket] - 56000. Therefore, the VS Code extension
# will find our process and add 56000 to find the socket we want. This script will set up an
# asyncio-powered forwarding to send it to the *actual* Unity process.

# Why 56003? Inside the VS Code sandbox, bwrap will be PID 1 and bash PID 2, so the lowest PID
# the fake Unity sleep process can start as will be 3.

# This script also uses PEP 484 type annotations to try and avoid awkward glitches slipping in.
# No runtime overhead is incurred, as PEP 563 deferred annotations are used (thanks to the
# future import), and the typing import is guarded by an 'if False'.


from __future__ import annotations

from typing import *

import asyncio
import errno
import itertools
import os
import subprocess
import sys
import traceback
import webbrowser


VSCODE_SCRIPT = r'''
arg_start_index=$1
package=$2
setting=$3
dotnet=$4
mono=$5
target_pid="${@: arg_start_index:1}"
shift

code=`which $package 2>/dev/null | head -1`
setting=$XDG_CONFIG_HOME/$setting

cp /usr/bin/sleep /run/Unity

for (( i=$$; i < $target_pid; i++ )); do /usr/bin/true; done
/run/Unity infinity &

[[ -d /usr/lib/sdk/$dotnet ]] && export PATH="/usr/lib/sdk/$dotnet/bin:$PATH"
[[ -d /usr/lib/sdk/$mono ]] && export PATH="/usr/lib/sdk/$mono/bin:$PATH"

# Note: don't do grep -q, code --list-extensions doesn't like SIGPIPE
if $code --list-extensions | grep ms-dotnettools.csharp >/dev/null &&
  grep -qs '"dotnet\.server\.useOmnisharp"\s*:\s*true' $user_setting &&
  ! grep -qs '"omnisharp\.useModernNet"\s*:\s*false' $user_setting; then
  zenity --warning --no-wrap --title='omnisharp.useModernNet should be false' \
    --text="omnisharp.useModernNet should be set to false to avoid errors when started
from within Unity Editor."
fi

$code "${@: arg_start_index}"
while ps -A | grep -q code; do sleep 5; done
kill $(jobs -p)
'''


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

    async def get_sdk(self, ref: str) -> Optional[str]:
        p = await self('info', '--show-sdk', ref, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL)
        return p.stdout.strip() if not p.returncode else None

    async def exists(self, ref: str) -> bool:
        result = await self('info', ref, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return not result.returncode

    async def get_extension(self, sdk_ext: str, arch: str, branch: str) -> str:
        p = await self('list', '--runtime', '--columns=ref', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if p.returncode:
            return None
        # it seems that `flatpak list` command return the list in ascending order, which mean oldest to latest, but I maybe wrong
        # loop through each line in reversed order to get latest version of the sdk extension in case we found multiple installed extensions
        for sdk in p.stdout.strip().splitlines()[::-1]:
            if sdk.find(sdk_ext) != -1 and sdk.find(arch) != -1 and sdk.find(branch) != -1:
                ref_parts = sdk.split('/')[0].split('.')
                # return only extension name, because we need it in the bash script
                return ref_parts[-1]
        return None

    async def search_remote_extension_ref(self, sdk_ext: str, arch: str, branch: str) -> str:
        p = await self('search', f'--arch={arch}', '--columns=application,branch', sdk_ext, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if p.returncode:
            return None
        for sdk in p.stdout.strip().splitlines():
            if sdk.find(branch) != -1:
                ref = sdk.split('\t')[0]
                return ref
        return None


async def not_installed(*, ref: str, title: str, text: str, branch: str,
                        available_on_web: bool) -> None:
    if ref and (HAS_GNOME_SOFTWARE or available_on_web):
        zenity = await aio_run('zenity', '--no-wrap', '--question', f'--title={title}', f'--text={text}')
        if not zenity.returncode:
            if HAS_GNOME_SOFTWARE:
                await aio_run('gdbus', 'call', '-e', '-d', 'org.gnome.Software', '-o',
                              '/org/gnome/Software', '-m', 'org.gtk.Actions.Activate', 'search',
                              f'[<"{ref}">, <"{branch}">]', '[]')
            else:
                webbrowser.open(f'https://flathub.org/apps/search/{ref}')

            sys.exit()
    else:
        await aio_run('zenity', '--no-wrap', '--warning', f'--title={title}', f'--text={text}')


class UnityBridge(asyncio.Protocol):
    """UnityBridge represents the connection from this script to Unity."""

    def __init__(self, vscode_transport: asyncio.BaseTransport) -> None:
        assert isinstance(vscode_transport, asyncio.Transport)
        self.vscode_transport = vscode_transport

    def data_received(self, data: bytes) -> None:
        self.vscode_transport.write(data)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self.vscode_transport.close()


class VscodeBridge(asyncio.Protocol):
    """VscodeBridge represents the connection from VS Code to this script."""

    def __init__(self, unity_port: int) -> None:
        self.unity_port = unity_port
        self.unity_transport: Optional[asyncio.Transport] = None
        self.buffer = bytearray()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        asyncio.create_task(self.try_connect(transport))

    async def try_connect(self, transport: asyncio.BaseTransport) -> None:
        loop = asyncio.get_running_loop()

        while True:
            # Try connecting to Unity.
            try:
                unity_transport: asyncio.BaseTransport
                unity_transport, _ = await loop.create_connection(  # type: ignore
                    lambda: UnityBridge(transport), 'localhost', self.unity_port)
            except OSError:
                # Likely a connection failure.
                print('Error connecting to Unity, will retry after 5s...')
                traceback.print_exc()
                await asyncio.sleep(5)
            else:
                assert isinstance(unity_transport, asyncio.Transport)
                self.unity_transport = unity_transport

                if self.buffer:
                    unity_transport.write(self.buffer)
                    self.buffer.clear()

                break

    def data_received(self, data: bytes) -> None:
        if self.unity_transport is not None:
            self.unity_transport.write(data)
        else:
            self.buffer.extend(data)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if self.unity_transport is not None:
            self.unity_transport.close()
            self.unity_transport = None


class Editor:
    def __init__(self, ref, package_name, user_setting):
        self.ref = ref
        self.package_name = package_name
        self.user_setting = user_setting

    def get_bash_arguments(self):
        result = []
        result.append(self.package_name)
        result.append(self.user_setting)
        return result

# global variables
HAS_GNOME_SOFTWARE = False
EDITORS: List[Editor] = []
EDITORS.append(Editor('com.visualstudio.code', 'code', 'Code/User/settings.json'))
EDITORS.append(Editor('com.visualstudio.code-oss', 'code-oss', 'Code - OSS/User/settings.json'))
EDITORS.append(Editor('com.vscodium.codium', 'com.vscodium.codium', 'Visual Studio Code/User/settings.json'))

async def forward_unity_socket(unity_port: int) -> Tuple[int, asyncio.AbstractServer]:
    loop = asyncio.get_running_loop()

    for target_pid in itertools.count(3):
        target_port = 56000 + target_pid

        try:
            server: asyncio.AbstractServer
            server = await loop.create_server(lambda: VscodeBridge(unity_port),  # type: ignore
                                              'localhost', target_port)
        except OSError as ex:
            if ex.errno == errno.EADDRINUSE:
                continue
            else:
                raise
        else:
            return target_pid, server

    assert False


async def spawn_vscode(flatpak: Flatpak, editor: Editor, sdk: str, unity_port: int) -> NoReturn:
    sdk_info = sdk.split('/')
    arch = sdk_info[1]
    branch = sdk_info[2]

    args: List[str] = []
    # the first element will mark the start index of the arguments that unity pass to the code editor
    # it will be equal to the size of our list plus 1, because bash script arguments index start at 1
    args.append("0")
    args.extend(editor.get_bash_arguments())
    for sdk_ext in 'org.freedesktop.Sdk.Extension.dotnet', 'org.freedesktop.Sdk.Extension.mono':
        ext = await flatpak.get_extension(sdk_ext, arch, branch)
        if ext:
            args.append(ext)
        else:
            # append anything just to have enough arguments, Idk if we need it, but I don't wanna handle complicated logic in bash script
            args.append(sdk_ext)

            # couldn't find required extensions, search for it on remotes and inform user
            ref_to_search = await flatpak.search_remote_extension_ref(sdk_ext, arch, branch)
            if ref_to_search:
                if HAS_GNOME_SOFTWARE:
                    additional_text = 'Would you like to install it?'
                else:
                    additional_text = 'Please install it from Flathub.'
            else:
                ref_to_search = sdk_ext
                additional_text = f'But we couldn\'t find anything that is compatible with your *{editor.ref}* code editor.'\
                    ' Please consider downgrade your code editor.'

            await not_installed(ref=ref_to_search,
                                title='SDK extensions are required',
                                text=f'The *{ref_to_search}* SDK extensions (arch: *{arch}*, branch: *{branch}*) are required for the Unity'
                                    f' debugger to work.\n{additional_text}',
                                branch=branch, available_on_web=False)

    args[0] = str(len(args) + 1)

    target_pid, transport = await forward_unity_socket(unity_port)
    res = await flatpak('run', '--command=bash', editor.ref, '-c', VSCODE_SCRIPT, '--', *args,
                        str(target_pid), *sys.argv[1:])
    transport.close()
    sys.exit(res.returncode)


async def main() -> None:
    # check gnome software only once to avoid unnecessary repeated check afterward
    gnome_software_check = await aio_run('gdbus', 'introspect', '-e', '-d', 'org.gnome.Software',
                                    '-o', '/org/gnome/Software', stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
    global HAS_GNOME_SOFTWARE
    HAS_GNOME_SOFTWARE = not gnome_software_check.returncode

    unity_pid = os.getppid()
    unity_port = unity_pid % 1000 + 56000

    flatpak = Flatpak()

    for editor in EDITORS:
        sdk = await flatpak.get_sdk(editor.ref)
        if sdk is not None:
            await spawn_vscode(flatpak, editor, sdk, unity_port)

    await not_installed(ref='com.visualstudio.code', title='Visual Studio Code is required',
                        text='Visual Studio Code is required to edit Unity scripts.', branch='',
                        available_on_web=True)


if __name__ == '__main__':
    asyncio.run(main())
