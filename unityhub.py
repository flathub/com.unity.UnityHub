#!/usr/bin/env python3

from xml.etree import ElementTree

import base64
import os
import subprocess
import sys


def to_base64(s):
    return base64.b64encode(s.encode('ascii')).decode('ascii')


def edit_pref(root, pref, type, func):
    element = root.find(f'*[@name="{pref}"]')
    if element is None:
        element = ElementTree.SubElement(root, 'pref', {
            'type': type,
            'name': pref
        })

    new_value = func(element.text)
    if element.text != new_value:
        element.text = new_value
        return True
    else:
        return False

def replace_string_pref(root, pref, value):
    return edit_pref(root, pref, 'string', lambda _: value)


def main():
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
        replace_string_pref(root, 'kScriptsDefaultApp', b64_editor),
        replace_string_pref(root, 'kScriptEditorArgs', b64_args),
        replace_string_pref(root, 'kScriptEditorArgs/app/bin/code', b64_args),
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
               ['zypak-wrapper', '/app/extra/unityhub-bin', '--', *sys.argv[1:]],
               env)


if __name__ == '__main__':
    main()
