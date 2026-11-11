"""Immutable approved public release maps; no arbitrary client URL registration."""

import re
from dataclasses import dataclass

from studymate.domain.client_observations.events import MAX_ASSET_ID


@dataclass(frozen=True, slots=True)
class PublicReleaseAssets:
    release_id: str
    asset_ids: frozenset[int]

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", self.release_id) is None:
            raise ValueError("Public asset map requires its exact source revision")
        if any(
            isinstance(identifier, bool) or not 0 <= identifier <= MAX_ASSET_ID
            for identifier in self.asset_ids
        ):
            raise ValueError("Public asset map requires bounded numeric asset identifiers")


@dataclass(frozen=True, slots=True)
class ApprovedPublicAssets:
    releases: tuple[PublicReleaseAssets, ...] = ()

    def __post_init__(self) -> None:
        if len({release.release_id for release in self.releases}) != len(self.releases):
            raise ValueError("Public release map must not rebind a source revision")

    def known_assets(self, release_id: str) -> frozenset[int] | None:
        return next(
            (release.asset_ids for release in self.releases if release.release_id == release_id),
            None,
        )
