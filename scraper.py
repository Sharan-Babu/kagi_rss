import re
from urllib.parse import urljoin
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as dateparser

# Try to import google-genai for LLM support
try:
    from google import genai
    from dotenv import load_dotenv
    import json, os

    load_dotenv()
    _GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    _gemini_client = genai.Client(api_key=_GEMINI_API_KEY) if _GEMINI_API_KEY else None
    # Choose model
    _GEMINI_MODEL = "gemini-2.0-flash"  # default, can be overridden later
except Exception:
    _gemini_client = None

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

# Simple in-memory cache for downloaded HTML to avoid repeated network calls in a single run
_HTML_CACHE: Dict[str, str] = {}

def fetch_html(url: str, timeout: int = 10, use_cache: bool = True) -> str:
    if use_cache and url in _HTML_CACHE:
        return _HTML_CACHE[url]
    resp = requests.get(url, timeout=timeout, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; kagi-rss-generator/1.0)'
    })
    resp.raise_for_status()
    html = resp.text
    if use_cache:
        # naive cache, keep up to 200 pages
        if len(_HTML_CACHE) > 200:
            _HTML_CACHE.clear()
        _HTML_CACHE[url] = html
    return html


def find_candidate_item_selector(soup: BeautifulSoup) -> str:
    """Return a CSS selector string that identifies repeating content items."""
    # Common container selectors to test in order
    candidates = [
        'article',
        'div.post', 'div.entry', 'div.article',
        'li.post', 'li.entry', 'li.article',
        'div[class*="post"]', 'div[class*="entry"]', 'div[class*="article"]',
    ]
    for selector in candidates:
        matches = soup.select(selector)
        if len(matches) >= 3:
            return selector
    # Fallback: try to find any tag that appears many times and contains <a>
    tag_counts = {}
    for tag in soup.find_all(True):
        key = tag.name
        tag_counts[key] = tag_counts.get(key, 0) + 1
    # choose tag with most counts if appears >5 and not common layout tags
    sorted_tags = sorted(tag_counts.items(), key=lambda x: -x[1])
    for name, cnt in sorted_tags:
        if cnt >= 5 and name not in ['div', 'span', 'p', 'a', 'li']:
            return name
    # Final fallback: 'a'
    return 'a'


def text_of(el: Tag) -> str:
    if not el:
        return ''
    return ' '.join(el.stripped_strings)


def parse_date(text: str):
    try:
        return dateparser.parse(text, fuzzy=True)
    except Exception:
        return None

# -----------------------------------------------------------------------------
# LLM-powered selector detection
# -----------------------------------------------------------------------------

def _strip_code(text: str) -> str:
    """Remove ``` wrappers the model might add."""
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _mapping_is_valid(url: str, mapping: Dict[str, str]) -> bool:
    essential = ['item_selector', 'title_selector', 'link_selector']
    if not all(k in mapping and isinstance(mapping[k], str) and mapping[k].strip() for k in essential):
        return False
    # quick sanity by extracting 1 item
    try:
        items = extract_items_with_mapping(url, mapping, limit=1)
        return len(items) > 0
    except Exception:
        return False


def llm_detect_selectors(url: str, html: str) -> Optional[Dict[str, str]]:
    """Use Gemini chat to iteratively get selectors. Returns mapping or None."""
    if not _gemini_client:
        return None

    snippet = html[:50000]
    base_prompt = (
        "You are an expert web scraper and will help build an RSS feed. "
        "Given the HTML of a web page that lists articles, extract CSS selectors needed to build the feed.\n\n"
        "Return ONLY valid JSON (no markdown) matching exactly this schema:\n"
        "{\n"
        "  \"result\": \"success|partial\",  # 'success' if confident selectors will work, else 'partial'\n"
        "  \"item_selector\": string,  # selects each article block\n"
        "  \"title_selector\": string, # relative selector inside item for the title\n"
        "  \"link_selector\": string,  # relative selector for the <a> link to full article\n"
        "  \"content_selector\": string, # relative selector for summary/paragraph (can be empty)\n"
        "  \"date_selector\": string,  # relative selector for publication date (can be empty)\n"
        "  \"author_selector\": string,  # relative selector for author (can be empty)\n"
        "  \"image_selector\": string  # relative selector for main image (can be empty)\n"
        "}\n"
        "If a field is not present in the page put an empty string. "
        "Never wrap the JSON in code fences."
    )

    chat = _gemini_client.chats.create(model=_GEMINI_MODEL)

    # First request
    chat.send_message(base_prompt + "\n\nHTML:\n" + snippet)

    for attempt in range(3):
        response = chat.get_history()[-1]  # latest assistant response
        text = _strip_code(response.parts[0].text)
        print("Gemini response attempt", attempt + 1, ":", text[:500])
        try:
            mapping = json.loads(text)
        except Exception:
            mapping = {}

        if mapping and mapping.get('result') == 'success' and _mapping_is_valid(url, mapping):
            mapping.pop('result', None)
            return mapping

        # Compose feedback
        feedback = (
            "Your previous JSON was incomplete or did not work for extracting items. "
            "Please try again and output corrected JSON only."
        )
        chat.send_message(feedback)

    return None

# -----------------------------------------------------------------------------
# Article-level selector detection (for date/author/content inside article page)
# -----------------------------------------------------------------------------

ARTICLE_SELECTOR_CACHE: Dict[str, Dict[str, str]] = {}


def llm_detect_article_fields(url: str, html: str) -> Optional[Dict[str, str]]:
    """Ask Gemini for selectors (relative to full article HTML) for missing fields."""
    if not _gemini_client:
        return None

    host = url.split('/')[2]
    if host in ARTICLE_SELECTOR_CACHE:
        return ARTICLE_SELECTOR_CACHE[host]

    snippet = html[:50000]
    prompt = (
        "You are an expert web scraper. Given the HTML of a single article, "
        "return CSS selectors (not XPath) that locate the publication date, author name, and main content text.\n\n"
        "Return ONLY JSON (no markdown) matching exactly this schema:\n"
        "{\n"
        "  \"date_selector\": string,\n"
        "  \"author_selector\": string,\n"
        "  \"content_selector\": string,\n"
        "  \"image_selector\": string\n"
        "}\n"
        "If a field is not present, set empty string. Never wrap JSON in code fences.\n\n"
        "HTML:\n" + snippet
    )

    try:
        response = _gemini_client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[prompt],
            config=genai.types.GenerateContentConfig(
                max_output_tokens=1024,
                temperature=0.1
            )
        )
        text = _strip_code(response.text)
        print("Gemini article field response for", host, ":", text[:400])
        data = json.loads(text)
        ARTICLE_SELECTOR_CACHE[host] = data
        return data
    except Exception as e:
        print("Article field LLM error", e)
        return None

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def auto_detect(url: str) -> Tuple[Dict[str, str], List[Dict]]:
    """Detect selectors using LLM; fallback to heuristics."""
    html = fetch_html(url)

    mapping = llm_detect_selectors(url, html)
    if mapping is None:
        # Fallback heuristic
        soup = BeautifulSoup(html, 'html.parser')
        item_selector = find_candidate_item_selector(soup)
        mapping = {
            'item_selector': item_selector,
            'title_selector': 'h1, h2, h3',
            'link_selector': 'a',
            'content_selector': 'p',
            'date_selector': 'time',
            'author_selector': '[class*="author"], .author',
            'image_selector': '',
        }

    # Remove potential 'result' key if present
    mapping.pop('result', None)
    items = extract_items_with_mapping(url, mapping, limit=5)
    return mapping, items


def extract_items_with_mapping(base_url: str, mapping: Dict[str, str], limit: int = 20) -> List[Dict]:
    html = fetch_html(base_url)
    soup = BeautifulSoup(html, 'html.parser')
    item_selector = mapping.get('item_selector') or 'article'
    items: List[Dict] = []

    # We will dynamically fetch article-level selectors per external host when needed
    
    for item_el in soup.select(item_selector):
        if len(items) >= limit:
            break

        title_el = item_el.select_one(mapping.get('title_selector')) if mapping.get('title_selector') else None
        link_el = item_el.select_one(mapping.get('link_selector')) if mapping.get('link_selector') else None
        content_el = item_el.select_one(mapping.get('content_selector')) if mapping.get('content_selector') else None
        date_el = item_el.select_one(mapping.get('date_selector')) if mapping.get('date_selector') else None
        author_el = item_el.select_one(mapping.get('author_selector')) if mapping.get('author_selector') else None
        image_el = item_el.select_one(mapping.get('image_selector')) if mapping.get('image_selector') else None

        title = text_of(title_el)
        link = link_el['href'] if link_el and link_el.has_attr('href') else None
        if link:
            link = urljoin(base_url, link)

        content = text_of(content_el)
        date_text = text_of(date_el)
        pub_date = parse_date(date_text)
        author = text_of(author_el)
        image_url = None
        if image_el:
            if image_el.name == 'img' and image_el.has_attr('src'):
                image_url = urljoin(base_url, image_el['src'])
            elif image_el.has_attr('content'):
                image_url = urljoin(base_url, image_el['content'])

        # Fallback to article page if any field missing
        if link and (not pub_date or not author or not content or not image_url):
            host = link.split('/')[2]
            extra_selectors = ARTICLE_SELECTOR_CACHE.get(host)
            if extra_selectors is None:
                art_html = fetch_html(link)
                extra_selectors = llm_detect_article_fields(link, art_html) or {}
            if extra_selectors:
                art_html = fetch_html(link)
                art_soup = BeautifulSoup(art_html, 'html.parser')
                if not pub_date and extra_selectors.get('date_selector'):
                    date_el = art_soup.select_one(extra_selectors['date_selector'])
                    pub_date = parse_date(text_of(date_el))
                if not author and extra_selectors.get('author_selector'):
                    author = text_of(art_soup.select_one(extra_selectors['author_selector']))
                if not content and extra_selectors.get('content_selector'):
                    content = text_of(art_soup.select_one(extra_selectors['content_selector']))
                if not image_url and extra_selectors.get('image_selector'):
                    img_el = art_soup.select_one(extra_selectors['image_selector'])
                    if img_el:
                        if img_el.name == 'img' and img_el.has_attr('src'):
                            image_url = urljoin(link, img_el['src'])
                        elif img_el.has_attr('content'):
                            image_url = urljoin(link, img_el['content'])
                ARTICLE_SELECTOR_CACHE[host] = extra_selectors

        # Only accept items with title and link at minimum
        if not title or not link:
            continue

        item = {
            'title': title,
            'link': link,
            'content': content,
            'date': pub_date.isoformat() if pub_date else None,
            'author': author,
            'image': image_url,
        }
        items.append(item)

    return items 