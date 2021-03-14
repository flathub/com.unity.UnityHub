#!/usr/bin/env python3

from xml.etree import ElementTree

import base64
import os
import subprocess
import sys

EULA_ACCEPT = '/var/data/eula-accept'


def to_base64(s):
    return base64.b64encode(s.encode('ascii')).decode('ascii')


def replace_pref(root, pref, value):
    element = root.find(f'*[@name="{pref}"]')
    if element is None:
        element = ElementTree.SubElement(root, 'pref', {
            'type': 'string',
            'name': pref
        })

    if element.text != value:
        element.text = value
        return True
    else:
        return False


def main():
    if not os.path.exists(EULA_ACCEPT):
        ret = subprocess.run([
            'zenity', '--text-info', '--title=Unity Hub',
            '--filename=/app/extra/license.txt', '--ok-label=Agree',
            '--cancel-label=Disagree'
        ])
        if ret.returncode:
            sys.exit()

        with open(EULA_ACCEPT, 'w'):
            pass

    prefs = os.path.join(os.environ['XDG_DATA_HOME'], 'unity3d', 'prefs')
    if not os.path.exists(prefs):
        os.makedirs(os.path.dirname(prefs), exist_ok=True)

        with open(prefs, 'w') as fp:
            print('<unity_prefs version_major="1" version_minor="1">', file=fp)
            print('</unity_prefs>', file=fp)

    b64_editor = to_base64('/app/bin/code')
    b64_args = to_base64('$(File)')

    tree = ElementTree.parse(prefs)
    root = tree.getroot()

    was_changed = any([
        replace_pref(root, 'kScriptsDefaultApp', b64_editor),
        replace_pref(root, 'kScriptEditorArgs', b64_args),
        replace_pref(root, 'kScriptEditorArgs/app/bin/code', b64_args),
    ])

    if was_changed:
        tmp = prefs + '.tmp'
        with open(tmp, 'wb') as fp:
            tree.write(fp)

        os.rename(tmp, prefs)

    env = os.environ.copy()
    env['UNITY_DATADIR'] = env['XDG_DATA_HOME']
    env['TMPDIR'] = f'{env["XDG_CACHE_HOME"]}/tmp'

    os.execvpe('zypak-wrapper',
               ['zypak-wrapper', '/app/extra/unityhub-bin', *sys.argv[1:]],
               env)


if __name__ == '__main__':
    main()
