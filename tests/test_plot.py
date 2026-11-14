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
    OTHER_STATION_COLOR,
    STATION_COLOR,
    ChartOptions,
    edge_limit,
    fit_labels,
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
    options = ChartOptions(direction="south", labeled_stations=("san_francisco", "nowhere"))
    plot_marey(ax, trips, feed.stations, positions, options)

    alphas = {line.get_label(): line.get_alpha() for line in ax.get_lines() if line.get_label()}
    assert alphas["Train 101"] == 1.0
    assert alphas["Train 102"] == FADED_ALPHA
    colors = {text.get_text(): text.get_color() for text in ax.texts}
    assert colors == {
        "San Francisco": STATION_COLOR,
        "Millbrae": OTHER_STATION_COLOR,
        "San Jose Diridon": OTHER_STATION_COLOR,
    }
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


def test_spread_labels_leaves_spaced_labels() -> None:
    assert spread_labels([0.0, 5.0, 10.0], min_gap=1.0) == [0.0, 5.0, 10.0]


def test_spread_labels_centers_crowded_groups() -> None:
    spread = spread_labels([0.0, 10.0, 10.2, 10.4, 12.0], min_gap=1.0)
    # The last four merge and center on their mean, 10.65.
    assert spread == pytest.approx([0.0, 9.15, 10.15, 11.15, 12.15])


def test_spread_labels_moves_light_labels_more() -> None:
    spread = spread_labels([10.0, 10.5], min_gap=1.0, weights=[1.0, 9.0])
    # The heavy label moves 0.05 and the light one 0.45: nine times as far.
    assert spread == pytest.approx([9.55, 10.55])


def test_plot_marey_names_stations_in_view_on_the_left(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(bottom_station="place_MLBR", labeled_stations=("sj_diridon",))
    plot_marey(ax, feed.trips, feed.stations, positions, options)
    # San Jose is out of view, so it gets no name and does not stretch the axis.
    assert ax.get_ylim()[0] < positions["sj_diridon"]
    assert [text.get_text() for text in ax.texts] == ["San Francisco", "Millbrae"]
    assert all(text.get_horizontalalignment() == "right" for text in ax.texts)
    plt.close(fig)


def test_fit_labels_drops_minor_labels_that_crowd_major_ones() -> None:
    # A minor label between two close major labels does not fit, and one
    # with room does.
    fitted = fit_labels(
        [0.0, 0.8, 1.5, 5.0],
        [True, False, True, False],
        min_gap=1.0,
        max_major_shift=0.1,
    )
    assert fitted == pytest.approx({0: 0.0, 2: 1.5, 3: 5.0})


def test_plot_marey_can_leave_out_other_names(feed_dir: Path) -> None:
    feed = load_feed(feed_dir)
    positions = station_positions(feed, "san_francisco")
    fig, ax = plt.subplots()
    options = ChartOptions(labeled_stations=("san_francisco",), other_names=False)
    plot_marey(ax, feed.trips, feed.stations, positions, options)
    assert [text.get_text() for text in ax.texts] == ["San Francisco"]
    # Millbrae keeps its grid line.
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
