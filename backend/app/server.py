"""Configured Uvicorn entry point used by the portable launcher."""

import argparse
import threading
import webbrowser

import uvicorn

from app.core.config import API_HOST, API_PORT


def browser_url(host: str = API_HOST, port: int = API_PORT) -> str:
    """Return a local URL even when the server listens on a wildcard address."""
    normalized = (host or "127.0.0.1").strip()
    if normalized in {"0.0.0.0", "::", "[::]", "*"}:
        normalized = "127.0.0.1"
    elif ":" in normalized and not normalized.startswith("["):
        normalized = f"[{normalized}]"
    return f"http://{normalized}:{int(port)}"


def run(*, open_browser: bool = False) -> None:
    url = browser_url()
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
        print(browser_url())
        return
    run(open_browser=args.open_browser)


if __name__ == "__main__":
    main()
