"""Links inside definitions: find them, show them, keep them out of the vocabulary.

A definition may contain web addresses ("see https://example.com/a/b"). The graph
page and the term pages turn them into links (only http and https ever become
links), long addresses get break points after every / ? & = # so they wrap at
natural places, and link previews and cards show just the site name.
"""
import html
import re
from urllib.parse import urlsplit

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
_CLOSERS = {")": "(", "]": "[", "}": "{"}


def _trim(url: str) -> str:
    """Drop sentence punctuation that trails an address, and a closing bracket that has no opening one in it."""
    while url:
        c = url[-1]
        if c in ".,;:!?'\"" or (c in _CLOSERS and url.count(c) > url.count(_CLOSERS[c])):
            url = url[:-1]
        else:
            break
    return url


def _href(url: str) -> str | None:
    full = "https://" + url if url.lower().startswith("www.") else url
    parts = urlsplit(full)
    return full if parts.scheme in ("http", "https") and parts.netloc else None


def _shown(url: str) -> str:
    return re.sub(r"/$", "", re.sub(r"^www\.", "", re.sub(r"^https?://", "", url, flags=re.IGNORECASE), flags=re.IGNORECASE))


def _host(url: str) -> str:
    return re.sub(r"^www\.", "", (urlsplit(_href(url) or "").hostname or _shown(url)))


def _breakable(text: str) -> str:
    """Escape, with <wbr> hints after / ? & = # so a long address wraps at natural places."""
    return "<wbr>".join(html.escape(piece) for piece in re.split(r"(?<=[/?&=#])", text) if piece)


def linkify_html(text: str) -> str:
    """Escape `text` for HTML and turn its web addresses into links."""
    out, last = [], 0
    for m in URL_RE.finditer(text):
        url = _trim(m.group(0))
        href = _href(url) if url else None
        if not href:
            continue
        out.append(html.escape(text[last : m.start()]))
        out.append(
            f'<a class="link" href="{html.escape(href, quote=True)}" target="_blank" rel="noopener noreferrer nofollow">'
            f"{_breakable(_shown(url))}</a>"
        )
        last = m.start() + len(url)
    out.append(html.escape(text[last:]))
    return "".join(out)


def plain_text(text: str) -> str:
    """The text with each web address replaced by its site name, for descriptions and cards."""
    def swap(m: re.Match) -> str:
        url = _trim(m.group(0))
        return _host(url) + m.group(0)[len(url):] if url and _href(url) else m.group(0)
    return re.sub(r"\s+", " ", URL_RE.sub(swap, text)).strip()


def strip_urls(text: str) -> str:
    """The text without web addresses, so their pieces ("https", "www", "org") never count as vocabulary."""
    return URL_RE.sub(" ", text)
