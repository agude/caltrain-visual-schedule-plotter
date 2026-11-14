"""Tests for the caltrain-schedule command-line interface."""

import argparse
import io
import runpy
import sys
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


def test_fetch_writes_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requested: list[str] = []

    def fake_urlopen(url: str) -> io.BytesIO:
        requested.append(url)
        return io.BytesIO(b"zip bytes")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    output = tmp_path / "data" / "feed.zip"
    assert main(["fetch", str(output), "--url", "https://example.com/feed.zip"]) == 0
    assert requested == ["https://example.com/feed.zip"]
    assert output.read_bytes() == b"zip bytes"


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
