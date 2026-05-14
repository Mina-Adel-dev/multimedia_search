# Shazam Clone

A simple local web app that detects songs from your microphone or from an uploaded audio file.

It works by scanning a local music folder, building audio fingerprints, and comparing new audio against the indexed songs.

## Main Features

- Detect songs using `Tap to Detect`
- Detect songs using manual audio upload
- Show the best match and Top-K results
- Show confidence score and match timestamp
- Play a short preview from the matched song
- Fetch lyrics/subtitles for the detected song
- Supports Arabic and English song names

## Project Files

```text
app.py                  Main Flask app
templates/index.html    Web page UI
requirements.txt        Python libraries
README.md               Project instructions
lyrics_overrides.json   Optional lyrics override links
```

Generated files like `.venv/`, `feature_cache.pkl`, `uploads/`, logs, and `__pycache__/` are ignored by Git.

## Requirements

- Python 3.10 or newer
- A browser with microphone permission
- Local music files to index

## Install

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install libraries:

```powershell
pip install -r requirements.txt
```

## Run

Start the app:

```powershell
python app.py
```

The app will print a URL like:

```text
https://192.168.x.x:5001
```

Open that URL in your browser.

## Music Folder

The default music folder is set inside `app.py`:

```text
D:\Music\new
```

Put your songs in that folder, then start the app. The first run may take time because the app builds the audio index.

After the first run, `feature_cache.pkl` is created automatically to make startup faster.

## How To Use

1. Open the app in your browser.
2. Allow microphone permission.
3. Press `Tap to Detect` to listen to a song.
4. Or use `Manual Upload` to upload an audio file.
5. Check the detected song, confidence, Top-K results, preview, and lyrics.

## Lyrics

Lyrics are searched using the detected song name.

The app cleans noisy filenames before searching. For example:

```text
abdulrahman mohammed-khalid barzanji-kolo laha _ قولو لها عبدالرحمن محمد وخالد برزنجي(MP3_160K).mp3
```

becomes a cleaner search like:

```text
قولو لها - عبدالرحمن محمد وخالد برزنجي
```

If lyrics cannot be found, the app shows:

```text
Lyrics not found
```

For the best lyrics accuracy, you can also place a `.lrc` or `.txt` file beside the song file with the same name.

Example:

```text
Song Name.mp3
Song Name.lrc
```

## Troubleshooting

### Microphone does not work

- Use the HTTPS URL printed by the app.
- Allow microphone permission in the browser.
- If testing on phone, connect the phone and computer to the same Wi-Fi.
- Refresh the page after restarting the server.

### Song is not detected

- Make sure the song exists in the music folder.
- Rebuild/restart the app after adding new songs.
- Try recording 25-45 seconds.
- Use a loud and clear part of the song.

### Lyrics are wrong or missing

- Make sure the filename has the correct artist and title.
- Add a local `.lrc` or `.txt` lyrics file beside the song.
- Check the server logs for the cleaned lyrics query and API response.

## Notes

- This is a local development project.
- Do not upload `.venv/` to GitHub.
- Do not upload generated cache files.
- The fingerprint detection logic is inside `app.py`.
