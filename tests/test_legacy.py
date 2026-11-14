"""Tests for reading 2017-style feeds."""

import datetime as dt
from pathlib import Path

import pytest

from caltrain_schedule.gtfs import (
    Feed,
    load_feed,
    services_on_date,
    services_on_weekday,
    station_positions,
)
from caltrain_schedule.legacy import MILEPOSTS_2017, fill_positions


def test_legacy_stops_map_to_station_ids(legacy_dir: Path) -> None:
    feed = load_feed(legacy_dir)
    trips = {trip.trip_id: trip for trip in feed.trips}
    assert [stop.station_id for stop in trips["w101"].stop_times] == [
        "san_francisco",
        "place_MLBR",
        "atherton",
        "sj_diridon",
    ]
    assert feed.stations["atherton"].name == "Atherton"
    assert feed.stations["san_francisco"].name == "San Francisco"


def test_legacy_bus_trips_are_dropped(legacy_dir: Path) -> None:
    assert "bus" not in {trip.trip_id for trip in load_feed(legacy_dir).trips}


def test_regular_weekday_service_ignores_removed_saturday_service(legacy_dir: Path) -> None:
    feed = load_feed(legacy_dir)
    # The calendar flags put Saturday service on Wednesdays; calendar_dates
    # removes it.
    assert services_on_date(feed, dt.date(2017, 7, 19)) == {"Weekday"}
    assert services_on_weekday(feed, "wednesday") == {"Weekday"}
    assert services_on_weekday(feed, "saturday") == {"Saturday"}


def test_station_positions_needs_shape_distances(legacy_dir: Path) -> None:
    with pytest.raises(ValueError, match="shape_dist_traveled"):
        station_positions(load_feed(legacy_dir), "san_francisco")


def test_fill_positions_interpolates_between_neighbors() -> None:
    positions = {"place_MLBR": 13.0, "sj_diridon": 47.0}
    filled = fill_positions(positions)
    fraction = (MILEPOSTS_2017["atherton"] - 13.7) / (46.9 - 13.7)
    assert filled["atherton"] == pytest.approx(13.0 + fraction * 34.0)
    assert filled["place_MLBR"] == 13.0


def test_fill_positions_extends_past_the_ends() -> None:
    filled = fill_positions({"place_MLBR": 13.0}, {"place_MLBR": 13.7, "a": 10.7, "b": 20.7})
    assert filled == pytest.approx({"place_MLBR": 13.0, "a": 10.0, "b": 20.0})


def test_fill_positions_needs_a_known_station() -> None:
    assert fill_positions({"nowhere": 1.0}) == {"nowhere": 1.0}


def test_unknown_stop_without_parent_is_its_own_station(legacy_dir: Path) -> None:
    feed = load_feed(legacy_dir)
    assert "999" not in feed.stations


def test_services_on_weekday_without_services() -> None:
    assert services_on_weekday(Feed({}, (), {}, {}), "monday") == set()
