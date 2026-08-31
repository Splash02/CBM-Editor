from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable, Optional


_VERSION_TAG_PATTERN = re.compile(
    r"^(?P<base>\d+\.\d+)(?:-pre(?P<preview>\d+))?$",
    re.IGNORECASE,
)
_VERSION_IN_FILENAME_PATTERN = re.compile(r"v\d+\.\d+(?:-pre\d+)?", re.IGNORECASE)


@dataclass(frozen=True)
class ReleaseVersion:
    tag: str
    base: Decimal
    preview: Optional[int]

    @property
    def channel(self) -> str:
        return "Preview" if self.preview is not None else "Stable"

    @property
    def sort_key(self):
        return self.base, self.preview if self.preview is not None else -1


def parse_release_tag(tag: str) -> Optional[ReleaseVersion]:
    clean_tag = str(tag or "").strip()
    match = _VERSION_TAG_PATTERN.fullmatch(clean_tag)
    if not match:
        return None
    try:
        base = Decimal(match.group("base"))
        preview_text = match.group("preview")
        preview = int(preview_text) if preview_text is not None else None
    except (InvalidOperation, ValueError):
        return None
    return ReleaseVersion(clean_tag, base, preview)


def release_tag_from_filename(filename: str) -> Optional[str]:
    match = _VERSION_IN_FILENAME_PATTERN.search(str(filename or ""))
    return match.group(0) if match else None


def newest_tag_for_channel(tags: Iterable[str], channel: str) -> Optional[ReleaseVersion]:
    wanted_channel = "Preview" if str(channel).casefold() == "preview" else "Stable"
    candidates = []
    for tag in tags:
        parsed = parse_release_tag(tag)
        if parsed is not None and parsed.channel == wanted_channel:
            candidates.append(parsed)
    return max(candidates, key=lambda version: version.sort_key, default=None)


def select_available_update(
    tags: Iterable[str],
    channel: str,
    current_tag: str,
    current_channel: str,
) -> Optional[ReleaseVersion]:
    wanted_channel = "Preview" if str(channel).casefold() == "preview" else "Stable"
    installed_channel = "Preview" if str(current_channel).casefold() == "preview" else "Stable"
    newest = newest_tag_for_channel(tags, wanted_channel)
    if newest is None:
        return None

    if wanted_channel != installed_channel:
        return newest

    normalized_current_tag = str(current_tag or "").strip()
    if normalized_current_tag[:1].casefold() == "v":
        normalized_current_tag = normalized_current_tag[1:]
    current = parse_release_tag(normalized_current_tag)
    if current is None:
        return newest

    if wanted_channel == "Stable":
        return newest if newest.base > current.base else None

    current_preview = current.preview if current.preview is not None else -1
    return newest if newest.sort_key > (current.base, current_preview) else None
