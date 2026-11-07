"""Runtime hook de PyInstaller: prepara pythonnet en la aplicación congelada.

Python.Runtime.dll es un ensamblado mixto: al cargarlo, .NET necesita encontrar
pythonXY.dll y las DLL de WebView2. Aquí se dejan accesibles antes de que se
importe la interfaz.
"""

import os
import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _exe_dir = os.path.dirname(sys.executable)
    _dll_name = f"python{sys.version_info[0]}{sys.version_info[1]}.dll"

    os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")

    for _candidate in (os.path.join(_base, _dll_name), os.path.join(_exe_dir, _dll_name)):
        if os.path.isfile(_candidate):
            os.environ["PYTHONNET_PYDLL"] = _candidate
            break

    _search_dirs = [
        _base,
        _exe_dir,
        os.path.join(_base, "pythonnet", "runtime"),
        os.path.join(_base, "webview", "lib"),
    ]
    _search_dirs = [path for path in _search_dirs if os.path.isdir(path)]

    os.environ["PATH"] = os.pathsep.join(
        _search_dirs + [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    )

    _handles = []
    if hasattr(os, "add_dll_directory"):
        for _path in _search_dirs:
            try:
                _handles.append(os.add_dll_directory(_path))
            except OSError:
                pass
