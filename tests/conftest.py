"""A small GTFS feed shaped like Caltrain's, for tests."""

import zipfile
from pathlib import Path

import pytest

# Three stations on a line: San Francisco, Millbrae (5000 m), and San Jose
# (20000 m). Train 101 is a southbound local, 102 a northbound express that
# runs past midnight, and 401 a weekend local.
TABLES = {
    "stops.txt": """\
stop_id,stop_name,location_type,parent_station
san_francisco,San Francisco Caltrain Station,1,
place_MLBR,Millbrae,1,
sj_diridon,San Jose Diridon Station,1,
sf_s,San Francisco Caltrain Southbound,0,san_francisco
sf_n,San Francisco Caltrain Northbound,0,san_francisco
mb_s,Millbrae Caltrain Southbound,0,place_MLBR
mb_n,Millbrae Caltrain Northbound,0,place_MLBR
sj_s,San Jose Diridon Caltrain Southbound,0,sj_diridon
sj_n,San Jose Diridon Caltrain Northbound,0,sj_diridon
""",
    "routes.txt": """\
route_id,route_short_name
1,Local Weekday
2,Express
3,Local Weekend
4,Mystery
""",
    "trips.txt": """\
route_id,service_id,trip_id,trip_short_name,direction_id
1,weekday,t101,101,1
2,weekday,t102,102,0
3,weekend,t401,401,1
4,holiday,t901,,0
""",
    "stop_times.txt": """\
trip_id,arrival_time,departure_time,stop_id,stop_sequence,shape_dist_traveled
t101,06:00:00,06:00:00,sf_s,1,0
t101,06:10:00,06:10:00,mb_s,2,5000
t101,06:40:00,06:40:00,sj_s,3,20000
t102,24:00:00,24:00:00,sj_n,1,0
t102,24:45:00,24:45:00,sf_n,2,20100
t401,09:00:00,09:00:00,sf_s,1,0
t401,09:12:00,09:12:00,mb_s,2,5000
t901,12:00:00,12:00:00,mb_n,1,0
t901,12:10:00,12:10:00,sf_n,2,5000
""",
    "calendar.txt": """\
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
weekday,1,1,1,1,1,0,0,20260101,20261231
weekend,0,0,0,0,0,1,1,20260101,20261231
""",
    "calendar_dates.txt": """\
service_id,date,exception_type
weekday,20261126,2
holiday,20261126,1
""",
}


def write_feed(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in TABLES.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


@pytest.fixture
def feed_dir(tmp_path: Path) -> Path:
    return write_feed(tmp_path / "feed")


@pytest.fixture
def feed_zip(tmp_path: Path) -> Path:
    path = tmp_path / "feed.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in TABLES.items():
            archive.writestr(name, text)
    return path
