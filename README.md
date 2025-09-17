# UnityHub Flatpak

This is a Flatpak for [Unity Hub](https://unity.com/unity-hub), a manager for Unity projects and installations.

## Forwarding File Open Requests

The Flatpak includes a `code` script in `/app/bin/code` that will perform a few checks and try to forward requests to
open files in your editor from Unity with VSCode. This works in tandem with the Unity
[visualstudio](https://docs.unity3d.com/Packages/com.unity.ide.visualstudio@2.0/) package and should thus automatically
be picked up by Unity.

### Using Arbitrary Editors

Because Flatpak is a sandbox, by default UnityHub isn't able to access other applications installed through Flatpak or
your host. Sometimes however you may wish to use another editor than VSCode with Unity in this Flatpak. **In the Unity
preferences you can select an additional script or executable** for this. By creating such a script in e.g.
`~/.var/app/com.unity.UnityHub/.config/unity3d/your-editor-script` and using e.g. `xdg-open`, you could forward a file
open request to the host.

You can follow what your script is printing (or if it is failing) in the Unity `Editor.log` as you request to open files
from Unity.

#### Faking VSCode To Get C# Project Generation

The downside of the above is that using another editor not recognized as being VSCode will make you lose C# project
generation as that seems to be tied together in the Unity package. **You can work around this by calling your custom
script `code` ** and selecting it as executable. This will make Unity automatically select the VSCode option again,
but it will still be using your script. This works at least in Unity 6000.1.2f1 and version 2.0.23 of the editor package.

Take note that pretending to be a VSCode executable will also make Unity pass different options. If you make a Bash
script, for example, the options passed in `$@` are e.g.
`/home/user/your/project/folder -g /home/user/your/project/folder/Assets/Scripts/YourScript.cs:50:10`, so you may
need to strip the line and character numbers if your chosen editor doesn't support them.

#### Zed Example

To give a concrete example of the above and have C# project generation (for e.g. the DotRush language server) and
to be able to open files from Unity in Zed, you could use the special `zed://file` URI to open files. For example,
in `~/.var/app/com.unity.UnityHub/.config/unity3d/code`:

```bash
#!/bin/bash
#
uri=$(python -c 'import sys,pathlib; print(pathlib.Path(sys.argv[1]).resolve().as_uri()[7:])' "$3")

xdg-open zed://file$uri
```
