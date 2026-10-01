"""Configured Uvicorn entry point used by the portable launcher."""

import argparse
from pathlib import Path
import threading
from urllib.parse import urlencode
import webbrowser

import uvicorn

from app.core.config import API_HOST, API_PORT

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


def frontend_build_token(index_path: Path = FRONTEND_INDEX) -> str | None:
    """Return a stable token that changes whenever the built frontend changes."""
    try:
        return str(index_path.stat().st_mtime_ns)
    except OSError:
        return None


def browser_url(
    host: str = API_HOST,
    port: int = API_PORT,
    *,
    cache_token: str | None = None,
) -> str:
    """Return a local URL even when the server listens on a wildcard address."""
    normalized = (host or "127.0.0.1").strip()
    if normalized in {"0.0.0.0", "::", "[::]", "*"}:
        normalized = "127.0.0.1"
    elif ":" in normalized and not normalized.startswith("["):
        normalized = f"[{normalized}]"
    url = f"http://{normalized}:{int(port)}"
    if cache_token:
        url = f"{url}/?{urlencode({'v': cache_token})}"
    return url


def run(*, open_browser: bool = False) -> None:
    url = browser_url(cache_token=frontend_build_token())
    print(f"[server] Listening on {API_HOST}:{API_PORT}")
    print(f"[server] Browser URL: {url}")
    if open_browser:
        timer = threading.Timer(1.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the BioAI Agent backend")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="open the configured local URL after startup",
    )
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="print the browser URL without starting the server",
    )
    args = parser.parse_args()
    if args.print_url:
        print(browser_url(cache_token=frontend_build_token()))
        return
    run(open_browser=args.open_browser)


if __name__ == "__main__":
    main()
