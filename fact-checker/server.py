from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript
import re
import json
import time
import requests
import openai

app = Flask(__name__)
CORS(app)


def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_video_title(video_id):
    """Fetch video title using YouTube oEmbed API (no API key needed)."""
    try:
        response = requests.get(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get("title", "Unknown Video")
    except Exception:
        pass
    return "Unknown Video"


def chunk_transcript(transcript, chunk_duration=40):
    """Group transcript entries into chunks of ~chunk_duration seconds each."""
    chunks = []
    current_chunk = []
    chunk_start = 0.0

    for entry in transcript:
        if not current_chunk:
            chunk_start = entry["start"]
        current_chunk.append(entry)
        chunk_end = entry["start"] + entry.get("duration", 0)
        if chunk_end - chunk_start >= chunk_duration:
            chunks.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": " ".join(e["text"] for e in current_chunk).replace("\n", " ")
            })
            current_chunk = []
            chunk_start = chunk_end

    if current_chunk:
        chunk_end = current_chunk[-1]["start"] + current_chunk[-1].get("duration", 0)
        chunks.append({
            "start": chunk_start,
            "end": chunk_end,
            "text": " ".join(e["text"] for e in current_chunk).replace("\n", " ")
        })

    return chunks


@app.route("/api/load", methods=["POST"])
def load_video():
    """Load video: fetch title + transcript and return chunked segments."""
    data = request.json or {}
    url = data.get("url", "")

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    title = get_video_title(video_id)

    ytt = YouTubeTranscriptApi()
    try:
        fetched = ytt.fetch(video_id)
        raw_entries = [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in fetched
        ]
    except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript) as e:
        # Fall back: list all transcripts and pick a generated one in any language
        try:
            tlist = ytt.list(video_id)
            lang_codes = [t.language_code for t in tlist]
            fetched = tlist.find_generated_transcript(lang_codes).fetch()
            raw_entries = [
                {"start": s.start, "duration": s.duration, "text": s.text}
                for s in fetched
            ]
        except Exception as inner:
            return jsonify({"error": f"No transcript available: {inner}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    chunks = chunk_transcript(raw_entries, chunk_duration=90)

    return jsonify({
        "video_id": video_id,
        "title": title,
        "transcript": raw_entries,
        "chunks": chunks
    })


@app.route("/api/factcheck", methods=["POST"])
def fact_check():
    """Run GPT fact-check on a transcript chunk."""
    data = request.json or {}
    text = data.get("text", "")
    api_key = data.get("api_key", "")
    video_title = data.get("video_title", "Unknown Video")

    if not api_key:
        return jsonify({"error": "OpenAI API key is required"}), 400
    if not text.strip():
        return jsonify({"claims": []}), 200

    client = openai.OpenAI(api_key=api_key)

    system_prompt = (
        "You are an expert real-time fact checker analysing video transcripts. "
        "Your job is to identify every specific, checkable claim in the transcript "
        "segment supplied. For each claim:\n"
        "  - Classify it as FACT or SPECULATION.\n"
        "  - FACT: a verifiable statement backed by evidence. Provide 1-3 real, "
        "publicly accessible source URLs (Wikipedia, academic papers, reputable news, "
        "official government/organisation sites). Only include URLs you are highly "
        "confident exist.\n"
        "  - SPECULATION: an opinion, prediction, unverified assertion, or exaggeration. "
        "Briefly explain why.\n\n"
        "Return ONLY a JSON object in this exact shape:\n"
        "{\n"
        '  "claims": [\n'
        "    {\n"
        '      "claim": "<short paraphrase of the claim>",\n'
        '      "type": "FACT" | "SPECULATION",\n'
        '      "explanation": "<brief explanation>",\n'
        '      "sources": ["<url>", ...]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "If there are no specific claims, return {\"claims\": []}."
    )

    user_prompt = f'Video title: "{video_title}"\n\nTranscript segment:\n{text}'

    max_attempts = 4
    backoff = 8  # seconds before first retry
    last_error = None

    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1200
            )
            result = json.loads(response.choices[0].message.content)
            claims = result.get("claims", [])
            break  # success
        except openai.AuthenticationError:
            return jsonify({"error": "Invalid OpenAI API key"}), 401
        except openai.RateLimitError as e:
            last_error = e
            if attempt < max_attempts - 1:
                wait = backoff * (2 ** attempt)  # 8s, 16s, 32s
                print(f"Rate limited – retrying in {wait}s (attempt {attempt + 1}/{max_attempts})")
                time.sleep(wait)
            else:
                return jsonify({"error": f"Rate limit persists after {max_attempts} attempts – try again in a minute"}), 429
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": str(last_error)}), 429

    return jsonify({"claims": claims})


if __name__ == "__main__":
    print("=== Fact Checker backend running on http://localhost:5503 ===")
    app.run(port=5503, debug=False)
