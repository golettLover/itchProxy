from flask import Flask, request, Response
import requests
import base64
from urllib.parse import urlparse
import re
import os

app = Flask(__name__)

ITCHZONE_SCRIPT_PATTERN = re.compile(
    r'<script[^>]*src=["\']?https?://static\.itch\.io/htmlgame\.js["\']?[^>]*>\s*</script>\s*',
    re.IGNORECASE
)

ITCHZONE_ABSOLUTE_PATTERN = re.compile(
    r'((?:src|href|poster|data)\s*=\s*["\'])'
    r'(https?://[a-zA-Z0-9.-]*itch\.zone/[^"\']*)'
    r'(["\'])',
    re.IGNORECASE
)


def fetch_content(url):
    try:
        print(f"Fetching: {url}")
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
        })
        return resp
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def encode_base_url(base_url):
    return base64.urlsafe_b64encode(base_url.encode()).decode()


def decode_base_url(encoded):
    return base64.urlsafe_b64decode(encoded.encode()).decode()


def rewrite_html(html_bytes, target_url):
    html = html_bytes.decode('utf-8', errors='replace')

    # 1. Remove itch.io sitelock script
    html = ITCHZONE_SCRIPT_PATTERN.sub('', html)

    # 2. Extract game directory (strip filename like index.html)
    parsed = urlparse(target_url)
    path_parts = parsed.path.strip('/').split('/')
    game_dir_parts = path_parts[:-1] if '.' in path_parts[-1] else path_parts
    game_dir = '/'.join(game_dir_parts)
    base_upstream_url = f"{parsed.scheme}://{parsed.netloc}/{game_dir}"

    # 3. Inject <base> tag so ALL relative URLs (including JS-constructed) resolve through proxy
    encoded = encode_base_url(base_upstream_url)
    base_href = f"/proxy/{encoded}/"
    if '<head' in html.lower():
        html = re.sub(r'(<head[^>]*>)', rf'\1\n<base href="{base_href}">', html, count=1, flags=re.IGNORECASE)
    elif '<html' in html.lower():
        html = re.sub(r'(<html[^>]*>)', rf'\1\n<head><base href="{base_href}"></head>', html, count=1, flags=re.IGNORECASE)
    else:
        html = f'<head><base href="{base_href}"></head>\n' + html

    # 4. Rewrite absolute itch.zone URLs in attributes to go through the proxy
    def rewrite_absolute_url(match):
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)
        asset_path = url.split(f'{parsed.netloc}/', 1)[-1] if parsed.netloc in url else url
        proxy_url = f"/proxy/{encoded}/{asset_path}"
        return f'{prefix}{proxy_url}{suffix}'

    html = ITCHZONE_ABSOLUTE_PATTERN.sub(rewrite_absolute_url, html)

    return html.encode('utf-8')


@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Proxy Gateway</title></head>
    <body style="padding: 20px;">
        <h1>API Proxy Service Running</h1>
        <p>This proxy acts as a middleware reverse proxy for itch.io HTML5 games.</p>
        <p>To load content, use the /proxy endpoint:</p>
        <pre><code>/proxy?url=https%3A%2F%2Fhtml-classic.itch.zone%2Fhtml%2F...%2Findex.html</code></pre>
    </body>
    </html>
    """, 200, {'Content-Type': 'text/html'}


@app.route('/proxy', methods=['GET'])
def proxy():
    target_url = request.args.get('url')
    if not target_url:
        return "Error: Missing 'url' parameter.", 400

    parsed_target = urlparse(target_url)
    if not parsed_target.scheme or not parsed_target.netloc:
        return "Error: Invalid URL provided.", 400

    response = fetch_content(target_url)
    if response is None:
        return "Error: Could not fetch content from upstream.", 502
    if response.status_code != 200:
        return f"Error: Upstream returned status {response.status_code}.", response.status_code

    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type:
        content = rewrite_html(response.content, target_url)
    else:
        content = response.content

    headers = {
        'Content-Type': content_type or 'text/html',
        'Access-Control-Allow-Origin': '*',
        'Content-Security-Policy': "frame-ancestors *",
        'Cache-Control': 'no-cache',
    }

    return Response(content, status=200, headers=headers)


@app.route('/proxy/<encoded_base>/<path:asset_path>')
def asset_proxy(encoded_base, asset_path):
    try:
        base_url = decode_base_url(encoded_base)
    except Exception:
        return "Error: Invalid asset URL encoding.", 400

    upstream_url = f"{base_url}/{asset_path}"

    response = fetch_content(upstream_url)
    if response is None:
        return "Error: Could not fetch asset.", 502
    if response.status_code != 200:
        return f"Error: Upstream returned {response.status_code}.", response.status_code

    headers = {
        'Content-Type': response.headers.get('content-type', 'application/octet-stream'),
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=3600',
    }

    return Response(response.content, status=200, headers=headers)


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
