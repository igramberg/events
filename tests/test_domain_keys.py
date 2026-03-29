import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from events.domain.keys import (
    derive_event_identity,
    format_starts_at_utc,
    make_event_key,
    make_location_key,
    make_organizer_key,
    make_venue_key,
)
from events.domain.models import IdentityKind


class KeyDerivationTests(unittest.TestCase):
    def test_location_venue_and_organizer_keys_are_deterministic(self) -> None:
        location_key = make_location_key(
            city="Boston", region="MA", country_code="US"
        )
        venue_key = make_venue_key(
            location_key=location_key, venue_name="Roadrunner"
        )
        organizer_key = make_organizer_key(name="Crossroads Presents")

        self.assertEqual("loc:v1:us:ma:boston", location_key)
        self.assertEqual(
            "venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner", venue_key
        )
        self.assertEqual("org:v1:crossroads%20presents", organizer_key)

    def test_format_starts_at_utc_uses_whole_seconds_z_suffix(self) -> None:
        self.assertEqual(
            "2026-03-28T20:00:00Z",
            format_starts_at_utc(
                datetime(
                    2026,
                    3,
                    28,
                    16,
                    0,
                    0,
                    900123,
                    tzinfo=ZoneInfo("America/New_York"),
                ),
            ),
        )

    def test_event_identity_uses_occurrence_id_when_unique(self) -> None:
        identity = derive_event_identity(
            source_name="roadrunner",
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            occurrence_id="SHOW Δ/123",
        )

        self.assertEqual(IdentityKind.OCCURRENCE_ID, identity.identity_kind)
        self.assertEqual(
            {"source_name": "roadrunner", "occurrence_id": "SHOW Δ/123"},
            dict(identity.identity_inputs),
        )
        self.assertEqual(
            "event:v1:roadrunner:occ:SHOW%20%CE%94%2F123",
            identity.event_key,
        )

    def test_event_identity_uses_series_id_plus_start_time(self) -> None:
        identity = derive_event_identity(
            source_name="boch_center",
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            source_event_id="HAMILTON/Evening",
        )

        self.assertEqual(
            IdentityKind.SOURCE_EVENT_ID_STARTS_AT,
            identity.identity_kind,
        )
        self.assertEqual(
            {
                "source_name": "boch_center",
                "source_event_id": "HAMILTON/Evening",
                "starts_at_utc": "2026-03-28T20:00:00Z",
            },
            dict(identity.identity_inputs),
        )
        self.assertEqual(
            "event:v1:boch_center:src:HAMILTON%2FEvening:2026-03-28T20%3A00%3A00Z",
            identity.event_key,
        )

    def test_event_identity_uses_fallback_hash_fixed_vector(self) -> None:
        identity = derive_event_identity(
            source_name="test_source",
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            title="Straße   Revue",
            venue_key="venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner",
        )

        self.assertEqual(
            IdentityKind.FALLBACK_HASH,
            identity.identity_kind,
        )
        self.assertEqual(
            {
                "source_name": "test_source",
                "normalized_title": "strasse revue",
                "starts_at_utc": "2026-03-28T20:00:00Z",
                "venue_key": "venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner",
                "normalization_version": "v1",
            },
            dict(identity.identity_inputs),
        )
        self.assertEqual(
            "event:v1:test_source:hash:7cf4d1c057987a8c6d2008615e7a03f8c5f8e0273e5689b1e1102cd1b3438adf",
            identity.event_key,
        )

    def test_derived_identity_inputs_are_immutable(self) -> None:
        identity = derive_event_identity(
            source_name="roadrunner",
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            occurrence_id="SHOW-123",
        )

        with self.assertRaises(TypeError):
            identity.identity_inputs["occurrence_id"] = "OTHER"

    def test_event_key_rejects_invalid_source_name(self) -> None:
        with self.assertRaises(ValueError):
            make_event_key(
                source_name="Roadrunner Boston",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                occurrence_id="SHOW-123",
            )

    def test_event_key_rejects_source_name_with_colon(self) -> None:
        with self.assertRaises(ValueError):
            make_event_key(
                source_name="roadrunner:boston",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                occurrence_id="SHOW-123",
            )

    def test_make_event_key_returns_event_key_string(self) -> None:
        event_key = make_event_key(
            source_name="test_source",
            starts_at=datetime(2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")),
            title="Example Show",
            venue_key="venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner",
        )

        self.assertTrue(event_key.startswith("event:v1:test_source:hash:"))

    def test_event_identity_requires_title_and_venue_key_for_hash_fallback(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            derive_event_identity(
                source_name="test_source",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
            )

    def test_event_identity_rejects_blank_fallback_inputs(self) -> None:
        with self.assertRaises(ValueError):
            derive_event_identity(
                source_name="test_source",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                title="   ",
                venue_key="venue:v1:loc%3Av1%3Aus%3Ama%3Aboston:roadrunner",
            )

        with self.assertRaises(ValueError):
            derive_event_identity(
                source_name="test_source",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                title="Example Show",
                venue_key="   ",
            )

    def test_event_key_rejects_naive_start_time(self) -> None:
        with self.assertRaises(ValueError):
            make_event_key(
                source_name="test_source",
                starts_at=datetime(2026, 3, 28, 20, 0, 0),
                occurrence_id="SHOW-123",
            )

    def test_event_identity_rejects_blank_source_native_ids(self) -> None:
        with self.assertRaises(ValueError):
            derive_event_identity(
                source_name="test_source",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                occurrence_id="   ",
            )

        with self.assertRaises(ValueError):
            derive_event_identity(
                source_name="test_source",
                starts_at=datetime(
                    2026, 3, 28, 20, 0, 0, tzinfo=ZoneInfo("UTC")
                ),
                source_event_id="   ",
            )


if __name__ == "__main__":
    unittest.main()
