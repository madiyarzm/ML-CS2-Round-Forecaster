# SpotiVibes

ML pipeline to analyze your Spotify library with **K-Means clustering** on audio features — discover "hidden vibes" beyond genre.

## How to run

### 1. Install dependencies

```bash
cd SpotiVibes
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set credentials (env vars)

Create a `.env` file in the project root (it is gitignored):

```
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
```

Get them from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) → your app → Settings. If you get **403 Forbidden** on audio-features: in Development Mode only listed users can use the app — add your Spotify account in **Settings → User Management**.

**Redirect URI (must match exactly):** In the app’s **Redirect URIs** click **Add** and paste **exactly** (no space, no trailing slash, `http` not `https`):

```
http://127.0.0.1:8080/callback
```

(Port 8080 avoids conflict with Jupyter on 8888.) Then click **Save**. If you use a different URI (e.g. `http://localhost:8080/callback`), set the same value in `.env` as `SPOTIPY_REDIRECT_URI=...`.

### 3. Launch the notebook

```bash
jupyter notebook sonic_blueprint_pipeline.ipynb
```

Or from VS Code / Cursor: open `sonic_blueprint_pipeline.ipynb` and use "Run All" or run cells one by one.

### 4. Run the pipeline

- Execute cells **in order** (top to bottom).
- First run: you’ll be asked to log in to Spotify in the browser (OAuth).
- The notebook will: fetch liked tracks → get audio features → scale → fit K-Means → show elbow plot, PCA scatter, and radar chart of cluster “vibes”.

## Requirements

- Python 3.10+
- Spotify account and app (Client ID + Client Secret)

## Project layout

- `sonic_blueprint_pipeline.ipynb` — main notebook (ingestion, preprocessing, K-Means, PCA, visualizations)
- `requirements.txt` — Python dependencies
- `.env` — your credentials (create locally, do not commit)
