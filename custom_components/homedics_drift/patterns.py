"""Pattern files, ids, and upload planning.

Josh Lannin's Drifted project (https://github.com/joshlannin/drifted) defined
the wire points and the upload recovery rules. This Home Assistant integration
was converted from Drifted using Grok Bot. Names live only on this computer;
the table stores ids.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

USER_ID_MIN = 50000
CLEAN_PATTERN_ID = 50000
STORAGE_CAP = 700
MAX_POINTS = 24_000
PAGE_SIZE = 40

class PatternRejected(Exception):
    """A pattern cannot be sent or deleted. The table is left unchanged."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def parse_thr(text: str) -> list[tuple[float, float]]:
    """Read a Sandify ``.thr`` file: theta in radians, rho 0..1.

    Blank lines and ``#`` comments are skipped. Commas and spaces both separate
    the two numbers.
    """
    points: list[tuple[float, float]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            raise PatternRejected(f"could not read a theta,rho pair from {line!r}")
        try:
            theta = float(parts[0])
            rho = float(parts[1])
        except ValueError as err:
            raise PatternRejected(f"could not read a theta,rho pair from {line!r}") from err
        points.append((theta, max(0.0, min(1.0, rho))))
    return points


def densify(points: list[tuple[float, float]], max_step: float = 0.01) -> list[tuple[float, float]]:
    """Insert points so a Sandify path does not jump across the table.

    This matches Drifted's polar densify: step length is estimated in radii,
    and each original segment is split until the steps are about ``max_step``.
    """
    if not points:
        return []
    out = [points[0]]
    prev_theta, prev_rho = points[0]
    for theta, rho in points[1:]:
        distance = math.hypot(rho - prev_rho, (theta - prev_theta) * max(rho, prev_rho))
        steps = max(1, math.ceil(distance / max_step - 1e-12))
        for index in range(1, steps + 1):
            fraction = index / steps
            out.append(
                (
                    prev_theta + (theta - prev_theta) * fraction,
                    prev_rho + (rho - prev_rho) * fraction,
                )
            )
        prev_theta, prev_rho = theta, rho
    return out


def wire_point(theta: float, rho: float) -> tuple[int, int]:
    """Convert one polar point the way Drifted does.

    ``t`` is millidegrees divided by 6. ``r`` is rho on 0..100000, then divided
    by 2, so the rim is 50000.
    """
    milli = int(round(theta * 180.0 / math.pi * 1000.0)) % 360_000
    if milli < 0:
        milli += 360_000
    rho_file = int(round(max(0.0, min(1.0, rho)) * 100_000))
    return milli // 6, rho_file // 2


def thr_to_wire(text: str) -> list[tuple[int, int]]:
    """Parse, densify, and convert a ``.thr`` document to wire points.

    A long track is resampled more coarsely until it fits the table. A short
    track still uses the usual 0.01 step.
    """
    source = parse_thr(text)
    if not source:
        raise PatternRejected("the pattern file has no points")
    step = 0.01
    polar = densify(source, max_step=step)
    while len(polar) > MAX_POINTS and step < 0.06:
        step *= 1.25
        polar = densify(source, max_step=step)
    if len(polar) > MAX_POINTS:
        raise PatternRejected(
            f"the pattern has {len(polar)} points; the limit is {MAX_POINTS}"
        )
    return [wire_point(theta, rho) for theta, rho in polar]


def _thin_polar(points: list[tuple[float, float]], spacing: float) -> list[tuple[float, float]]:
    if spacing <= 0 or len(points) < 2:
        return points
    kept = [points[0]]
    for theta, rho in points[1:]:
        prev_theta, prev_rho = kept[-1]
        distance = math.hypot(rho - prev_rho, (theta - prev_theta) * max(rho, prev_rho, 0.02))
        if distance >= spacing:
            kept.append((theta, rho))
    if kept[-1] != points[-1]:
        kept.append(points[-1])
    return kept


def fit_thr_text(text: str) -> str:
    """A ``.thr`` document the table can store, coarsened only when it is too long."""
    source = parse_thr(text)
    if len(source) < 2:
        raise PatternRejected("the pattern file has no points")
    step = 0.01
    thinned = source
    polar = densify(thinned, max_step=step)
    while len(polar) > MAX_POINTS - 1000 and step < 0.06:
        step *= 1.25
        thinned = _thin_polar(source, step)
        polar = densify(thinned, max_step=step)
    if len(polar) > MAX_POINTS:
        raise PatternRejected(
            f"the pattern has {len(polar)} points; the limit is {MAX_POINTS}"
        )
    lines = [f"{theta:.6f} {min(1.0, max(0.0, rho)):.6f}" for theta, rho in polar]
    return "\n".join(lines) + "\n"


def github_raw_url(url: str) -> str:
    """Turn a GitHub blob link into the raw file. Other https links stay as they are."""
    cleaned = https_pattern_url(url)
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if host != "github.com":
        return cleaned
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "blob":
        return cleaned
    user, repo, _blob, ref, *rest = parts
    return f"https://raw.githubusercontent.com/{user}/{repo}/{ref}/{'/'.join(rest)}"


def gcode_to_thr(text: str) -> str:
    """Turn Sandify-style G0/G1 moves into one theta-rho path inside the disc."""
    cursor: tuple[float, float] | None = None
    points: list[tuple[float, float]] = []
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        command = parts[0].upper()
        if not command.startswith("G"):
            continue
        values: dict[str, float] = {}
        for part in parts[1:]:
            if len(part) < 2 or part[0].upper() not in "XYZ":
                continue
            try:
                values[part[0].upper()] = float(part[1:])
            except ValueError as err:
                raise PatternRejected("that gcode move could not be read") from err
        if cursor is None and ("X" not in values or "Y" not in values):
            continue
        x = values.get("X", cursor[0] if cursor else 0.0)
        y = values.get("Y", cursor[1] if cursor else 0.0)
        cursor = (x, y)
        if command[:3] in {"G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"} or command in {
            "G0",
            "G00",
            "G1",
            "G01",
        }:
            points.append(cursor)
    if len(points) < 2:
        raise PatternRejected("that gcode file has no drawing moves")
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    scale = max(math.hypot(point[0] - cx, point[1] - cy) for point in points) or 1.0
    polar: list[tuple[float, float]] = []
    previous = 0.0
    for x, y in points:
        dx = (x - cx) / scale
        dy = (y - cy) / scale
        rho = min(1.0, math.hypot(dx, dy))
        theta = math.atan2(dy, dx)
        while theta - previous > math.pi:
            theta -= 2 * math.pi
        while theta - previous < -math.pi:
            theta += 2 * math.pi
        previous = theta
        polar.append((theta, rho))
    lines = [f"{theta:.6f} {rho:.6f}" for theta, rho in polar]
    return fit_thr_text("\n".join(lines) + "\n")


def paginate(points: list[tuple[int, int]], page_size: int = PAGE_SIZE) -> list[list[tuple[int, int]]]:
    """Split wire points into pages of 40. The last page may be shorter."""
    if not points:
        raise PatternRejected("the pattern file has no points")
    return [points[index : index + page_size] for index in range(0, len(points), page_size)]


def resend_indexes(page_count: int, missing: list[int], attempt: int) -> list[int]:
    """0-based pages to send again after ``0x34/1``.

    An empty missing list means the trailing pages were lost. Grow the tail
    that is resent. A non-empty list is the 1-based pages the table asked for.
    """
    if not missing:
        tail = min(page_count, 3 * attempt)
        return list(range(page_count - tail, page_count))
    indexes: list[int] = []
    for page in missing:
        index = page - 1
        if 0 <= index < page_count and index not in indexes:
            indexes.append(index)
    if not indexes:
        raise PatternRejected("the table asked for pages that are not in this pattern")
    return indexes


def allocate_id(
    stored: set[int],
    *,
    playing: int | None,
    reuse: int | None,
) -> int:
    """Pick an id at or above 50000.

    Stock ids are never returned. The id that is drawing is never returned.
    A new id is refused once the table already holds ``STORAGE_CAP`` patterns.
    Reusing the id already saved for this name does not spend another slot.
    """
    active = playing if playing and playing > 0 else None
    if reuse is not None:
        if reuse < USER_ID_MIN:
            raise PatternRejected("refusing to replace a pattern that came with the table")
        if active is not None and reuse == active:
            raise PatternRejected("that pattern is drawing; wait until it is finished")
        return reuse
    if len(stored) >= STORAGE_CAP:
        raise PatternRejected(
            f"the table already stores {len(stored)} patterns; the limit is {STORAGE_CAP}"
        )
    candidate = USER_ID_MIN
    while candidate in stored or candidate == active:
        candidate += 1
        if candidate > 65535:
            raise PatternRejected("no free pattern id is left")
    return candidate


def slots(stored_count: int) -> tuple[int, int]:
    """Used count and how many new patterns are still allowed."""
    used = max(0, stored_count)
    return used, max(0, STORAGE_CAP - used)


def deletion_refusal(
    pattern_id: int,
    *,
    stored: set[int],
    playing: int | None,
    uploaded: set[int],
    protected: set[int] | None = None,
) -> str | None:
    """Why a delete must not be sent, or None when it is safe."""
    if pattern_id in (protected or set()):
        return "the clean pattern is kept"
    if pattern_id < USER_ID_MIN or pattern_id not in uploaded:
        return "only a pattern uploaded from Home Assistant can be deleted"
    if playing and pattern_id == playing:
        return "that pattern is drawing; wait until it is finished"
    if pattern_id not in stored:
        return "the table did not list that pattern, so it was not deleted"
    return None


def cleaning_spiral(spacing: float = 0.05) -> list[tuple[float, float]]:
    """Tight spiral from the centre to the rim.

    Turn spacing is about 0.05 of the radius, a little under the ball width,
    which is the full-table wipe Drifted uses. Points are already close
    together, so this list is sent as-is.
    """
    turns = max(1, math.ceil(1.0 / spacing - 1e-12))
    total = turns * 2.0 * math.pi
    points: list[tuple[float, float]] = []
    theta = 0.0
    while theta < total:
        rho = theta / total
        points.append((theta, rho))
        theta += min(0.4, 0.02 / max(rho, 0.02))
    points.append((total, 1.0))
    return points


def spiral_thr(points: list[tuple[float, float]] | None = None) -> str:
    """``.thr`` text for the cleaning spiral, kept with the library entry."""
    chosen = cleaning_spiral() if points is None else points
    return "".join(f"{theta:.6f} {rho:.6f}\n" for theta, rho in chosen)


@dataclass(frozen=True, slots=True)
class CleanList:
    """A playlist the table sent, reduced to what clean-pattern lookup needs."""

    index: int
    name: str | None
    pattern_ids: tuple[int, ...]


def find_stock_clean(
    playlists: list[CleanList], names: dict[int, str], stored: set[int]
) -> int | None:
    """A factory pattern named clean, preferring the list entry at position 1.

    Names come from a playlist the table sent or from a local rename of a
    stock id. Uploaded ids are not treated as the factory clean pattern.
    """
    for pattern_id, name in names.items():
        if (
            name.casefold() == "clean"
            and pattern_id in stored
            and pattern_id < USER_ID_MIN
        ):
            return pattern_id
    matches = [
        item
        for item in playlists
        if item.name and item.name.casefold() == "clean" and item.pattern_ids
    ]
    matches.sort(key=lambda item: (item.index != 1, item.index))
    for item in matches:
        pattern_id = item.pattern_ids[0]
        if pattern_id > 0 and (not stored or pattern_id in stored) and pattern_id < USER_ID_MIN:
            return pattern_id
    return None


def clean_play_order(target: int, clean_id: int | None, *, clean_before: bool) -> list[int]:
    """Patterns to draw. Clean runs first only when that option is on."""
    if clean_before and clean_id is not None and clean_id != target:
        return [clean_id, target]
    return [target]


def reusable_id(reuse: int | None, protected: set[int]) -> int | None:
    """Do not let a new drawing replace the protected clean pattern."""
    if reuse is None or reuse in protected:
        return None
    return reuse


def choose_clean_upload_id(stored: set[int], playing: int | None, existing: int | None) -> int:
    """Prefer id 50000. Never replace a drawing id or a different stored pattern."""
    active = playing if playing and playing > 0 else None
    if existing is not None and existing >= USER_ID_MIN and existing != active:
        return existing
    if CLEAN_PATTERN_ID not in stored and CLEAN_PATTERN_ID != active:
        return CLEAN_PATTERN_ID
    return allocate_id(stored, playing=playing, reuse=None)


def path_under_config(config_dir: Path, raw: str) -> Path:
    """Resolve a pattern path and require it to stay inside the config folder."""
    root = config_dir.expanduser().resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise PatternRejected("the pattern path has to stay inside the Home Assistant config folder")
    if path.suffix.lower() != ".thr":
        raise PatternRejected("the pattern file must be a .thr file")
    return path


def label_patterns(pattern_ids: list[int], names: dict[int, str]) -> list[tuple[str, int]]:
    """Display names in id order. Duplicate names gain the id so both can be picked."""
    ordered = sorted(pattern_id for pattern_id in pattern_ids if pattern_id > 0)
    bases = [names.get(pattern_id) or f"Pattern {pattern_id}" for pattern_id in ordered]
    counts: dict[str, int] = {}
    for base in bases:
        counts[base] = counts.get(base, 0) + 1
    seen: dict[str, int] = {}
    labeled: list[tuple[str, int]] = []
    for pattern_id, base in zip(ordered, bases, strict=True):
        if counts[base] == 1:
            label = base
        else:
            seen[base] = seen.get(base, 0) + 1
            label = f"{base} ({pattern_id})"
        labeled.append((label, pattern_id))
    return labeled


@dataclass
class PatternRecord:
    """One uploaded pattern remembered on this Home Assistant machine."""

    pattern_id: int
    name: str
    thr: str
    source: str = ""
    protected: bool = False


@dataclass
class PatternLibrary:
    """Local names and uploaded files. The table itself has no names."""

    records: dict[int, PatternRecord] = field(default_factory=dict)
    aliases: dict[int, str] = field(default_factory=dict)
    clean_before: bool = False
    favorites: set[str] = field(default_factory=set)

    def name_for(self, pattern_id: int) -> str | None:
        alias = self.aliases.get(pattern_id)
        if alias:
            return alias
        record = self.records.get(pattern_id)
        if record is not None:
            return record.name
        return None

    def names(self) -> dict[int, str]:
        found = {record.pattern_id: record.name for record in self.records.values()}
        found.update({pattern_id: name for pattern_id, name in self.aliases.items() if name})
        return found

    def uploaded_ids(self) -> set[int]:
        return set(self.records)

    def id_for_upload_name(self, name: str) -> int | None:
        for record in self.records.values():
            if record.name == name:
                return record.pattern_id
        return None

    def protected_ids(self) -> set[int]:
        return {record.pattern_id for record in self.records.values() if record.protected}

    def protected_clean_id(self) -> int | None:
        for record in self.records.values():
            if record.protected:
                return record.pattern_id
        return None

    def remember(
        self,
        pattern_id: int,
        name: str,
        thr: str,
        source: str = "",
        *,
        protected: bool = False,
    ) -> None:
        self.records[pattern_id] = PatternRecord(pattern_id, name, thr, source, protected)
        self.aliases[pattern_id] = name

    def rename(self, pattern_id: int, name: str) -> None:
        """Store a display name. This does not write the table."""
        cleaned = name.strip()
        if not cleaned:
            raise PatternRejected("the pattern needs a name")
        if pattern_id <= 0:
            raise PatternRejected("that is not a pattern id")
        self.aliases[pattern_id] = cleaned
        record = self.records.get(pattern_id)
        if record is not None:
            record.name = cleaned

    def forget(self, pattern_id: int) -> None:
        name = self.name_for(pattern_id)
        self.records.pop(pattern_id, None)
        self.aliases.pop(pattern_id, None)
        if name:
            self.favorites.discard(name)

    def set_favorite(self, name: str, on: bool) -> None:
        cleaned = name.strip()
        if not cleaned:
            raise PatternRejected("the pattern needs a name")
        if on:
            self.favorites.add(cleaned)
        else:
            self.favorites.discard(cleaned)

    def favorite_names(self) -> list[str]:
        return sorted(self.favorites)

    def to_dict(self) -> dict[str, object]:
        return {
            "records": [
                {
                    "id": record.pattern_id,
                    "name": record.name,
                    "thr": record.thr,
                    "source": record.source,
                    "protected": record.protected,
                }
                for record in self.records.values()
            ],
            "aliases": {str(pattern_id): name for pattern_id, name in self.aliases.items()},
            "clean_before": self.clean_before,
            "favorites": sorted(self.favorites),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> PatternLibrary:
        library = cls()
        if not data:
            return library
        records = data.get("records")
        if isinstance(records, list):
            for item in records:
                if not isinstance(item, dict):
                    continue
                try:
                    pattern_id = int(item["id"])
                    name = str(item["name"])
                    thr = str(item.get("thr") or "")
                    source = str(item.get("source") or "")
                    protected = bool(item.get("protected"))
                except (KeyError, TypeError, ValueError):
                    continue
                if pattern_id >= USER_ID_MIN and name:
                    library.records[pattern_id] = PatternRecord(
                        pattern_id, name, thr, source, protected
                    )
        if data.get("clean_before") is True:
            library.clean_before = True
        favorites = data.get("favorites")
        if isinstance(favorites, list):
            library.favorites = {str(name).strip() for name in favorites if str(name).strip()}
        aliases = data.get("aliases")
        if isinstance(aliases, dict):
            for key, value in aliases.items():
                try:
                    pattern_id = int(key)
                except (TypeError, ValueError):
                    continue
                if isinstance(value, str) and value.strip():
                    library.aliases[pattern_id] = value.strip()
        return library


MAX_IMPORT_BYTES = 1_500_000
MAX_IMPORT_FILES = 12


def https_pattern_url(url: str) -> str:
    """Accept only a public https link. Nothing is bundled from the internet."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise PatternRejected("the pattern link must start with https")
    if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local"):
        raise PatternRejected("that link is not a public pattern file")
    return cleaned


def _looks_like_thr(text: str) -> bool:
    for line in text.splitlines():
        parts = line.strip().replace(",", " ").split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        try:
            float(parts[0])
            float(parts[1])
        except ValueError:
            continue
        return True
    return False


def documents_from_download(filename: str, body: bytes) -> list[tuple[str, str]]:
    """``.thr`` documents inside one download. Other files are ignored."""
    if len(body) > MAX_IMPORT_BYTES:
        raise PatternRejected("that download is too large")
    if body[:2] == b"PK":
        found: list[tuple[str, str]] = []
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile as err:
            raise PatternRejected("that zip file could not be read") from err
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".thr"):
                continue
            if info.file_size > MAX_IMPORT_BYTES:
                continue
            text = archive.read(info).decode("utf-8", errors="replace")
            if not _looks_like_thr(text):
                continue
            found.append((Path(info.filename).stem, text))
            if len(found) >= MAX_IMPORT_FILES:
                break
        if not found:
            raise PatternRejected("that zip has no .thr patterns")
        return found
    text = body.decode("utf-8", errors="replace")
    stem = Path(urlparse(filename).path).stem or "Imported"
    lower = Path(urlparse(filename).path).suffix.lower()
    if lower in {".gcode", ".gco", ".nc"} or (
        not _looks_like_thr(text) and text.lstrip().upper().startswith("G")
    ):
        return [(stem, gcode_to_thr(text))]
    if not _looks_like_thr(text):
        raise PatternRejected("that file is not a .thr or gcode pattern")
    return [(stem, fit_thr_text(text))]


def inbox_names(filenames: list[str], library: PatternLibrary) -> list[str]:
    """``.thr`` files in the folder that have not been uploaded yet."""
    used = {record.source for record in library.records.values() if record.source}
    used.update(record.name + ".thr" for record in library.records.values())
    found: list[str] = []
    for name in sorted(filenames):
        if not name.lower().endswith(".thr"):
            continue
        if name in used:
            continue
        found.append(name)
    return found
