# FactCheckAI

Real-time AI-powered fact checker for YouTube videos. As a video plays, the app automatically analyses the transcript in segments and classifies each claim as a **FACT** (with sources) or **SPECULATION**, in sync with the video.

---

## Features

- Paste any YouTube URL and watch it in an embedded player
- Real-time fact checking via GPT-4o-mini — synced to the current video position
- Claims highlighted as **FACT** (green) or **SPECULATION** (amber)
- Source links provided for facts
- Persistent source archive grouped by video title with timestamps
- Automatic retry with countdown on rate limits

---

## Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys) (GPT-4o-mini access required)

---

## Running Locally

### 1. Clone the repo

```bash
git clone https://github.com/shashanksub42/fact-checker-whynot.git
cd fact-checker-whynot/fact-checker
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the backend

```bash
python server.py
```

The Flask API will start on **http://localhost:5503**.

### 5. Serve the frontend

Open a second terminal (in the same directory):

```bash
python3 -m http.server 5504
```

### 6. Open the app

Go to **http://localhost:5504** in your browser.

---

## Usage

1. Paste a YouTube URL into the input field.
2. Enter your OpenAI API key (stored locally in your browser — never sent to any third-party server).
3. Click **Load Video & Start Fact Check**.
4. Press play — fact check results will appear in the right panel as the video plays.
5. Scroll down to the **Source Archive** to review all saved sources, grouped by video.

---

## Project Structure

```
fact-checker/
├── server.py          # Flask backend — transcript fetching + OpenAI fact-check
├── index.html         # App shell
├── style.css          # Dark-theme UI
├── app.js             # YouTube IFrame API + polling + fact-check logic
└── requirements.txt   # Python dependencies
```

---

## Notes

- The app splits the transcript into ~90-second segments and fact-checks each one as it is reached during playback.
- If you hit OpenAI rate limits, the segment will automatically retry after 30 seconds.
- Sources are saved to `localStorage` and persist across page refreshes.
