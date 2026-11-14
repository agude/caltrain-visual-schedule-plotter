"""Tests for reading GTFS feeds."""

import datetime as dt
from pathlib import Path

import pytest

from caltrain_schedule.gtfs import (
    METERS_PER_MILE,
    load_feed,
    parse_time,
    services_on_date,
    services_on_weekday,
    station_name,
    station_positions,
)


def test_parse_time_keeps_after_midnight_hours() -> None:
    assert parse_time("06:30:15") == 6 * 3600 + 30 * 60 + 15
    assert parse_time("25:00:00") == 25 * 3600


@pytest.mark.parametrize(
    ("stop_name", "expected"),
    [
        ("Palo Alto Station", "Palo Alto"),
        ("San Jose Diridon Station", "San Jose Diridon"),
        ("Tamien Caltrain Station", "Tamien"),
        ("Millbrae", "Millbrae"),
    ],
)
def test_station_name_drops_suffix(stop_name: str, expected: str) -> None:
    assert station_name(stop_name) == expected


def test_load_feed_reads_directory_and_zip(feed_dir: Path, feed_zip: Path) -> None:
    assert load_feed(feed_dir) == load_feed(feed_zip)


def test_load_feed_maps_platforms_to_stations(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    trips = {trip.trip_id: trip for trip in feed.trips}
    local = trips["t101"]
    assert [stop.station_id for stop in local.stop_times] == [
        "san_francisco",
        "place_MLBR",
        "sj_diridon",
    ]
    assert local.direction == "south"
    assert local.route == "Local Weekday"
    assert trips["t102"].direction == "north"
    assert trips["t901"].train == "t901"
    assert feed.stations["sj_diridon"].name == "San Jose Diridon"


def test_services_on_weekday(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    assert services_on_weekday(feed, "monday") == {"weekday"}
    assert services_on_weekday(feed, "sunday") == {"weekend"}
    with pytest.raises(ValueError, match="unknown day"):
        services_on_weekday(feed, "funday")


def test_services_on_date_applies_exceptions(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    assert services_on_date(feed, dt.date(2026, 11, 25)) == {"weekday"}
    assert services_on_date(feed, dt.date(2026, 11, 26)) == {"holiday"}
    assert services_on_date(feed, dt.date(2027, 1, 6)) == set()


def test_station_positions_follow_the_line(feed_dir: Path) -> None:
    positions = station_positions(load_feed(feed_dir), "san_francisco")
    assert positions["san_francisco"] == 0
    assert positions["place_MLBR"] == pytest.approx(5000 / METERS_PER_MILE)
    # The local measures San Jose at 20000 m through Millbrae, and the
    # express at 20100 m directly. Either path is accurate enough.
    assert 20000 <= positions["sj_diridon"] * METERS_PER_MILE <= 20100


def test_station_positions_from_a_middle_station(feed_dir: Path) -> None:
    positions = station_positions(load_feed(feed_dir), "place_MLBR")
    assert positions["san_francisco"] == pytest.approx(-5000 / METERS_PER_MILE)
    assert positions["sj_diridon"] > 0


def test_station_positions_rejects_unknown_origin(feed_dir: Path) -> None:
    with pytest.raises(ValueError, match="origin"):
        station_positions(load_feed(feed_dir), "gilroy")
