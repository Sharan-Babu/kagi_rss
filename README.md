# Site2RSS

Generate RSS feeds for any website—even those without native feeds—using a lightweight Flask backend, heuristic + Gemini-powered scraping, and a vanilla-JS UI.

## 📐 Architecture Overview

1. **Flask API / UI (`app.py`)**
   • CRUD for feeds, HTML templates, JSON endpoints, `/proxy` for CORS-free page capture, `/feeds/<id>.xml` RSS output.

2. **SQLite + SQLAlchemy**
   • `Feed` model stores CSS selectors per site (item, title, link, content, date, author, image).

3. **Scraper (`scraper.py`)**
   ```text
   ┌ URL
   │  ├─ fetch_list_page → BeautifulSoup
   │  ├─ LLM auto-detect selectors   ← Gemini 2.0 Flash
   │  │   • JSON schema (item_selector … image_selector)
   │  │   • 3-turn self-validation loop
   │  └─ Heuristic fallback (if LLM unsure)
   └ Extract items
       ├─ Missing fields? fetch article   → LLM per-host selector cache
       └─ Build item dict {title, link, content, date, author, image}
   ```
   • Results & extra selectors cached in-memory for speed.

4. **RSS Generation (`rss_utils.py`)**
   • Uses `feedgen` to emit RSS 2.0 with `<enclosure>` for images. Timezone-naive dates are fixed to UTC.

5. **Visual Picker**
   • `/picker` renders a proxied copy of the page in an iframe.
   • User hovers/clicks to choose elements.
   • JS computes smart selectors:
     – `item_selector`: semantic class (e.g. `.post` / `article`).
     – Child selectors: relative path from item container (`figure img`, `h2.title`, etc.).
   • Selector sent back via `postMessage`; preview auto-refreshes.

## ⚡ Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env (NOT committed)
GEMINI_API_KEY=YOUR_KEY_HERE

python app.py
```
Go to `http://127.0.0.1:5000`.

## 🛠️ Typical Workflow

1. **Add Feed** → enter site URL → *Auto Detect* (LLM) → selectors + preview.
2. **Fine-tune** selectors with the 🎯 picker; preview updates live.
3. **Save** feed → RSS available at `/feeds/<id>.xml`.

## 🤖 LLM Usage

Gemini 2.5 Flash is used twice:

1. **List-page auto detection**  
   • Prompt returns full selector mapping + `result` flag.  
   • Client loops up to 3 times, validating by extracting a sample item; asks Gemini to correct itself if needed.

2. **Article-page field recovery**  
   • When date/author/content/image are missing, the first article page is sent to Gemini to get per-host selectors.  
   • These selectors are cached to avoid repeat calls.

Fallback heuristics ensure a feed is created even if the LLM fails.

## 🖱️ Selector Strategy

• Generic, class-based selectors preferred over brittle nth-child paths.
• For images the picker detects `img` tags or parent figures with semantic classes.
• The `<base>` tag injected by `/proxy` makes relative resources resolve, while stripping CSP/X-Frame headers avoids 403 errors in the iframe.

---
