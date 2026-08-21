import json
from pathlib import Path

from n0jcg_air_band_scanner.catalog import AirbandCatalog
from n0jcg_air_band_scanner.fft_scan import score_channels, simulated_spectrum
from n0jcg_air_band_scanner import server

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_airport_lookup():
    catalog = AirbandCatalog(ROOT / "web/data/airband-channels.json")
    assert [row["code"] for row in catalog.airport_codes("kden")] == ["KDEN"]
    assert len(catalog.for_airport("KDEN")) == 3


def test_catalog_radius_lookup():
    catalog = AirbandCatalog(ROOT / "web/data/airband-channels.json")
    nearby = catalog.nearby(39.8561, -104.6737, 5)
    assert len(nearby) == 3
    assert all("distance_miles" in row for row in nearby)


def test_fft_selects_strongest_candidate():
    channels = AirbandCatalog(ROOT / "web/data/airband-channels.json").channels()
    candidates = score_channels(simulated_spectrum(channels), channels)
    assert candidates[0].channel["serviced_facility"] == "KDEN"
    assert candidates[0].channel["frequency_use"] == "TWR"
    assert candidates[0].snr_db >= 6


def test_product_contract():
    assert json.loads((ROOT / "web/data/airband-channels.json").read_text())["schema_version"] == 1


def test_channel_pause_and_block_exclude_from_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNTIME", tmp_path / "runtime")
    state = server.RadioState(simulate=True)
    frequency = 118_700_000
    state.update_channel_control({"frequency_hz": frequency, "action": "pause"})
    assert state.channel_control(frequency)["mode"] == "pause"
    assert frequency not in [int(channel["frequency_hz"]) for channel in state.available_channels()]
    state.update_channel_control({"frequency_hz": frequency, "action": "block"})
    assert state.channel_control(frequency)["mode"] == "block"
    state.update_channel_control({"frequency_hz": frequency, "action": "unblock"})
    assert state.channel_control(frequency)["mode"] == "active"
    assert json.loads((tmp_path / "runtime/settings.json").read_text())["channel_controls"] == {}
