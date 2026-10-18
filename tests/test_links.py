"""Web addresses inside definitions: linking, wrapping, safety."""
from links import linkify_html, plain_text, strip_urls


def test_http_and_https_addresses_become_safe_links():
    out = linkify_html("see https://example.com/a?b=1&c=2 now")
    assert 'href="https://example.com/a?b=1&amp;c=2"' in out
    assert 'target="_blank"' in out and "noopener noreferrer nofollow" in out
    assert out.startswith("see ") and out.endswith(" now")


def test_www_addresses_get_https():
    assert 'href="https://www.example.org/x"' in linkify_html("go to www.example.org/x")


def test_other_schemes_and_markup_stay_plain_text():
    out = linkify_html("javascript:alert(1) <script>x</script> ftp://a.b/c")
    assert "<a " not in out and "<script>" not in out and "&lt;script&gt;" in out


def test_trailing_punctuation_and_unbalanced_brackets_are_not_part_of_the_link():
    assert 'href="https://a.io/x"' in linkify_html("(see https://a.io/x).")
    assert 'href="https://en.wikipedia.org/wiki/Index_(disambiguation)"' in linkify_html("https://en.wikipedia.org/wiki/Index_(disambiguation).")


def test_break_hints_never_split_an_html_entity():
    out = linkify_html("https://a.io/p?x=1&y=2&z=3")
    assert "&amp;<wbr>y=" in out and "&<wbr>amp;" not in out


def test_plain_text_replaces_addresses_with_the_site_name():
    assert plain_text("Collocations: https://dictionary.cambridge.org/collocation/english/love") == "Collocations: dictionary.cambridge.org"
    assert plain_text("Visit www.example.org/page, then stop.") == "Visit example.org, then stop."


def test_strip_urls_removes_addresses_so_their_pieces_are_not_vocabulary():
    assert "cambridge" not in strip_urls("about https://dictionary.cambridge.org/x and more").lower()
