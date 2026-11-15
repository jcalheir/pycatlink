import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location(
    "visits", Path(__file__).parents[1] / "custom_components" / "catlink" / "visits.py"
)
visits = importlib.util.module_from_spec(spec)
sys.modules["visits"] = visits
spec.loader.exec_module(visits)

TZ = ZoneInfo("Europe/Lisbon")


def log(i, t, event, w="5.3kg", d="107s", pet="223538", typ="WC"):
    return SimpleNamespace(id=str(i), type=typ, time=t, event=event, first_section=w,
                           second_section=d, sn_flag=0, pet_id=pet)


def test_parse_log_kinds_and_values():
    now = datetime(2026, 11, 15, 3, 30, tzinfo=timezone.utc)
    v = visits.parse_log(log(1, "02:40", "Nico pooped"), TZ, now)
    assert v.kind == "coco" and v.weight_kg == 5.3 and v.duration_s == 107
    assert v.when.isoformat() == "2026-11-15T02:40:00+00:00"
    assert v.attributes()["resumo"] == "cocó · 1 min 47 s · 5,3 kg"
    assert visits.parse_log(log(2, "02:10", "Nina peed", pet="223540"), TZ, now).kind == "xixi"
    assert visits.parse_log(log(3, "02:45", "Sensor cleaning", typ="RUN"), TZ, now) is None
    unknown = visits.parse_log(log(4, "01:00", "Unrecognized cat", pet="0"), TZ, now)
    assert unknown.pet_id is None and unknown.kind == "desconhecido"


def test_time_after_now_is_yesterday():
    now = datetime(2026, 11, 15, 0, 5, tzinfo=timezone.utc)
    v = visits.parse_log(log(5, "23:50", "Nico peed"), TZ, now)
    assert v.when.date().isoformat() == "2026-11-14"


def test_tracker_baseline_then_new_events():
    calls = []

    class Client:
        async def request_with_auto_login(self, path, method, parameters):
            calls.append(parameters["petId"])
            return {"data": {"toilet": {"times": 4, "peed": 3, "pood": 1,
                                        "weightAvg": 5.2, "durationAvg": 78.5,
                                        "healthStatus": "GOOD"}}}

    tr = visits.VisitTracker(Client(), TZ)
    now = datetime(2026, 11, 15, 3, 30, tzinfo=timezone.utc)
    st = asyncio.run(tr.update([log(1, "02:40", "Nico pooped")], ["223538"], now))
    assert st.new_visits == []  # baseline: no events for old logs
    assert st.last_visit["223538"].kind == "coco"
    assert st.today["223538"].visits == 4 and st.today["223538"].duration_avg_s == 78.5
    st = asyncio.run(tr.update([log(1, "02:40", "Nico pooped"), log(6, "03:20", "Nico peed")],
                               ["223538"], now))
    assert [v.log_id for v in st.new_visits] == ["6"]
    assert st.last_visit["223538"].kind == "xixi"
    assert len(calls) == 2  # new visit forces a refresh of today's summary
