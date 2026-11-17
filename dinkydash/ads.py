"""Google Ads settings used by the separate marketing site."""

import os

# The regions Consent Mode v2 defaults to denied: the EEA (EU plus Iceland,
# Liechtenstein and Norway), the UK and Switzerland. Every other region gets
# the second, granting default.
CONSENT_REGIONS = (
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "GB", "CH",
)


def ads_id():
    """The public container id, or `""` when the base tag should render nothing."""
    return os.environ.get("GOOGLE_ADS_ID", "").strip()


def enabled():
    return bool(ads_id())
