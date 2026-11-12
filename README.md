# Reel Maker

A Windows desktop app that turns a 16:9 video into a 1080 × 1920 Instagram Reel.

- **Background:** black, white, blurred video or any colour
- **Safe zones:** Level 1 (clear of all Instagram UI), Level 2, the 3:4 profile-grid crop, or your own margins
- **Trim** with handles on the timeline, then **Delete trimmed parts** to drop the rest from the timeline (non-destructive; **Restore full clip** brings it back)
- **Text boxes** you can type into right on the preview (double-click), that keep a fixed width and wrap onto new lines, with box or line-highlight styles, an iPhone-style font (Inter Display) and built-in colour emoji with an **Emoji** picker (search, categories, skin tones, recents). You can also load your own colour emoji font (`.ttf`) or a folder of emoji images under **Layers → Text → Emoji → Change**.
- **Logos and photos** you can drag, resize and snap to the safe zone, kept as sharp as possible: **SVG logos stay vectors** and are redrawn at the exact size shown; a picture shown at (or within 2% of) its own size is copied pixel for pixel; smaller sizes use one high-quality shrink; **Crispest size** snaps a logo to its own size or exactly ½, ⅓, ¼ … of it; and templates keep the original file byte for byte
- **One-line captions:** tick **Auto size and place one-line text** on a text box and, whenever its words fit on one line, they're shown bigger and placed in a balanced spot above the video (a little closer to the video than to the top, never touching it). Longer text goes back to the box's normal size and sits on the video. Saved in templates; caption boxes added by an X import have it on.
- **Sit on video:** one click puts a text box, logo or photo a set gap above the video and keeps it there as the words or the video change
- **Alignment guides:** pink lines and snapping when anything lines up with the centre, the safe zone, the video or another layer (hold Alt to move freely)
- **Templates:** save a layout once, and every new video uses it locked in place. Only the words and images change. Sign in with GitHub to keep them in the cloud and use them on any PC.
- **Cover editor:** frame a 9:16 window over the full 16:9 picture, add a title and save a PNG. The cover is built into the reel as its first frame (so Instagram uses it as the cover automatically) and stored as the MP4's thumbnail
- **Export:** H.264 MP4 with AAC audio, ready for Instagram: text and logos are mixed in at full colour detail with high-quality scaling and correct BT.709 colours, so they stay crisp after Instagram re-compresses them, with **Play video**, **Show in folder** and **Post to Instagram** (opens Instagram and selects the reel so you can drag it in) when it finishes
- **From X link:** paste a link to an X (Twitter) post (the **From X link** button, or just press **Ctrl+V** in the window) and Reel Maker downloads the video, loads it into your current template, fills the caption box with the post's text (links and leading @replies removed) and opens the Cover tab, so all that's left is picking a cover and exporting. Mark the box to fill with **Layers → Text → Caption box for X imports** (otherwise the first text box is used; with no text box, one is added just above the video). Videos are saved to `Videos\Reel Maker\From X`. Posts that X only shows to signed-in people (sensitive content, protected accounts) can't be imported.
- **Export folder:** **Export → Save to → Choose folder…** sends every reel (and its cover PNG) to one folder; **Next to the video** goes back to saving beside each video. Untick **Ask for a file name each time** for one-click exports with automatic names.
- **Undo / redo:** the arrows in the top bar (or Ctrl+Z, Ctrl+Y) step back and forward through your changes to the layout, text, images, trim, cover and export settings
- **No accidental changes:** number boxes, dropdowns and sliders ignore the mouse wheel until you click them, so scrolling the panel past them can't change anything. Zooming the cover with the wheel needs Ctrl held down.
- **Built-in updates:** one click installs the newest release

## Other versions

- **Web:** https://aduseii.github.io/Reel-maker/ works in Safari on iPhone and in Chrome or Edge on any computer, and can be added to the Home Screen. Same templates (connect GitHub with a token that only has the `gist` permission, or import template files). Exporting plays the clip once in real time. No X link import (browsers can't download from X). Source in `web/`.
- **iPhone app:** the `ios` pre-release has `ReelMaker.ipa` for AltStore or Sideloadly, and `altstore-source.json` to get updates in AltStore. Source in `ios/`.

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
| `app/x_import.py` | X link import: finds the post, downloads the video, cleans up the caption, keeps yt-dlp updated |
| `app/cloud.py` | GitHub sign-in and cloud templates |
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
- Videos imported from X: `Videos\Reel Maker\From X\`
- Newer copies of the X downloader (yt-dlp): `%LOCALAPPDATA%\ReelMaker\ytdlp\`
- Error log: `%LOCALAPPDATA%\ReelMaker\error.log`

## Credits

- Inter Display font by Rasmus Andersson, SIL Open Font License (`app/fonts/Inter-LICENSE.txt`)
- Noto Emoji by Google, Apache License 2.0 (`app/emoji/NOTICE.txt`)
- Emoji names and groups from unicode-emoji-json, MIT (`app/emoji/LICENSE-unicode-emoji-json.txt`)
- FFmpeg via imageio-ffmpeg; Qt via PySide6 (LGPL)
- yt-dlp (Unlicense) for downloading from X. It's bundled, and because X changes often the app fetches the newest yt-dlp from PyPI (checked against its published SHA-256) at most once a day, and again if a download fails.
