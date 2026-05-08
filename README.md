# Multimedia Search Engine

A modular Python information retrieval system that supports local document search, web page indexing, image metadata retrieval, similar-image search, and audio transcript search.

This project was built as a practical Information Retrieval prototype. It combines classic IR techniques with multimedia features through a Flask web interface.

---

## Features

### Local File Indexing

The system can index local folders containing:

- `.txt`
- `.pdf`
- `.docx`
- `.csv`
- `.json`
- `.md`
- `.jpg`
- `.jpeg`
- `.png`
- `.webp`
- `.mp3`
- `.wav`
- `.m4a`
- `.ogg`
- `.webm`
- `.mp4`
- `.mpeg`
- `.mpga`
- `.flac`

Local files are parsed into searchable text and stored in a saved index.

---

### Web Page Indexing

The system can index web pages by URL.

It includes URL normalization and duplicate control, so equivalent URLs such as trailing-slash variants or default-port variants are not indexed multiple times.

---

### Text Retrieval

The system supports several search modes:

- Ranked retrieval
- Boolean retrieval
- Phrase retrieval
- Automatic search mode detection
- Query spelling assistance
- Synonym expansion
- Soundex-style phonetic suggestion
- Document analytics
- Term analytics

Examples:

```text
cloud security
"incident response"
python AND indexing
dog OR cat
network NOT attack
