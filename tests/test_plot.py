"""Tests for drawing Marey charts."""

from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import pytest

from caltrain_schedule.gtfs import load_feed, station_positions
from caltrain_schedule.plot import (
    FADED_ALPHA,
    ChartOptions,
    edge_limit,
    hour_label,
    plot_marey,
    route_color,
    time_range,
)


def test_route_color_falls_back_to_grey() -> None:
    assert route_color("Express") == "#e41a1c"
    assert route_color("Mystery") == "#999999"


def test_hour_label_wraps_after_midnight() -> None:
    assert [hour_label(hour) for hour in (4, 24, 25, 26)] == ["4", "24", "1", "2"]


def test_time_range_rejects_no_trips() -> None:
    with pytest.raises(ValueError, match="no trips"):
        time_range([])


def test_plot_marey_fades_other_direction(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    trips = [trip for trip in feed.trips if trip.service_id == "weekday"]
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(direction="south", labeled_stations=("san_francisco", "nowhere"))
    plot_marey(ax, trips, feed.stations, positions, options)

    alphas = {line.get_label(): line.get_alpha() for line in ax.get_lines() if line.get_label()}
    assert alphas["Train 101"] == 1.0
    assert alphas["Train 102"] == FADED_ALPHA
    assert [label.get_text() for label in ax.get_yticklabels()] == ["San Francisco"]
    # San Francisco is on top: the y axis runs downward.
    bottom, top = ax.get_ylim()
    assert bottom > top
    plt.close(fig)


def test_plot_marey_uses_given_hours(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(start_hour=5.5, end_hour=25.0)
    plot_marey(ax, feed.trips, feed.stations, positions, options)
    assert ax.get_xlim() == (5.5, 25.0)
    plt.close(fig)


def test_plot_marey_rejects_unknown_direction(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    fig, ax = plt.subplots()
    with pytest.raises(ValueError, match="direction"):
        plot_marey(ax, feed.trips, feed.stations, {}, ChartOptions(direction="east"))
    plt.close(fig)


def test_edge_limit_makes_room_for_a_close_station() -> None:
    # San Jose Diridon at 46.8 mi, Tamien 1.8 mi farther.
    assert edge_limit(46.8, [0.0, 46.8, 48.6], 1) == pytest.approx(49.6)
    # Gilroy is the last station.
    assert edge_limit(76.8, [0.0, 76.8], 1) == pytest.approx(78.8)
    # San Francisco at the top, with 22nd Street 1.6 mi south of it.
    assert edge_limit(0.0, [0.0, 1.6], -1) == pytest.approx(-2.0)
    # A station farther than the pad does not move the limit.
    assert edge_limit(46.8, [46.8, 51.7], 1) == pytest.approx(48.8)
