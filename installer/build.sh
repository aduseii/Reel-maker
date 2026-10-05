#!/usr/bin/env bash
# Builds dist/ReelMakerSetup.exe (Windows installer) on Linux.
# Needs: python3 + pip, curl, unzip, makensis (apt install nsis).
# Used by .github/workflows/build.yml; also runs locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/build"
STAGE="$WORK/ReelMaker"
DIST="$ROOT/dist"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/app/core.py")"

PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7%2B20241016-x86_64-pc-windows-msvc-install_only.tar.gz"
QT_VER="6.11.2"

echo "==> Reel Maker $VERSION"
rm -rf "$WORK" && mkdir -p "$STAGE" "$WORK/wheels" "$DIST"

echo "==> Windows Python"
curl -sSL -o "$WORK/python.tar.gz" "$PY_URL"
tar xzf "$WORK/python.tar.gz" -C "$STAGE"

echo "==> Windows wheels"
python3 -m pip download -q --dest "$WORK/wheels" --platform win_amd64 --python-version 3.12 \
  --only-binary=:all: --no-deps \
  "PySide6-Essentials==$QT_VER" "PySide6-Addons==$QT_VER" "shiboken6==$QT_VER" "imageio-ffmpeg==0.6.0"

SP="$STAGE/python/Lib/site-packages"
mkdir -p "$SP"
(cd "$SP"
 unzip -q -o "$WORK"/wheels/shiboken6-*.whl
 unzip -q -o "$WORK"/wheels/imageio_ffmpeg-*.whl
 unzip -q -o "$WORK"/wheels/pyside6_essentials-*.whl
 unzip -q -o "$WORK"/wheels/pyside6_addons-*.whl \
   'PySide6/Qt6Multimedia.dll' 'PySide6/QtMultimedia.pyd' 'PySide6/plugins/multimedia/windowsmediaplugin.dll')

echo "==> Trim Qt to what the app uses"
# FFmpeg itself is downloaded by the installer, which keeps the .exe under 30 MB.
rm -f "$SP"/imageio_ffmpeg/binaries/*.exe
python3 - "$SP" <<'EOF'
import os, sys, shutil, glob
sp = sys.argv[1]
keep = {
    "PySide6": {
        "__init__.py", "_config.py", "_git_pyside_version.py", "py.typed", "PySide6_Essentials.json",
        "pyside6.abi3.dll", "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll",
        "Qt6Multimedia.dll", "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtNetwork.pyd",
        "QtMultimedia.pyd", "support/__init__.py", "support/deprecated.py", "support/generate_pyi.py",
        "plugins/platforms/qwindows.dll", "plugins/styles/qmodernwindowsstyle.dll",
        "plugins/imageformats/qgif.dll", "plugins/imageformats/qico.dll",
        "plugins/imageformats/qjpeg.dll", "plugins/imageformats/qwebp.dll",
        "plugins/multimedia/windowsmediaplugin.dll",
    },
    "shiboken6": {
        "__init__.py", "_config.py", "_git_shiboken_module_version.py", "py.typed", "Shiboken.pyd",
        "shiboken6.abi3.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    },
}
for pkg, names in keep.items():
    base = os.path.join(sp, pkg)
    for path in glob.glob(base + "/**/*", recursive=True):
        rel = os.path.relpath(path, base).replace(os.sep, "/")
        if os.path.isfile(path) and rel not in names:
            os.remove(path)
    for name in names:
        assert os.path.isfile(os.path.join(base, name)), f"missing {pkg}/{name}"
    for d in sorted(glob.glob(base + "/**/", recursive=True), key=len, reverse=True):
        if not os.listdir(d):
            os.rmdir(d)
py = os.path.dirname(os.path.dirname(sp))
for d in ["Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo", "Lib/ensurepip", "Lib/lib2to3",
          "Lib/pydoc_data", "Lib/unittest", "Lib/sqlite3", "Lib/venv", "Lib/xmlrpc", "Lib/wsgiref",
          "Lib/curses", "Lib/dbm", "tcl", "include", "libs", "Lib/site-packages/pip"]:
    shutil.rmtree(os.path.join(py, d), ignore_errors=True)
for p in glob.glob(os.path.join(sp, "pip-*.dist-info")):
    shutil.rmtree(p, ignore_errors=True)
for n in ["_sqlite3.pyd", "sqlite3.dll", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "_ctypes_test.pyd",
          "_testcapi.pyd", "_testinternalcapi.pyd", "_testbuffer.pyd", "_testimportmultiple.pyd",
          "_testmultiphase.pyd", "_testsinglephase.pyd", "_testclinic.pyd", "xxsubtype.pyd", "_testconsole.pyd"]:
    try:
        os.remove(os.path.join(py, "DLLs", n))
    except FileNotFoundError:
        pass
for p in glob.glob(py + "/**/*.pdb", recursive=True):
    os.remove(p)
for p in glob.glob(py + "/**/__pycache__", recursive=True):
    shutil.rmtree(p, ignore_errors=True)
EOF

echo "==> App files"
mkdir -p "$STAGE/app"
cp "$ROOT"/app/{reel_maker.py,core.py,cloud.py,launch.pyw,icon.ico,emoji_list.json} "$STAGE/app/"
cp -r "$ROOT/app/fonts" "$ROOT/app/emoji" "$STAGE/app/"
cp "$ROOT/app/icon.ico" "$ROOT/installer/get-ffmpeg.ps1" "$STAGE/"

echo "==> ReelMaker.exe launcher"
bash "$ROOT/installer/launcher/build.sh"
cp "$ROOT/installer/launcher/ReelMaker.exe" "$STAGE/python/ReelMaker.exe"
cp "$ROOT/installer/installer.nsi" "$WORK/"

echo "==> Installer"
(cd "$WORK" && makensis -V2 -DVER="$VERSION" installer.nsi)
mv "$WORK/ReelMakerSetup.exe" "$DIST/ReelMakerSetup-$VERSION.exe"
ls -la "$DIST"
SIZE=$(stat -c %s "$DIST/ReelMakerSetup-$VERSION.exe")
echo "==> Done: dist/ReelMakerSetup-$VERSION.exe ($((SIZE / 1048576)) MB)"
