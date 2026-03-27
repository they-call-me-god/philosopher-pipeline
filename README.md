# philosopher-pipeline

Automated Instagram Reel factory for philosopher quotes.

**Flow:** Claude generates quote → Wikimedia portrait → Claude vibe-matches song → Pillow B&W Reel image → yt-dlp audio → FFmpeg 30s MP4 → instagrapi upload

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
```

## Run

```bash
python pipeline.py --single   # one philosopher (least-posted)
python pipeline.py            # all philosophers
python scheduler.py           # daemon, posts daily at 9am
python upload_pending.py      # upload any pending output/*.mp4
```

## Input files

- `philosophers.md` — one philosopher per line (`- Name`)
- `songs.md` — one song per line (`- <youtube-url>  # <vibe label>`)

## State

`state.json` tracks used quotes/songs/photos per philosopher so nothing repeats across runs.

## Tests

```bash
pytest tests/
```
