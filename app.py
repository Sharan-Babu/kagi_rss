import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy import text

from scraper import auto_detect, extract_items_with_mapping
from rss_utils import generate_rss

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Disable Jinja2 auto-escape for inline JS injection (we will keep templates simple)
app.jinja_env.autoescape = True

db = SQLAlchemy(app)

# ----------------------------------------------------------------------------
# Database Models
# ----------------------------------------------------------------------------

class Feed(db.Model):
    __tablename__ = 'feeds'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(2048), nullable=False)

    # CSS selectors
    item_selector = db.Column(db.String(512), nullable=False)
    title_selector = db.Column(db.String(512), nullable=True)
    link_selector = db.Column(db.String(512), nullable=True)
    content_selector = db.Column(db.String(512), nullable=True)
    date_selector = db.Column(db.String(512), nullable=True)
    author_selector = db.Column(db.String(512), nullable=True)
    image_selector = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def as_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'item_selector': self.item_selector,
            'title_selector': self.title_selector,
            'link_selector': self.link_selector,
            'content_selector': self.content_selector,
            'date_selector': self.date_selector,
            'author_selector': self.author_selector,
            'image_selector': self.image_selector,
        }

# ----------------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------------

def init_db():
    with app.app_context():
        db.create_all()
        # Add image_selector column if DB existed before
        try:
            with db.engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE feeds ADD COLUMN image_selector VARCHAR(512)")
        except Exception:
            pass  # column exists or other

# ----------------------------------------------------------------------------
# Routes - UI Pages
# ----------------------------------------------------------------------------

@app.route('/')
def index():
    feeds = Feed.query.all()
    return render_template('index.html', feeds=feeds)

@app.route('/feeds/<int:feed_id>')
def view_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    return render_template('feed_detail.html', feed=feed)

@app.route('/feeds/new')
def new_feed_page():
    return render_template('feed_new.html')

@app.route('/picker')
def picker_page():
    url = request.args.get('url')
    field = request.args.get('field')
    item_sel = request.args.get('item_sel', '')
    if not url or not field:
        return 'Missing url or field', 400
    return render_template('picker.html', url=url, field=field, item_sel=item_sel)

# ----------------------------------------------------------------------------
# API Routes (JSON)
# ----------------------------------------------------------------------------

@app.route('/api/feeds', methods=['GET'])
def api_list_feeds():
    feeds = Feed.query.all()
    return jsonify([f.as_dict() for f in feeds])

@app.route('/api/feeds', methods=['POST'])
def api_create_feed():
    data = request.json
    # Required fields: name, url, item_selector
    required = ['name', 'url', 'item_selector']
    if not all(field in data for field in required):
        return jsonify({'error': 'Missing required fields'}), 400

    feed = Feed(
        name=data['name'],
        url=data['url'],
        item_selector=data['item_selector'],
        title_selector=data.get('title_selector'),
        link_selector=data.get('link_selector'),
        content_selector=data.get('content_selector'),
        date_selector=data.get('date_selector'),
        author_selector=data.get('author_selector'),
        image_selector=data.get('image_selector')
    )
    db.session.add(feed)
    db.session.commit()
    return jsonify(feed.as_dict()), 201

@app.route('/api/feeds/<int:feed_id>', methods=['PUT'])
def api_update_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    data = request.json or {}
    for field in [
        'name', 'url', 'item_selector', 'title_selector',
        'link_selector', 'content_selector', 'date_selector', 'author_selector', 'image_selector']:
        if field in data:
            setattr(feed, field, data[field])
    db.session.commit()
    return jsonify(feed.as_dict())

@app.route('/api/feeds/<int:feed_id>', methods=['DELETE'])
def api_delete_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    db.session.delete(feed)
    db.session.commit()
    return jsonify({'status': 'deleted'})

@app.route('/api/auto_detect', methods=['POST'])
def api_auto_detect():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Missing url'}), 400
    try:
        mapping, preview_items = auto_detect(url)
        return jsonify({'mapping': mapping, 'preview': preview_items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview', methods=['POST'])
def api_preview():
    data = request.json
    url = data.get('url')
    mapping = data.get('mapping')
    if not url or not mapping:
        return jsonify({'error': 'Missing url or mapping'}), 400
    try:
        items = extract_items_with_mapping(url, mapping)
        return jsonify({'items': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ----------------------------------------------------------------------------
# RSS Feed Endpoint
# ----------------------------------------------------------------------------

@app.route('/feeds/<int:feed_id>.xml')
def feed_rss(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    try:
        mapping = {
            'item_selector': feed.item_selector,
            'title_selector': feed.title_selector,
            'link_selector': feed.link_selector,
            'content_selector': feed.content_selector,
            'date_selector': feed.date_selector,
            'author_selector': feed.author_selector,
            'image_selector': feed.image_selector,
        }
        xml_output = generate_rss(feed, mapping)
        return Response(xml_output, mimetype='application/rss+xml')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ----------------------------------------------------------------------------
# Proxy Route for Visual Selector (to bypass CORS)
# ----------------------------------------------------------------------------

@app.route('/proxy')
def proxy():
    """Fetch external HTML and serve it with relaxed headers so it can be iframed."""
    target_url = request.args.get('url')
    if not target_url:
        abort(400)

    import requests, re
    try:
        resp = requests.get(target_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; Site2RSS-picker/1.0)'
        })
    except Exception as e:
        return f'Error fetching url: {e}', 500

    html = resp.text

    # Inject <base> tag to resolve relative URLs so the page looks correct
    if '<head' in html:
        base_tag = f"<base href=\"{target_url}\">"
        html = re.sub(r'<head[^>]*>', lambda m: m.group(0) + base_tag, html, count=1, flags=re.IGNORECASE)

    # Always return 200 so iframe can load even if origin sent 403/404
    response = Response(html, status=200, mimetype='text/html')
    # Remove framing-breaking headers
    response.headers.pop('X-Frame-Options', None)
    response.headers.pop('Content-Security-Policy', None)
    return response

# ----------------------------------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 