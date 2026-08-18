"""Regression: rg context lines must never be mistaken for match lines.

A match line uses "path:line:content"; a context line (from --context) uses
"path-line-content" instead. If a matched file's content itself contains a
"digit:digit" pattern (e.g. an ISO timestamp inside JSON), a context line can
be misparsed into a bogus SourceLocation unless the path is anchored to stop
at the first ':' or whitespace.
"""

from reposcout.executors.ripgrep import _match_locations


def test_context_line_with_embedded_colon_digit_is_not_a_match_location() -> None:
    stdout = "src/a.py:3:def target():\nsrc/a.py-4-    # seen at 12:00:00.134Z in the log\n"

    locations = _match_locations(stdout)

    assert [(loc.path, loc.start_line, loc.end_line) for loc in locations] == [
        ("src/a.py", 3, 3),
    ]


def test_match_line_content_with_embedded_colon_digit_is_still_one_location() -> None:
    stdout = 'src/a.py:3:{"timestamp": "12:00:00.134Z"}\n'

    locations = _match_locations(stdout)

    assert [(loc.path, loc.start_line, loc.end_line) for loc in locations] == [
        ("src/a.py", 3, 3),
    ]
