"""Tests for the caltrain-schedule command-line interface."""

import argparse
import io
import runpy
import sys
import zipfile
from pathlib import Path

import pytest

from caltrain_schedule import __version__
from caltrain_schedule.cli import main, parse_hour


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"caltrain-schedule {__version__}\n"


def test_command_is_required() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2


def test_module_entry_point_runs_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["caltrain-schedule", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("caltrain_schedule", run_name="__main__")
    assert exit_info.value.code == 0


def test_parse_hour() -> None:
    assert parse_hour("25:30") == 25.5
    for bad in ("7", "7:xx", "7:60"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_hour(bad)


def serve_zip(monkeypatch: pytest.MonkeyPatch, entries: dict[str, str]) -> list[str]:
    """Make urlopen return a zip of ``entries``, and record the URLs requested."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    requested: list[str] = []

    def fake_urlopen(url: str) -> io.BytesIO:
        requested.append(url)
        return io.BytesIO(buffer.getvalue())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return requested


def test_fetch_unpacks_feed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, feed_tables: dict[str, str]
) -> None:
    requested = serve_zip(monkeypatch, feed_tables)
    output = tmp_path / "data" / "caltrain-20261113"
    assert main(["fetch", str(output), "--url", "https://example.com/feed.zip"]) == 0
    assert requested == ["https://example.com/feed.zip"]
    assert sorted(path.name for path in output.iterdir()) == sorted(feed_tables)
    assert (output / "stops.txt").read_text(encoding="utf-8") == feed_tables["stops.txt"]
    # Only the unpacked feed is left in data/: no staging directory.
    assert [path.name for path in output.parent.iterdir()] == ["caltrain-20261113"]


@pytest.mark.parametrize("name", ["../escape.txt", "sub/stops.txt", "/abs.txt"])
def test_fetch_refuses_entries_outside_the_feed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    serve_zip(monkeypatch, {"stops.txt": "", name: ""})
    output = tmp_path / "feed"
    with pytest.raises(SystemExit, match="refusing feed entry"):
        main(["fetch", str(output)])
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_fetch_refuses_existing_output(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="already exists"):
        main(["fetch", str(tmp_path)])


@pytest.mark.parametrize(
    "when",
    [
        [],
        ["--day", "weekend"],
        ["--day", "saturday"],
        ["--date", "2026-11-26"],
    ],
)
def test_plot_writes_image(feed_zip: Path, tmp_path: Path, when: list[str]) -> None:
    output = tmp_path / "out" / "chart.svg"
    assert main(["plot", str(feed_zip), str(output), *when]) == 0
    assert output.read_text(encoding="utf-8").startswith("<?xml")


def test_plot_accepts_chart_options(feed_dir: Path, tmp_path: Path) -> None:
    output = tmp_path / "chart.png"
    argv = [
        "plot",
        str(feed_dir),
        str(output),
        "--direction=north",
        "--start=05:00",
        "--end=25:00",
        "--bottom=place_MLBR",
        "--label=place_MLBR",
        "--title=Test",
    ]
    assert main(argv) == 0
    assert output.stat().st_size > 0


def test_plot_reports_no_trips(feed_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no trips run on 2030-01-01"):
        main(["plot", str(feed_dir), str(tmp_path / "x.png"), "--date", "2030-01-01"])


def test_plot_reports_unknown_station(feed_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="unknown station ID: nowhere"):
        main(["plot", str(feed_dir), str(tmp_path / "x.png"), "--bottom", "nowhere"])


def test_plot_legacy_feed_with_distances_from_another_feed(
    legacy_dir: Path, feed_zip: Path, tmp_path: Path
) -> None:
    output = tmp_path / "legacy.svg"
    argv = ["plot", str(legacy_dir), str(output), "--distances", str(feed_zip)]
    assert main(argv) == 0
    svg = output.read_text(encoding="utf-8")
    assert "Weekday, July 2017" in svg
    assert "Atherton" in svg


def test_plot_legacy_feed_needs_distances(legacy_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="shape_dist_traveled"):
        main(["plot", str(legacy_dir), str(tmp_path / "x.svg")])


def test_plot_names_chart_in_title(feed_zip: Path, tmp_path: Path) -> None:
    output = tmp_path / "chart.svg"
    assert main(["plot", str(feed_zip), str(output), "--name", "Weekday Morning"]) == 0
    assert "Weekday Morning, January 2026" in output.read_text(encoding="utf-8")


def test_plot_without_other_names(feed_zip: Path, tmp_path: Path) -> None:
    output = tmp_path / "chart.svg"
    argv = ["plot", str(feed_zip), str(output), "--label=san_francisco", "--no-other-names"]
    assert main(argv) == 0
    svg = output.read_text(encoding="utf-8")
    assert "San Francisco" in svg
    assert "Millbrae" not in svg


def test_plot_without_key(feed_zip: Path, tmp_path: Path) -> None:
    output = tmp_path / "chart.svg"
    assert main(["plot", str(feed_zip), str(output), "--no-key"]) == 0
    assert "Express" not in output.read_text(encoding="utf-8")
