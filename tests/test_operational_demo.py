import importlib.util
from pathlib import Path


def test_real_cli_replay_failure_and_recovery(tmp_path):
    spec = importlib.util.spec_from_file_location("operational_demo", Path(__file__).parents[1] / "scripts/operational_demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    events = demo.demonstrate(tmp_path)
    assert [e["exit_code"] == 0 for e in events] == [True, True, False, True]
    assert events[2]["runs"][-1]["status"] == "FAILED"
    assert events[3]["runs"][-1]["status"] == "SUCCEEDED"
    assert (tmp_path / "operational-demo.html").exists()
