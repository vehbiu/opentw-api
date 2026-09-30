"""One weight class's bracket sheet, read into entries, bout numbers and routing hints.

Only what varies between tournaments is read. The bracket's shape follows from its size, so
the nested table geometry - the most fragile thing on the page - is left alone:

    entries          who is in which first-round slot, with seed, school and record
    bout numbers     the published schedule, which differs by division and is not derivable
    pigtail entrants wrestlers who appear on the sheet but hold no first-round slot
    routes           "Loser of 19", "To top of 265" - where pigtails and consolation feeds go

Established against the 2026 NCAA D1, D2, D3 and women's championships.
"""
import html as html_module
import re
from typing import List

from models.ttypes import BracketEntry, BracketRoute, BracketSheet, PigtailEntrant

_ENTRY = re.compile(
    r"class='full-line'[^>]*?data-wrestler-id='(?P<id>\d+)'[^>]*?data-team-id='(?P<team>\d+)'"
    r"[^>]*?>(?P<line>.*?)</div>",
    re.S,
)
# Every name on the sheet, seated or not. Later rounds and pre-rounds are drawn as half-lines.
_MENTION = re.compile(
    r"class='(?:full|half)-line'[^>]*?data-wrestler-id='(?P<id>\d+)'"
    r"(?:[^>]*?data-team-id='(?P<team>\d+)')?[^>]*?>(?P<line>.*?)</div>",
    re.S,
)
# From the link TEXT. openBoutSheet's first argument repeats across pages and is not an id.
_BOUT = re.compile(r"openBoutSheet\(\d+,'[A-Z]'\)\"[^>]*>\s*(\d+)\s*</a>")
_ROUTE = re.compile(r"(?P<kind>Loser of|To top of|To bottom of)\s*(?:<[^>]+>)?\s*(?P<bout>\d+)")

# Every tag except <br>, which separates the name from the school on some sheets.
_TAGS_BUT_BR = re.compile(r"<(?!br[ />])[^>]+>")
_BREAK = re.compile(r"<br\s*/?>")
_SEED = re.compile(r"^\((\d+)\)\s*")
_RECORD = re.compile(r",?\s*(\d+-\d+)\s*$")
_RANK = re.compile(r"\s*\((\d+)\)\s*$")

_ROUTE_KINDS = {"Loser of": "loser_of", "To top of": "to_top_of", "To bottom of": "to_bottom_of"}


def _text(fragment: str) -> str:
    """Visible text with <br> kept, and a non-breaking space turned into a plain one."""
    plain = html_module.unescape(_TAGS_BUT_BR.sub("", fragment))
    return re.sub(r"\s+", " ", plain.replace(" ", " ")).strip()


def _has_seed_slot(raw_line: str) -> bool:
    """Whether a raw line begins with the seed slot every real entry line carries."""
    trimmed = raw_line.lstrip()
    return (
        trimmed.lower().startswith("&nbsp;")
        or trimmed.startswith(" ")
        or bool(_SEED.match(trimmed))
    )


def _parse_entry(wrestler_id: str, team_id: str, text: str) -> BracketEntry:
    """One entry line.

    Three formats, and which one a sheet uses is per TOURNAMENT:

        D1     (1) Luke Lilledahl, PSU, 25-0
        D2/W   (1) Isaiah Gamez<br>Adams St., 27-3
        D3     (1) Christian Guzman<br>North Central (IL) (5)

    The name ends at the <br> where there is one and at the first comma where there is not.
    Splitting on the profile link instead fails for a wrestler with no profile.
    """
    if _BREAK.search(text):
        name_part, origin = _BREAK.split(text, maxsplit=1)
    else:
        name_part, _, origin = text.partition(", ")

    name_part, school = name_part.strip(), origin.strip()

    seed_match = _SEED.match(name_part)
    seed = int(seed_match.group(1)) if seed_match else None
    name = (name_part[seed_match.end():] if seed_match else name_part).strip()

    record = None
    record_match = _RECORD.search(school)
    if record_match:
        record = record_match.group(1)
        school = school[:record_match.start()].rstrip().rstrip(",")

    # D3's trailing "(5)" is a regional qualifying rank. Digits only, so "North Central (IL)"
    # keeps its state.
    qualifying_rank = None
    rank_match = _RANK.search(school)
    if rank_match:
        qualifying_rank = int(rank_match.group(1))
        school = school[:rank_match.start()].rstrip()

    return BracketEntry(
        wrestler_id=wrestler_id,
        team_id=team_id,
        name=name,
        school=school.strip(),
        seed=seed,
        record=record,
        qualifying_rank=qualifying_rank,
    )


def parse_entries(html: str) -> List[BracketEntry]:
    """First-round slots in the order the sheet prints them, which is bracket order."""
    return [
        _parse_entry(m.group("id"), m.group("team"), _text(m.group("line")))
        for m in _ENTRY.finditer(html)
    ]


def parse_bout_numbers(html: str) -> List[int]:
    """Every published bout number on the sheet, ascending and distinct."""
    return sorted({int(n) for n in _BOUT.findall(html)})


def parse_pigtail_entrants(html: str) -> List[PigtailEntrant]:
    """Wrestlers who appear on the sheet but never in a first-round slot.

    Found by wrestler id, not position. D1 and D3 print these as "Schafer, BLOO" - a surname
    and a team abbreviation - which would read as a wrestler called Schafer from a school
    called BLOO, so those are flagged `partial`.
    """
    seated = {m.group("id") for m in _ENTRY.finditer(html)}
    seen = set()
    entrants = []

    for m in _MENTION.finditer(html):
        wrestler_id = m.group("id")
        if wrestler_id in seated or wrestler_id in seen:
            continue
        seen.add(wrestler_id)

        raw = m.group("line")
        text = _text(raw)
        entry = _parse_entry(wrestler_id, m.group("team") or "", text)
        partial = not _has_seed_slot(raw) or " " not in entry.name

        entrants.append(PigtailEntrant(
            wrestler_id=wrestler_id, text=_BREAK.sub(" ", text), entry=entry, partial=partial,
        ))

    return entrants


def parse_routes(html: str) -> List[BracketRoute]:
    """Every routing hint on the sheet, in document order, verbatim."""
    return [
        BracketRoute(kind=_ROUTE_KINDS[m.group("kind")], bout=int(m.group("bout")))
        for m in _ROUTE.finditer(html)
    ]


def parse_bracket_sheet(html: str) -> BracketSheet:
    return BracketSheet(
        entries=parse_entries(html),
        bout_numbers=parse_bout_numbers(html),
        pigtail_entrants=parse_pigtail_entrants(html),
        routes=parse_routes(html),
    )
