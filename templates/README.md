# Templates for headless export

Put Reel Maker template files (`.json`) here so `app/headless_export.py` can use them anywhere,
including on a server or in an AI assistant's workspace that can't see your PC or your cloud gist.

To add one: on your PC, copy it from `%LOCALAPPDATA%\ReelMaker\templates\` (for example
`News.json`) into this folder and push. Logos and photos are stored inside the file, so nothing
else is needed.

Use it by name:

```
python app/headless_export.py --template "News" --video clip.mp4 --caption "Your headline"
```

A file here with the same name as one on your PC wins.
