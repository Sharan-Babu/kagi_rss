from typing import Dict
from datetime import timezone
from dateutil import parser as dateparser
import mimetypes

from feedgen.feed import FeedGenerator

from scraper import extract_items_with_mapping


def generate_rss(feed_model, mapping: Dict[str, str]) -> bytes:
    """Generate RSS XML string for a given Feed SQLAlchemy model."""
    items = extract_items_with_mapping(feed_model.url, mapping, limit=50)

    fg = FeedGenerator()
    fg.id(str(feed_model.id))
    fg.title(feed_model.name or feed_model.url)
    fg.link(href=feed_model.url, rel='alternate')
    fg.description(f"RSS feed generated from {feed_model.url}")

    for itm in items:
        fe = fg.add_entry()
        fe.title(itm['title'])
        fe.link(href=itm['link'])
        if itm.get('date'):
            try:
                dt = dateparser.parse(itm['date']) if isinstance(itm['date'], str) else itm['date']
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                fe.pubDate(dt)
            except Exception:
                # ignore date parsing errors
                pass
        if itm.get('author'):
            fe.author({'name': itm['author']})
        if itm.get('content'):
            fe.description(itm['content'])
        if itm.get('image'):
            img_url = itm['image']
            # Try to guess mime type
            mime = mimetypes.guess_type(img_url)[0] or 'image/jpeg'
            fe.enclosure(img_url, 0, mime)

    return fg.rss_str(pretty=True) 