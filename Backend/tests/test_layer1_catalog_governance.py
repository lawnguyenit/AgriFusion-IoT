from __future__ import annotations

import unittest

from Backend.Core.layer1.contracts import catalog_entries
from Backend.Core.layer1.validation.canonical import build_unknown_catalog_entries


class Layer1CatalogGovernanceTests(unittest.TestCase):
    def test_catalog_marks_timestamp_as_split_only(self) -> None:
        entries = {entry["canonical_name"]: entry for entry in catalog_entries()}
        timestamp_entry = entries["record.ts_sample"]

        self.assertEqual(timestamp_entry["feature_role"], "split_and_order")
        self.assertEqual(timestamp_entry["split_only"], True)
        self.assertEqual(timestamp_entry["eligible_for_model"], False)

    def test_catalog_marks_direct_rule_proxy_fields(self) -> None:
        entries = {entry["canonical_name"]: entry for entry in catalog_entries()}
        proxy_entry = entries["delivery.is_buffered_replay"]

        self.assertEqual(proxy_entry["feature_role"], "rule_proxy")
        self.assertEqual(proxy_entry["used_by_label_rule"], True)
        self.assertEqual(proxy_entry["rule_proxy_level"], "direct")
        self.assertEqual(proxy_entry["allowed_views"], "v3|v4|v5")
        self.assertEqual(proxy_entry["eligible_for_model"], True)

    def test_unknown_catalog_entries_use_explicit_missing_catalog_role(self) -> None:
        unknown_entries = build_unknown_catalog_entries(["record.fake_field"])
        self.assertEqual(len(unknown_entries), 1)
        self.assertEqual(unknown_entries[0]["feature_role"], "missing_catalog_entry")
        self.assertEqual(unknown_entries[0]["rule_proxy_level"], "unknown")


if __name__ == "__main__":
    unittest.main()
