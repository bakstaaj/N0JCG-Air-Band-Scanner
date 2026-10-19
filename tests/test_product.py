import json
from array import array
from pathlib import Path

from n0jcg_air_band_scanner.catalog import AirbandCatalog
from n0jcg_air_band_scanner.fft_scan import score_channels, simulated_spectrum
from n0jcg_air_band_scanner import server
from n0jcg_licensing import LicenseClient

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


def test_registration_metadata(tmp_path):
    metadata = server.registration_status(tmp_path / "registration.json")
    assert metadata["product_name"] == "N0JCG Air Band Scanner"
    assert metadata["product_id"] == "n0jcg-air-band-scanner"
    assert metadata["license_prefix"] == "N0JCG-ABS-"


def test_registered_airband_installation_does_not_expire_or_refresh(tmp_path, monkeypatch):
    client = LicenseClient(
        product_slug="n0jcg-air-band-scanner",
        app_version="1.0.0",
        state_root=tmp_path / "license",
        environment={"N0JCG_INSTALLATION_ID": "test-installation"},
        now=lambda: 2_000_000_000,
        persistent_registration=True,
    )
    client._write_private_json(client.credentials_path, {"license_serial": "N0JCG-ABS-ABCD-2345-EFGH-JKLM", "email": "operator@example.com"})
    client._write_private_json(client.lease_path, {"lease": {"license_suffix": "ABCD", "expires_at": 1, "grace_until": 2}, "signature": "cached"})
    monkeypatch.setattr(client, "_verify_response", lambda response, email: response["lease"])

    status = client.status()

    assert status["registered"] is True
    assert status["trial_limit_seconds"] is None
    client.start_background_refresh(interval_seconds=1)
    assert client._refresh_thread is None


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
    state.update_channel_control({"frequency_hz": frequency, "action": "block"})
    state.update_channel_control({"action": "clear_all"})
    assert state.channel_control(frequency)["mode"] == "active"
    assert json.loads((tmp_path / "runtime/settings.json").read_text())["channel_controls"] == {}


def test_squelch_gate_fades_without_hard_chunk_edges(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNTIME", tmp_path / "runtime")
    state = server.RadioState(simulate=True)
    signal = array("h", [12000] * 4096).tobytes()
    gated = array("h")
    gated.frombytes(state.audio_chunk(signal))
    assert 0 < gated[0] < gated[100] < gated[-1] == 12000
    silence = array("h")
    silence.frombytes(state.audio_chunk(array("h", [500] * 4096).tobytes()))
    assert silence[0] > silence[100] > silence[1000] >= silence[-1] == 0


def test_manual_tune_does_not_release_into_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNTIME", tmp_path / "runtime")
    state = server.RadioState(simulate=True)
    channel = state.catalog.for_airport("KDEN")[0]
    state.select(channel)
    calls = []
    monkeypatch.setattr(state, "scan", lambda nearby=False: calls.append(nearby))
    state._release_quiet_channel()
    assert state.manual_tuned is True
    assert calls == []
