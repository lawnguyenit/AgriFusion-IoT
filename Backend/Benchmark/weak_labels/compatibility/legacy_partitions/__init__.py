"""Compatibility facade for legacy base-split construction."""

from .splitting import BaseSplitBundle, build_base_split_bundle

LEGACY_COMPATIBILITY_ONLY = True

__all__ = ["BaseSplitBundle", "build_base_split_bundle"]
