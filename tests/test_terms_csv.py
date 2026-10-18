"""How repeated words are handled, and that the import and the build agree on every address."""
from pathlib import Path

import pytest

from terms_csv import load_terms, slugify


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "terms.csv"
    path.write_text("term,definition,vibe\n" + body, encoding="utf-8")
    return path


def slugs(rows):
    return [r["slug"] for r in rows]


def test_plain_terms_keep_their_plain_slug(tmp_path):
    rows, report = load_terms(write(tmp_path, "Love,affection,a\nHate,the opposite,b\n"))
    assert slugs(rows) == ["love", "hate"]
    assert report == {"skipped": [], "kept": []}


def test_exact_repeat_is_skipped_ignoring_case_and_spacing(tmp_path):
    rows, report = load_terms(write(tmp_path, 'love,A strong feeling.,a\nLove,"a  strong   feeling.",b\n'))
    assert slugs(rows) == ["love"]
    assert report["skipped"] == [(3, "Love", 2)]


def test_same_word_different_definition_is_kept_and_named_by_vibe(tmp_path):
    rows, report = load_terms(write(tmp_path, "love,one,quote topics\nlove,two,collocations\n"))
    assert slugs(rows) == ["love", "love-collocations"]
    assert [k[2] for k in report["kept"]] == ["love-collocations"]


def test_same_vibe_or_no_vibe_falls_back_to_a_number(tmp_path):
    rows, _ = load_terms(write(tmp_path, "love,one,v\nlove,two,v\nlove,three,\nlove,four,\n"))
    assert slugs(rows) == ["love", "love-v", "love-2", "love-3"]


def test_punctuation_variants_of_a_word_share_a_base_slug(tmp_path):
    rows, _ = load_terms(write(tmp_path, "love,one,a\nLove!,two,b\n"))
    assert slugs(rows) == ["love", "love-b"]


def test_a_real_term_named_like_a_generated_slug_gets_its_own_unique_slug(tmp_path):
    rows, _ = load_terms(write(tmp_path, "love,one,\nlove,two,\nlove-2,three,\n"))
    assert len(set(slugs(rows))) == 3


def test_slugs_are_always_unique(tmp_path):
    body = "".join(f"w{i % 7},def{i},v{i % 3}\n" for i in range(200))
    rows, _ = load_terms(write(tmp_path, body))
    assert len(set(slugs(rows))) == len(rows)


def test_broken_rows_still_fail_with_the_line_number(tmp_path):
    for body, needle in [("a,,x\n", ":2:"), (",def,x\n", ":2:"), ("!!!,def,x\n", "no usable characters")]:
        with pytest.raises(SystemExit) as e:
            load_terms(write(tmp_path, body))
        assert needle in str(e.value)


def test_missing_columns_fail(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text("word,meaning\nlove,x\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_terms(path)


def test_blank_lines_are_ignored(tmp_path):
    rows, _ = load_terms(write(tmp_path, "a,one,x\n\nb,two,y\n\n"))
    assert slugs(rows) == ["a", "b"]


def test_slugify():
    assert slugify("  Ice Cream!! ") == "ice-cream"
    assert slugify("!!!") == ""
