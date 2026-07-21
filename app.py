from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

# Configuration: Set via environment variable (e.g., PROXY_ORIGIN_DOMAIN=your-website.com)
PROXY_ORIGIN_DOMAIN = os.getenv('PROXY_ORIGIN_DOMAIN', 'localhost')

def fetch_content(url):
    """Helper function to safely fetch content from a given external URL."""
    try:
        print(f"Fetching content from: {url}")
        response = requests.get(url, timeout=15)
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {str(e)}")
        return None

@app.route('/')
def index():
    """Handles the root URL request (for testing)."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Proxy Gateway</title></head>
    <body style="padding: 20px;">
        <h1>API Proxy Service Running</h1>
        <p>This proxy acts as a middleware reverse proxy.</p>
        <p>To load content, you must send the initial HTML fetch via the /proxy endpoint:</p>
        <pre><code>/proxy?url=https%3A%2F%2Fexternal-site.com/index.html</code></pre>
        <p>Subsequent asset requests (CSS, JS) will be caught by the general resource handler.</p>
    </body>
    </html>
    """
    return html_content

@app.route('/proxy')
def proxy():
    """Handles the initial HTML document load."""
    target_url = request.args.get('url')

    if not target_url:
        return "Error: Missing 'url' parameter in the request.", 400

    # Set headers to trick external site into thinking this is a legitimate request
    headers = {
        'Content-Type': 'text/html',
        'X-Frame-Options': f'ALLOW-FROM https://{PROXY_ORIGIN_DOMAIN}',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        # Force the browser to allow this content from our domain
        'Access-Control-Allow-Origin': f'https://{PROXY_ORIGIN_DOMAIN}',
        'Referer': f"https://{PROXY_ORIGIN_DOMAIN}/",
    }

    response = fetch_content(target_url)

    if response is None or response.status_code != 200:
        return f"Failed to load initial page content from {target_url}", response.status_code

    # Parse the original URL and construct a dynamic base for asset requests
    parsed_base_url = target_url.split('?')[0]  # Remove any query string
    full_base_domain = PROXY_ORIGIN_DOMAIN if not parsed_base_url.startswith("http") else f"https://{PROXY_ORIGIN_DOMAIN}"
    dynamic_proxy_url = f"https://{full_base_domain}{parsed_base_url}"

    # Stream the HTML content while ensuring headers are correctly set for embedding
    return Response(response.content, status=200, headers=headers)

@app.route('/<path:subpath>')
def asset_proxy(subpath):
    """CATCH-ALL HANDLER for all assets (CSS, JS, images, data files)."""
    # Construct the final URL by appending the subpath to our dynamically derived base URL
    dynamic_target_url = f"https://{PROXY_ORIGIN_DOMAIN}{request.url_root.replace('/proxy', '')}/{subpath}"

    response = fetch_content(dynamic_target_url)

    if response is None or response.status_code != 200:
        return "Asset Not Found", 404

    # Apply necessary headers to ensure browser security policies are bypassed
    headers = {
        'Content-Type': response.headers.get('content-type', 'application/octet-stream'),
        'Access-Control-Allow-Origin': f'https://{PROXY_ORIGIN_DOMAIN}',
        'X-Frame-Options': f'ALLOW-FROM https://{PROXY_ORIGIN_DOMAIN}',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    }

    return Response(response.content, status=200, headers=headers)
