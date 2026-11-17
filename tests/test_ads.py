"""The Google Ads conversion decisions, with no Flask and no network.

`dinkydash/ads.py` is deliberately plain: an unset `GOOGLE_ADS_ID` has to mean
every tag renders nothing, and a conversion's value and currency have to come
from the live plan `Billing.prices()` already fetched, never a number written
here.
"""

import pytest

from dinkydash import ads

PRICES = {
    "month": {"id": "price_month_example", "unit_amount": 600, "currency": "usd"},
    "year": {"id": "price_year_example", "unit_amount": 3900, "currency": "usd"},
}


class TestTheBaseTag:
    def test_unset_is_off(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_ADS_ID", raising=False)
        assert ads.ads_id() == ""
        assert not ads.enabled()

    def test_a_blank_value_is_off(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_ADS_ID", "   ")
        assert ads.ads_id() == ""
        assert not ads.enabled()

    def test_a_real_one_is_stripped_and_kept(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_ADS_ID", "  AW-123456789  ")
        assert ads.ads_id() == "AW-123456789"
        assert ads.enabled()

    def test_consent_regions_cover_the_eea_plus_gb_and_ch(self):
        for code in ("GB", "CH", "DE", "FR", "IS", "LI", "NO"):
            assert code in ads.CONSENT_REGIONS
        # Not a member of either, and not accidentally swept in.
        assert "US" not in ads.CONSENT_REGIONS
