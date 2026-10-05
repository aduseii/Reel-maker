# Reel Maker

A Windows desktop app that turns a 16:9 video into a 1080 × 1920 Instagram Reel.

- **Background:** black, white, blurred video or any colour
- **Safe zones:** Level 1 (clear of all Instagram UI), Level 2, the 3:4 profile-grid crop, or your own margins
- **Trim** with handles on the timeline
- **Text boxes** you can type into right on the preview (double-click), that keep a fixed width and wrap onto new lines, with box or line-highlight styles, an iPhone-style font (Inter Display) and built-in colour emoji with an **Emoji** picker (search, categories, skin tones, recents). You can also load your own colour emoji font (`.ttf`) or a folder of emoji images under **Layers → Text → Emoji → Change**.
- **Logos and photos** you can drag, resize and snap to the safe zone
- **Alignment guides:** pink lines and snapping when anything lines up with the centre, the safe zone, the video or another layer (hold Alt to move freely)
- **Templates:** save a layout once, and every new video uses it locked in place. Only the words and images change. Sign in with GitHub to keep them in the cloud and use them on any PC.
- **Cover editor:** frame a 9:16 window over the full 16:9 picture, add a title and save a PNG
- **Export:** H.264 MP4 with AAC audio, ready for Instagram, with **Play video** and **Show in folder** when it finishes
- **Built-in updates:** one click installs the newest release

## Install

Download `ReelMakerSetup-x.y.z.exe` from [Releases](../../releases) and run it. Windows may say "Windows protected your PC" because the app isn't signed: click **More info → Run anyway**. Setup downloads the video encoder (about 30 MB) once.

## Updates

Click the circular arrow in the top bar to check for updates. Reel Maker also checks quietly when it starts and shows **Update to x.y.z** when a new version is out. Clicking it downloads the installer from this repo's latest release, checks it, closes the app, installs the update and reopens. Your templates are kept.

## Cloud templates (GitHub)

**Templates → Sign in with GitHub** shows a short code; enter it at github.com/login/device and your templates are kept in a *secret gist* on your GitHub account (unlisted and not on your profile, though anyone with its exact link could open it). They sync when the app opens, whenever you save or delete a template, and from **Templates → Sync now**. The newest version of each template wins, and deleting one deletes it everywhere. The sign-in token only has the `gist` permission and is stored encrypted for your Windows account.

The app's GitHub OAuth App client ID is `GITHUB_CLIENT_ID` in `app/cloud.py` (public by design; device flow needs no secret).

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

1. Change the code.
2. Bump `__version__` in `app/core.py` (for example `1.1.0` → `1.2.0`).
3. Commit and push to `main`.

GitHub Actions builds the installer (about 3 minutes) and publishes it under **Releases** as `v1.2.0`. Pushes that don't change the version still build an installer; you'll find it in that run's **Artifacts** on the Actions tab.

Installing a new version replaces the old one and keeps your templates.

## Where things are saved

- Templates: `%LOCALAPPDATA%\ReelMaker\templates\` (and your GitHub gist when signed in)
- GitHub sign-in (encrypted for your Windows account): `%LOCALAPPDATA%\ReelMaker\cloud\`
- Video encoder: `%LOCALAPPDATA%\ReelMaker\ffmpeg\`
- Error log: `%LOCALAPPDATA%\ReelMaker\error.log`

## Credits

- Inter Display font by Rasmus Andersson, SIL Open Font License (`app/fonts/Inter-LICENSE.txt`)
- Noto Emoji by Google, Apache License 2.0 (`app/emoji/NOTICE.txt`)
- Emoji names and groups from unicode-emoji-json, MIT (`app/emoji/LICENSE-unicode-emoji-json.txt`)
- FFmpeg via imageio-ffmpeg; Qt via PySide6 (LGPL)
