# Reel Maker

A Windows desktop app that turns a 16:9 video into a 1080 × 1920 Instagram Reel.

- **Background:** black, white, blurred video or any colour
- **Safe zones:** Level 1 (clear of all Instagram UI), Level 2, the 3:4 profile-grid crop, or your own margins
- **Trim** with handles on the timeline
- **Text boxes** that keep a fixed width and wrap onto new lines, with box or line-highlight styles, an iPhone-style font (Inter Display) and built-in colour emoji
- **Logos and photos** you can drag, resize and snap to the safe zone
- **Templates:** save a layout once, and every new video uses it locked in place. Only the words and images change.
- **Cover editor:** frame a 9:16 window over the full 16:9 picture, add a title and save a PNG
- **Export:** H.264 MP4 with AAC audio, ready for Instagram

## Install

Download `ReelMakerSetup-x.y.z.exe` from [Releases](../../releases) and run it. Windows may say "Windows protected your PC" because the app isn't signed: click **More info → Run anyway**. Setup downloads the video encoder (about 30 MB) once.

## Making changes

The app is plain Python (PySide6) in `app/`:

| File | What it does |
| --- | --- |
| `app/reel_maker.py` | Window, panels, templates, cover editor, export |
| `app/core.py` | Version number, encoder download, emoji, text layout, layers |
| `app/launch.pyw` | Starts the app and shows a message if startup fails |
| `installer/` | Installer script and build script |

To run it from source on your PC:

```
pip install -r requirements.txt
python app/reel_maker.py
```

## Releasing an update

1. Change the code and bump `__version__` in `app/core.py`.
2. Commit and push to `main`. GitHub Actions builds the installer; download it from the run's **Artifacts**.
3. To publish it as a release, push a tag:

```
git tag v1.2.0
git push origin v1.2.0
```

The installer appears under **Releases**. Installing a new version replaces the old one and keeps your templates.

## Where things are saved

- Templates: `%LOCALAPPDATA%\ReelMaker\templates\`
- Video encoder: `%LOCALAPPDATA%\ReelMaker\ffmpeg\`
- Error log: `%LOCALAPPDATA%\ReelMaker\error.log`

## Credits

- Inter Display font by Rasmus Andersson, SIL Open Font License (`app/fonts/Inter-LICENSE.txt`)
- Noto Emoji by Google, Apache License 2.0 (`app/emoji/NOTICE.txt`)
- FFmpeg via imageio-ffmpeg; Qt via PySide6 (LGPL)
