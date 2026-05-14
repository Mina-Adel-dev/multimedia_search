# Integrated Multimedia Search and Shazam Navigation System

A graduation project that connects two independent web-based systems through clean navigation integration:

1. **Multimedia Project** - a multimedia search engine for local files, web pages, images, audio, videos, short-video metadata, news, and transcripts.
2. **Shazam Project** - a Shazam-style song detection system that identifies songs using microphone input or uploaded audio files.

The integration keeps both projects independent. Each system preserves its original user interface, theme, and functionality. The Multimedia Project includes a navigation button that opens the Shazam Project without redesigning either application.

## Features

- Connects two separate Flask applications through hyperlink-based navigation.
- Keeps the original Multimedia Project UI and theme unchanged.
- Keeps the original Shazam Project UI and theme unchanged.
- Adds an `Open Shazam` button inside the Multimedia Project header.
- Preserves all existing search, indexing, upload, preview, and detection functionality.
- Supports configurable navigation URLs through environment variables.
- Allows both projects to run at the same time on separate ports.
- Keeps the integration organized and maintainable by centralizing the Shazam URL in the Multimedia Flask app.

## Technologies Used

### Core Technologies

- Python
- Flask
- Jinja2 Templates
- HTML5
- CSS3
- JavaScript

### Multimedia Project

- Local file indexing and retrieval
- Ranked, phrase, and Boolean search
- Image metadata and similar image search
- Audio and video preview support
- Web/API data import
- Optional transcript and media processing dependencies

### Shazam Project

- Audio fingerprinting and feature extraction
- Microphone-based song detection
- Audio upload detection
- Lyrics lookup support
- `librosa`
- `numpy`
- `soundfile`
- `requests`
- `shazamio`
- `ytmusicapi`

## Installation & Setup

### Prerequisites

Install the following before running the project:

- Python 3.10 or newer
- `pip`
- A modern browser
- FFmpeg support is recommended for audio decoding
- Local audio files for the Shazam song index

### 1. Clone or Open the Project Folder

```powershell
cd "D:\FINAL Project"
```

### 2. Install Multimedia Project Dependencies

Open a terminal and run:

```powershell
cd "D:\FINAL Project\multimedia_search (discussion latest )"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ".\multimedia_search\requirements.txt"
```

### 3. Install Shazam Project Dependencies

Open a second terminal and run:

```powershell
cd "D:\FINAL Project\inttShazamll\Shazamll"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## How to Run

Run both projects in separate terminals.

### Terminal 1: Run the Multimedia Project

```powershell
cd "D:\FINAL Project\multimedia_search (discussion latest )"
.\.venv\Scripts\Activate.ps1
python -m flask --app multimedia_search.webapp.app:app run --host 127.0.0.1 --port 5000 --no-reload
```

Open the Multimedia Project:

```text
http://127.0.0.1:5000
```

### Terminal 2: Run the Shazam Project

```powershell
cd "D:\FINAL Project\inttShazamll\Shazamll"
.\.venv\Scripts\Activate.ps1
$env:APP_HOST = "0.0.0.0"
$env:APP_PORT = "5001"
python app.py
```

Open the Shazam Project:

```text
https://127.0.0.1:5001
```

The Shazam app uses HTTPS by default for microphone access. Your browser may show a warning for the local development certificate. Accept the local certificate warning when testing locally.

### Navigation Flow

1. Start both servers.
2. Open the Multimedia Project at `http://127.0.0.1:5000`.
3. Click the `Open Shazam` button in the Multimedia header.
4. The Shazam Project opens at `https://127.0.0.1:5001`.

## Project Structure

```text
FINAL Project/
|-- README.md
|-- docs/
|   `-- screenshots/
|       `-- .gitkeep
|-- inttShazamll/
|   `-- Shazamll/
|       |-- app.py
|       |-- requirements.txt
|       |-- README.md
|       |-- lyrics_overrides.json
|       `-- templates/
|           `-- index.html
|-- multimedia_search (discussion latest )/
|   `-- multimedia_search/
|       |-- main.py
|       |-- requirements.txt
|       |-- webapp/
|       |   |-- app.py
|       |   |-- services.py
|       |   |-- templates/
|       |   |   |-- base.html
|       |   |   `-- index.html
|       |   `-- static/
|       |       |-- css/
|       |       |   `-- main.css
|       |       `-- js/
|       |           `-- autocomplete.js
|       |-- core/
|       |-- parsers/
|       |-- scanner/
|       |-- sources/
|       |-- audio/
|       |-- video/
|       |-- vision/
|       `-- tests/
`-- run_logs/
```

## Integration Explanation

The project uses a simple and maintainable navigation integration.

The Multimedia Project remains the main entry point. Its header contains an `Open Shazam` button. This button links to the independently running Shazam Project.

The integration is implemented in the Multimedia Project:

- `multimedia_search/webapp/app.py` exposes the Shazam URL to templates.
- `multimedia_search/webapp/templates/base.html` renders the `Open Shazam` navigation button.
- `multimedia_search/webapp/static/css/main.css` contains a small button style that matches the original Multimedia header style.

No shared theme was applied. No redesign was done. Each project keeps its own templates, CSS, layout, and user experience.

### Configurable Navigation

By default, the Multimedia Project points to:

```text
https://127.0.0.1:5001
```

You can override the target URL if needed:

```powershell
$env:SHAZAM_APP_URL = "https://127.0.0.1:5001"
```

Optional separate settings are also supported:

```powershell
$env:SHAZAM_APP_SCHEME = "https"
$env:SHAZAM_APP_PORT = "5001"
```

## Screenshots

Place all project screenshots in:

```text
docs/screenshots/
```

Recommended screenshot files:

```text
docs/screenshots/multimedia-home.png
docs/screenshots/shazam-home.png
docs/screenshots/navigation-button.png
docs/screenshots/multimedia-search-results.png
docs/screenshots/shazam-detection-result.png
```

After uploading screenshots, update this section using the following format:

```markdown
![Multimedia Home](docs/screenshots/multimedia-home.png)
![Shazam Home](docs/screenshots/shazam-home.png)
![Navigation Button](docs/screenshots/navigation-button.png)
```

### Screenshot Checklist

- Multimedia Project home page
- Multimedia search results page
- `Open Shazam` navigation button
- Shazam Project home page
- Shazam song detection result

## Future Improvements

- Add a shared landing page that lists both systems without changing their internal UI.
- Add automatic health checks to show whether the Shazam server is running.
- Add a fallback message if the Shazam app is not available.
- Add Docker support for easier deployment.
- Add a unified startup script for running both applications together.
- Add automated end-to-end tests for navigation between the two systems.
- Add deployment documentation for university demo environments.

## Contributors / Team

Update this section with the final team information before submission.

| Role | Name |
| --- | --- |
| Student 1 | Your Name |
| Student 2 | Team Member Name |
| Supervisor | Supervisor Name |
| Department | Department Name |
| University | University Name |

## License

This project is prepared for academic and educational purposes as part of a university graduation project.

If the project will be published publicly, add an appropriate license file such as `LICENSE` and update this section with the selected license terms.
