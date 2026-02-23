"""Tests for collection run summary (S2.5)."""

import json
from io import StringIO

from src.collector import print_summary
from src.storage import save_run_summary


def _make_summary(**overrides):
    """Create a summary dict with sensible defaults, overridable by kwargs."""
    base = {
        "run_timestamp": "2026-02-22T12:00:00",
        "total_tweets": 25,
        "new_tweets": 20,
        "duplicates_skipped": 5,
        "images_downloaded": 10,
        "images_failed": 0,
        "scroll_count": 4,
        "run_time_seconds": 30.5,
        "stop_reason": "Reached max_tweets limit (50)",
        "warnings": [],
    }
    base.update(overrides)
    return base


# --- save_run_summary tests ---


def test_save_run_summary_creates_file(tmp_path):
    """First summary creates run_log.json with a one-element array."""
    summary = _make_summary()
    path = save_run_summary(summary, str(tmp_path))

    assert path.exists()
    entries = json.loads(path.read_text())
    assert len(entries) == 1
    assert entries[0]["total_tweets"] == 25


def test_save_run_summary_appends(tmp_path):
    """Multiple summaries append to the same array."""
    save_run_summary(_make_summary(total_tweets=10), str(tmp_path))
    save_run_summary(_make_summary(total_tweets=20), str(tmp_path))
    path = save_run_summary(_make_summary(total_tweets=30), str(tmp_path))

    entries = json.loads(path.read_text())
    assert len(entries) == 3
    assert [e["total_tweets"] for e in entries] == [10, 20, 30]


def test_save_run_summary_file_location(tmp_path):
    """run_log.json is saved in today's date directory."""
    path = save_run_summary(_make_summary(), str(tmp_path))
    assert path.name == "run_log.json"
    # Parent should be a date-formatted directory
    assert path.parent.name  # non-empty date dir name


def test_save_run_summary_preserves_all_fields(tmp_path):
    """All summary fields survive the save/load round-trip."""
    summary = _make_summary(
        warnings=["No tweets parsed", "2 image downloads failed"],
        images_failed=2,
    )
    path = save_run_summary(summary, str(tmp_path))

    entries = json.loads(path.read_text())
    saved = entries[0]
    assert saved["run_timestamp"] == "2026-02-22T12:00:00"
    assert saved["new_tweets"] == 20
    assert saved["duplicates_skipped"] == 5
    assert saved["images_downloaded"] == 10
    assert saved["images_failed"] == 2
    assert saved["scroll_count"] == 4
    assert saved["run_time_seconds"] == 30.5
    assert saved["stop_reason"] == "Reached max_tweets limit (50)"
    assert len(saved["warnings"]) == 2


def test_save_run_summary_pretty_printed(tmp_path):
    """run_log.json is pretty-printed (indented)."""
    path = save_run_summary(_make_summary(), str(tmp_path))
    text = path.read_text()
    # Pretty-printed JSON has indentation — at least some lines start with spaces
    assert any(line.startswith("  ") for line in text.splitlines())


def test_save_run_summary_with_warnings(tmp_path):
    """Warnings are preserved in run_log.json."""
    summary = _make_summary(warnings=["No GraphQL responses after extended wait"])
    path = save_run_summary(summary, str(tmp_path))

    entries = json.loads(path.read_text())
    assert entries[0]["warnings"] == ["No GraphQL responses after extended wait"]


def test_save_run_summary_empty_warnings(tmp_path):
    """Empty warnings list is saved correctly."""
    summary = _make_summary(warnings=[])
    path = save_run_summary(summary, str(tmp_path))

    entries = json.loads(path.read_text())
    assert entries[0]["warnings"] == []


# --- print_summary tests ---


def test_print_summary_outputs_key_fields(capsys):
    """print_summary includes all key stats in output."""
    summary = _make_summary(
        total_tweets=25,
        new_tweets=20,
        duplicates_skipped=5,
        images_downloaded=10,
        images_failed=0,
        scroll_count=4,
        run_time_seconds=30.5,
        stop_reason="Reached max_tweets limit (50)",
    )
    print_summary(summary)
    output = capsys.readouterr().out

    assert "25" in output  # total tweets
    assert "20" in output  # new tweets
    assert "5" in output  # dupes
    assert "10" in output  # images
    assert "4" in output  # scrolls
    assert "30.5" in output  # run time
    assert "max_tweets" in output  # stop reason


def test_print_summary_shows_warnings(capsys):
    """print_summary displays warnings when present."""
    summary = _make_summary(warnings=["3 image download(s) failed"])
    print_summary(summary)
    output = capsys.readouterr().out

    assert "3 image download(s) failed" in output
    assert "Warnings" in output


def test_print_summary_no_warnings_section_when_empty(capsys):
    """print_summary omits warnings section when list is empty."""
    summary = _make_summary(warnings=[])
    print_summary(summary)
    output = capsys.readouterr().out

    assert "Warnings" not in output


def test_print_summary_has_header(capsys):
    """print_summary includes a visual header."""
    print_summary(_make_summary())
    output = capsys.readouterr().out

    assert "Collection Run Summary" in output
    assert "=" in output  # separator line
