"""Tests for drawing Marey charts."""

from pathlib import Path

import matplotlib as mpl
import numpy as np

mpl.use("Agg")

import matplotlib.pyplot as plt
import pytest
from matplotlib.offsetbox import AnchoredOffsetbox

from caltrain_schedule.gtfs import load_feed, station_positions
from caltrain_schedule.plot import (
    FADED_ALPHA,
    STATION_COLOR,
    ChartOptions,
    edge_limit,
    hour_label,
    key_entries,
    key_names,
    plot_marey,
    route_color,
    spread_labels,
    time_range,
)


def test_route_color_falls_back_to_grey() -> None:
    assert route_color("Express") == "#e41a1c"
    assert route_color("Mystery") == "#999999"


def test_hour_label_names_noon_and_midnight() -> None:
    hours = (4, 11, 12, 13, 23, 24, 25, 26)
    expected = ["4", "11", "Noon", "13", "23", "Midnight", "1", "2"]
    assert [hour_label(hour) for hour in hours] == expected


def test_time_range_rejects_no_trips() -> None:
    with pytest.raises(ValueError, match="no trips"):
        time_range([])


def test_plot_marey_fades_other_direction(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    trips = [trip for trip in feed.trips if trip.service_id == "weekday"]
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(direction="south")
    plot_marey(ax, trips, feed.stations, positions, options)

    alphas = {line.get_label(): line.get_alpha() for line in ax.get_lines() if line.get_label()}
    assert alphas["Train 101"] == 1.0
    assert alphas["Train 102"] == FADED_ALPHA
    colors = {text.get_text(): text.get_color() for text in ax.texts}
    assert colors == dict.fromkeys(("San Francisco", "Millbrae", "San Jose Diridon"), STATION_COLOR)
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


def test_edge_limit_pads_past_the_outermost_station() -> None:
    # San Jose Diridon at 46.8 mi, Tamien 1.8 mi farther: pad past Tamien.
    assert edge_limit(46.8, [0.0, 46.8, 48.6], 1) == pytest.approx(50.6)
    # Gilroy is the last station.
    assert edge_limit(76.8, [0.0, 76.8], 1) == pytest.approx(78.8)
    # San Francisco at the top, with only stations south of it.
    assert edge_limit(0.0, [0.0, 1.6], -1) == pytest.approx(-2.0)
    # A station farther than the pad does not move the limit.
    assert edge_limit(46.8, [46.8, 51.7], 1) == pytest.approx(48.8)
    # Close stations chain: each is within the pad of the one before.
    assert edge_limit(10.0, [10.0, 11.5, 13.0, 16.0], 1) == pytest.approx(15.0)


def test_spread_labels_leaves_spaced_labels() -> None:
    assert spread_labels([0.0, 5.0, 10.0], min_gap=1.0) == [0.0, 5.0, 10.0]


def test_spread_labels_centers_crowded_groups() -> None:
    spread = spread_labels([0.0, 10.0, 10.2, 10.4, 12.0], min_gap=1.0)
    # The last four merge and center on their mean, 10.65.
    assert spread == pytest.approx([0.0, 9.15, 10.15, 11.15, 12.15])


def test_spread_labels_moves_a_close_pair_equally() -> None:
    assert spread_labels([10.0, 10.5], min_gap=1.0) == pytest.approx([9.75, 10.75])


def test_plot_marey_names_stations_in_view_on_the_left(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(bottom_station="place_MLBR")
    plot_marey(ax, feed.trips, feed.stations, positions, options)
    # San Jose is out of view, so it gets no name and does not stretch the axis.
    assert ax.get_ylim()[0] < positions["sj_diridon"]
    assert [text.get_text() for text in ax.texts] == ["San Francisco", "Millbrae"]
    assert all(text.get_horizontalalignment() == "right" for text in ax.texts)
    plt.close(fig)


def test_plot_marey_puts_names_with_room_on_their_lines(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    plot_marey(ax, feed.trips, feed.stations, positions, ChartOptions())
    names = {text.get_text(): text.get_position()[1] for text in ax.texts}
    assert names["Millbrae"] == pytest.approx(positions["place_MLBR"])
    # Every named station has a grid line.
    millbrae = positions["place_MLBR"]
    assert any(np.array_equal(line.get_ydata(), [millbrae, millbrae]) for line in ax.get_lines())
    plt.close(fig)


def test_key_entries_merge_and_order_routes() -> None:
    routes = ["South County", "Local Weekend", "Express", "Local Weekday", "Mystery", "Limited"]
    assert key_entries(routes) == [
        ("Local", "#377eb8"),
        ("Limited", "#4daf4a"),
        ("Express", "#e41a1c"),
        ("South County", "#984ea3"),
        ("Mystery", "#999999"),
    ]


def test_plot_marey_draws_key_unless_turned_off(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    trips = [trip for trip in feed.trips if trip.service_id == "weekday"]
    for key, expected in ((True, [["Local", "Express"]]), (False, [])):
        fig, ax = plt.subplots()
        plot_marey(ax, trips, feed.stations, positions, ChartOptions(key=key))
        keys = [key_names(artist) for artist in ax.artists if isinstance(artist, AnchoredOffsetbox)]
        assert keys == expected
        plt.close(fig)
