from flask import Flask, request, Response
import requests

app = Flask(__name__)

# --- CONFIGURATION ---
PROXY_ORIGIN_DOMAIN = "http://itchproxy-production.up.railway.app" # MUST BE THE DOMAIN OF YOUR PARENT SITE
TARGET_SITE_BASE_URL = "https://html-classic.itch.zone/html/6957140/BR_WEBGL_NO_WRONG_DRONG/"
# ---------------------

def fetch_content(url):
    """Helper function to safely fetch content from a given external URL."""
    try:
        print(f"Fetching content from: {url}")
        response = requests.get(url, timeout=15)
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {str(e)}")
        return None

@app.route('/proxy')
def proxy():
    """
    Accepts the full target URL via a query parameter 'url' and proxies the request.
    Example call: /proxy?url=https%3A%2F%2Fexternal-site.com%2Fpage1
    """
    # 1. Get the full target URL from the query parameters
    target_url = request.args.get('url')

    if not target_url:
        return "Error: Missing 'url' parameter in the request.", 400

    print(f"Proxying request for: {target_url}")

    try:
        # 2. Fetch the actual content from the target URL
        response = requests.get(target_url, timeout=15)

        if response.status_code != 200:
            return f"Error fetching external content: Status {response.status_code}. Details: {response.reason}", response.status_code

        # 3. Set crucial headers to simulate local origin and bypass protections
        headers = {
            'Content-Type': response.headers.get('content-type', 'text/html'),
            # This is essential for frame bypassing common security measures (X-Frame)
            'X-Frame-Options': f'ALLOW-FROM http://{PROXY_ORIGIN_DOMAIN}',
            'Referer': f"http://{PROXY_ORIGIN_DOMAIN}/" # Simulate the parent page as referrer
        }

        # 4. Return the content stream, allowing the browser to display it locally
        return Response(response.content, status=200, headers=headers)

    except requests.exceptions.RequestException as e:
        return f"Proxy connection error accessing {target_url}: {str(e)}", 503

@app.route('/<path:subpath>')
def asset_proxy(subpath):
    """
    CATCH-ALL HANDLER for all assets (CSS, JS, images, data files).
    This route intercepts requests like /Build/file.data.gz or /styles/main.css
    and assumes they are relative to the TARGET_SITE_BASE_URL.
    """
    # Reconstruct the full URL of the asset we need to fetch (e.g., https://external-site.com/Build/file.data.gz)
    asset_target_url = f"{TARGET_SITE_BASE_URL}{subpath}"

    response = fetch_content(asset_target_url)

    if response is None or response.status_code != 200:
         # Return a proper 404 if the asset cannot be found at the external location
        return f"Asset Not Found: {subpath}", 404

    print(f"Successfully proxied asset: {asset_target_url}")

    # --- Apply Headers for Asset Content ---
    headers = {
        'Content-Type': response.headers.get('content-type', 'application/octet-stream'),
        # Crucial: We rewrite the headers so the browser thinks this file came from us.
        'X-Frame-Options': f'ALLOW-FROM http://{PROXY_ORIGIN_DOMAIN}',
        'Referer': f"http://{PROXY_ORIGIN_DOMAIN}/",
    }

    # We return the raw content, preserving mime types and data integrity
    return Response(response.content, status=200, headers=headers)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
