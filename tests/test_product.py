import json
from pathlib import Path

from n0jcg_air_band_scanner.catalog import AirbandCatalog
from n0jcg_air_band_scanner.fft_scan import score_channels, simulated_spectrum

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
