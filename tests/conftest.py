"""A small GTFS feed shaped like Caltrain's, for tests."""

import datetime as dt
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

# A feed shaped like Caltrain's 2017 ones: platforms named after their
# station with no parent stations, no shape distances, a shuttle bus, and a
# Saturday service flagged for every day but removed from weekdays.
LEGACY_TABLES = {
    "stops.txt": """\
stop_id,stop_name,location_type,parent_station
70011,San Francisco Caltrain,0,
70012,San Francisco Caltrain,0,
70061,Millbrae Caltrain,0,
70151,Atherton Caltrain,0,
70261,San Jose Diridon Caltrain,0,
777402,San Jose Caltrain Station,0,
777403,Tamien Caltrain Station,0,
999,Mystery Stop,0,
""",
    "routes.txt": """\
route_id,route_short_name,route_type
Lo,Local,2
Bu,Baby Bullet,2
TaSj,TaSj,3
""",
    "trips.txt": """\
route_id,service_id,trip_id,trip_short_name,direction_id
Lo,Weekday,w101,101,1
Bu,Weekday,w305,305,0
Lo,Saturday,s421,421,1
TaSj,Weekday,bus,90,1
""",
    "stop_times.txt": """\
trip_id,arrival_time,departure_time,stop_id,stop_sequence
w101,06:00:00,06:00:00,70012,1
w101,06:20:00,06:20:00,70061,2
w101,06:40:00,06:40:00,70151,3
w101,07:20:00,07:20:00,70261,4
w305,08:00:00,08:00:00,70261,1
w305,08:50:00,08:50:00,70011,2
s421,09:00:00,09:00:00,70012,1
s421,09:20:00,09:20:00,70061,2
bus,10:00:00,10:00:00,777402,1
bus,10:10:00,10:10:00,777403,2
""",
    "calendar.txt": """\
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
Weekday,1,1,1,1,1,0,0,20170717,20190719
Saturday,1,1,1,1,1,1,1,20170715,20190720
""",
    "calendar_dates.txt": """\
service_id,date,exception_type
""",
}
# The July 2017 feed removes Saturday service from every weekday.
_first_monday = dt.date(2017, 7, 17)
LEGACY_TABLES["calendar_dates.txt"] += "".join(
    f"Saturday,{_first_monday + dt.timedelta(weeks=week, days=day):%Y%m%d},2\n"
    for week in range(60)
    for day in range(5)
)


def write_feed(directory: Path, tables: dict[str, str] = TABLES) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in tables.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


@pytest.fixture
def feed_dir(tmp_path: Path) -> Path:
    return write_feed(tmp_path / "feed")


@pytest.fixture
def legacy_dir(tmp_path: Path) -> Path:
    return write_feed(tmp_path / "legacy", LEGACY_TABLES)


@pytest.fixture
def feed_zip(tmp_path: Path) -> Path:
    path = tmp_path / "feed.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in TABLES.items():
            archive.writestr(name, text)
    return path


@pytest.fixture
def feed_tables() -> dict[str, str]:
    return dict(TABLES)
