"""Parsers for a tournament's listing pages: teams, wrestlers, weights, results, stats.

These pages share TrackWrestling's `tw-table` grid and `tw-list` result sections, but their
columns differ by tournament type (open tournaments have classes, team tournaments have no
qualifying fields), so tables are read by header name rather than by position.
"""
import re
from typing import Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from models.details import (
    Competitor, MatchResult, Option, Participant, Placement, RoundOptions, StatsTable,
    TournamentClass, TournamentTeam, WeightClass, WeightResults,
)
from models.ttypes import EventType
from utils.cache import ttl_cache
from utils.session_manager import session_manager, UpstreamError

# TrackWrestling caps listing pages at 30 rows. Stop paging after this many pages regardless,
# so a markup change can't send us round in circles.
MAX_PAGES = 100

# Which id a `javascript:fn(id)` link in a cell carries.
_LINK_IDS = {
    "editParticipant": "wrestler_id",
    "viewTeamMembers": "team_id",
    "viewWeightClass": "weight_class_id",
    "viewClass": "division_id",
    "viewClassWeights": "class_id",
    "openTeamPointsDetail": "team_id",
}

_HEADER_ALIASES = {
    "abbr": "abbreviation",
    "count": "wrestler_count",
    "wrestlers": "wrestler_count",
    "max_wt": "max_weight",
    "group": "division",
    "seed_saved": "seeds_saved",
    "dob_range": "birth_date_range",
    "pre_reg_entry_fee": "pre_registration_fee",
    "onsite_entry_fee": "onsite_fee",
    "reg_limit": "registration_limit",
    "class_name": "name",
    "wrestler_name": "name",
}


def _key(header: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    return _HEADER_ALIASES.get(key, key)


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _yes(value: Optional[str]) -> Optional[bool]:
    if not value:
        return None
    return value.strip().lower() in ("yes", "y", "true")


def _read_table(html: str) -> List[Dict[str, str]]:
    """Rows of the page's `tw-table` as {header_key: text}, plus any ids its links carry.

    Header cells left blank (the row-number and spacer columns) are dropped.
    """
    # Some grids close a <div> they never opened inside a cell ("12/31/2020</div></td>"),
    # which html.parser takes as closing the page wrapper, and with it the whole table.
    # </td> closes any div genuinely opened in the cell, so the one before it can go.
    html = re.sub(r"</div>\s*(?=</td>)", "", html)
    table = BeautifulSoup(html, "html.parser").select_one("table.tw-table")
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    headers = [_key(th.get_text(" ", strip=True)) for th in rows[0].find_all(["th", "td"])]
    records = []

    for tr in rows[1:]:
        cells = tr.find_all("td")
        if len(cells) != len(headers):
            continue  # "no records" rows and the like

        record: Dict[str, str] = {}
        for header, cell in zip(headers, cells):
            if header:
                record[header] = cell.get_text(" ", strip=True)
            for element in [cell, *cell.find_all(True)]:
                for attr in ("href", "onclick"):
                    match = re.search(r"(\w+)\((\d+)", element.get(attr, "") or "")
                    if match and match.group(1) in _LINK_IDS:
                        record.setdefault(_LINK_IDS[match.group(1)], match.group(2))
            if cell.get("data-team-abbr"):
                record.setdefault("team_abbreviation", cell["data-team-abbr"])
        records.append(record)

    return records


def _has_next_page(html: str) -> bool:
    return bool(re.search(r"javascript:next\w*\(\)", html))


_NOT_RELEASED = "This information is not being released to the public yet."


async def _fetch(tournament_type: EventType, tournament_id: int, page: str, params: dict = None) -> str:
    html = await session_manager.fetch(
        f"{tournament_type.tournament_type}/{page}",
        {"tournamentId": tournament_id, **(params or {})},
        tournament_id,
        tournament_type,
    )
    # Organisers can hide a page; say so rather than returning an empty list that reads as
    # "no wrestlers".
    if _NOT_RELEASED in html:
        raise UpstreamError(_NOT_RELEASED, 404)
    return html


async def _all_pages(tournament_type: EventType, tournament_id: int, page: str, index_param: str,
                     extra: dict = None) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for index in range(MAX_PAGES):
        html = await _fetch(tournament_type, tournament_id, page, {index_param: index, **(extra or {})})
        rows = _read_table(html)
        new = [r for r in rows if r not in records]
        records += new
        # A "next" arrow on the last page would otherwise keep us paging to MAX_PAGES.
        if not _has_next_page(html) or not new:
            break
    return records


# ---------------------------------------------------------------------------------------------
# Teams, wrestlers, weights, classes
# ---------------------------------------------------------------------------------------------

def _parse_teams(records: Iterable[Dict[str, str]]) -> List[TournamentTeam]:
    return [
        TournamentTeam(
            id=_int(r.get("team_id")),
            name=r.get("team", ""),
            abbreviation=r.get("abbreviation") or None,
            # "Penn State, PA (GET)": drop the link TrackWrestling appends.
            season_team=re.sub(r"\s*\(\s*GET\s*\)\s*$", "", r["season_team"]) or None
            if r.get("season_team") else None,
            wrestler_count=_int(r.get("wrestler_count")),
            points=_float(r.get("points")),
        )
        for r in records
    ]


def _split_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    """TrackWrestling lists participants as "Last, First"."""
    last, sep, first = name.partition(",")
    return (first.strip() or None, last.strip() or None) if sep else (None, name.strip() or None)


def _parse_participants(records: Iterable[Dict[str, str]]) -> List[Participant]:
    participants = []
    for r in records:
        first, last = _split_name(r.get("name", ""))
        participants.append(Participant(
            id=_int(r.get("wrestler_id")),
            name=f"{first} {last}".strip() if first else (last or ""),
            first_name=first,
            last_name=last,
            team=r.get("team") or None,
            team_id=_int(r.get("team_id")),
            weight_class=r.get("weight_class") or None,
            weight_class_id=_int(r.get("weight_class_id")),
            division=r.get("division") or None,
            division_id=_int(r.get("division_id")),
            weight=r.get("weight") or None,
            grade=r.get("grade") or None,
            record=r.get("record") or None,
            scoring=_yes(r.get("scoring")),
            qualifying_tournament=r.get("qualifying_tournament") or None,
            qualifying_place=r.get("qualifying_place") or None,
        ))
    return participants


def _parse_weight_classes(records: Iterable[Dict[str, str]]) -> List[WeightClass]:
    return [
        WeightClass(
            id=_int(r.get("weight_class_id")),
            name=r.get("weight", ""),
            max_weight=r.get("max_weight") or None,
            wrestler_count=_int(r.get("wrestler_count")),
            bracket_type=r.get("bracket_type") or None,
            seeds_saved=_yes(r.get("seeds_saved")),
            bracket_built=_yes(r.get("bracket_built")),
        )
        for r in records
    ]


def _parse_classes(records: Iterable[Dict[str, str]]) -> List[TournamentClass]:
    return [
        TournamentClass(
            id=_int(r.get("class_id")),
            name=r.get("name", ""),
            wrestler_count=_int(r.get("wrestler_count")),
            birth_date_range=r.get("birth_date_range") or None,
            style=r.get("style") or None,
            pre_registration_fee=r.get("pre_registration_fee") or None,
            onsite_fee=r.get("onsite_fee") or None,
            registration_limit=r.get("registration_limit") or None,
            match_length=r.get("match_length") or None,
        )
        for r in records
    ]


@ttl_cache(300)
async def get_teams(tournament_type: EventType, tournament_id: int) -> List[TournamentTeam]:
    records = await _all_pages(tournament_type, tournament_id, "TournamentTeams.jsp", "displayIndex")
    seen, unique = set(), []
    for team in _parse_teams(records):  # consecutive pages may overlap by a row
        key = team.id or team.name
        if key not in seen:
            seen.add(key)
            unique.append(team)
    return unique


@ttl_cache(300)
async def get_participants(tournament_type: EventType, tournament_id: int) -> List[Participant]:
    # Only the page number: the page's own filter/sort parameters differ by tournament type,
    # and a sort column the type doesn't have makes TrackWrestling return an empty grid.
    records = await _all_pages(tournament_type, tournament_id, "TournamentParticipants.jsp", "participantIndex")

    # Consecutive pages overlap by a row.
    seen, unique = set(), []
    for participant in _parse_participants(records):
        key = participant.id or (participant.name, participant.team, participant.weight_class)
        if key not in seen:
            seen.add(key)
            unique.append(participant)
    return unique


# Open and freestyle tournaments organise weights into classes (age/gender groups).
CLASS_TYPES = (EventType.OPEN, EventType.FREESTYLE)


@ttl_cache(300)
async def get_weight_classes(tournament_type: EventType, tournament_id: int) -> List[WeightClass]:
    if tournament_type in CLASS_TYPES:
        raise UpstreamError(f"{tournament_type.alias.title()} tournaments list classes, not weight classes; see /classes", 404)
    html = await _fetch(tournament_type, tournament_id, "TournamentWeightClasses.jsp")
    return _parse_weight_classes(_read_table(html))


@ttl_cache(300)
async def get_classes(tournament_type: EventType, tournament_id: int) -> List[TournamentClass]:
    if tournament_type not in CLASS_TYPES:
        raise UpstreamError("Only open and freestyle tournaments have classes; see /weights", 404)
    html = await _fetch(tournament_type, tournament_id, "TournamentClasses.jsp")
    return _parse_classes(_read_table(html))


# ---------------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------------

_WIN_TYPES = [
    # (prefix of TrackWrestling's result code, win type)
    ("M. For", "medical_forfeit"),
    ("FF", "forfeit"),
    ("For", "forfeit"),
    ("Inj", "injury_default"),
    ("DQ", "disqualification"),
    ("Dec", "decision"),
    ("MD", "major_decision"),
    ("TF", "tech_fall"),
    ("Fall", "fall"),
    ("SV", "sudden_victory"),
    ("TB", "tie_breaker"),
    ("UTB", "tie_breaker"),
    ("OT", "overtime"),
    ("2-OT", "overtime"),
    ("Bye", "bye"),
]

_COMPETITOR = r"(?P<{0}>.+?) \((?P<{0}_team>[^()]*)\)(?: (?P<{0}_record>\d+-\d+))?(?:, \.)?"

_BOUT = re.compile(
    r"^" + _COMPETITOR.format("winner")
    + r" (?:won (?:by|in) (?P<how>[a-z \-\d]+?) over|over) "
    + _COMPETITOR.format("loser")
    # Open tournaments' round results print the result bare instead of in brackets.
    + r"(?: (?P<bare_result>(?:Dec|MD|TF|Fall|FF|For|M\. For|Inj|DQ|SV|TB|UTB|OT|2-OT|NC)\b.*))?$"
)
# "won by fall over", for lines without a result code.
_HOW = {
    "decision": "decision", "major decision": "major_decision", "tech fall": "tech_fall",
    "fall": "fall", "forfeit": "forfeit", "medical forfeit": "medical_forfeit",
    "injury default": "injury_default", "disqualification": "disqualification",
    "sudden victory": "sudden_victory", "tie breaker": "tie_breaker",
    "overtime": "overtime", "double overtime": "overtime",
}
_BYE = re.compile(r"^" + _COMPETITOR.format("winner") + r" received a bye")
_DUAL = re.compile(r"^(?P<winner>.+) defeated (?P<loser>.+) (?P<ws>\d+)-(?P<ls>\d+)\.?$")


def _trailing_parens(text: str) -> Tuple[str, Optional[str]]:
    """Split "... (TF-1.5 5:45 (19-3))" into ("...", "TF-1.5 5:45 (19-3)"), nesting aware."""
    text = text.rstrip()
    if not text.endswith(")"):
        return text, None
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        if text[i] == ")":
            depth += 1
        elif text[i] == "(":
            depth -= 1
            if depth == 0:
                return text[:i].rstrip(), text[i + 1:-1].strip()
    return text, None


def _win_type(result: Optional[str]) -> Optional[str]:
    if not result:
        return None
    for prefix, win_type in sorted(_WIN_TYPES, key=lambda p: -len(p[0])):
        if result.startswith(prefix):
            return win_type
    return None


def _competitor(match: re.Match, prefix: str) -> Competitor:
    return Competitor(
        name=match.group(prefix).strip(),
        team=match.group(f"{prefix}_team").strip() or None,
        record=match.group(f"{prefix}_record"),
    )


def parse_match_line(text: str, round_name: Optional[str] = None,
                     weight_class: Optional[str] = None) -> MatchResult:
    """Read one result line. Unrecognised lines are kept, with only `text` set."""
    text = re.sub(r"\s+", " ", text).strip()
    body = text

    # Round results prefix each line with its round: "Cons. Semi - Nico Provo (...) ..."
    prefix = re.match(r"^([^()]+?) - (?=.*\()", body)
    if prefix and not re.search(r"\d+-\d+$", prefix.group(1)):
        round_name = round_name or prefix.group(1).strip()
        body = body[prefix.end():]

    dual = _DUAL.match(body)
    if dual:
        return MatchResult(
            round=round_name, weight_class=weight_class,
            winner=Competitor(name=dual.group("winner").strip()),
            loser=Competitor(name=dual.group("loser").strip()),
            win_type="dual", result=f"{dual.group('ws')}-{dual.group('ls')}",
            winner_score=int(dual.group("ws")), loser_score=int(dual.group("ls")),
            text=text,
        )

    bye = _BYE.match(body)
    if bye:
        return MatchResult(
            round=round_name, weight_class=weight_class,
            winner=_competitor(bye, "winner"), loser=None,
            win_type="bye", result="Bye", text=text,
        )

    # Peel the trailing "(Dec 2-1)" off as the result. A line can also end in the loser's
    # "(Team)" with no result at all; then the peeled line won't parse, so use the whole line.
    peeled, result = _trailing_parens(body)
    bout = _BOUT.match(peeled)
    if not bout:
        bout, result = _BOUT.match(body), None
    if bout and bout.group("bare_result"):
        result = bout.group("bare_result").strip()
    if not bout:
        return MatchResult(round=round_name, weight_class=weight_class, winner=None, loser=None,
                           win_type=None, result=result, text=text)

    # The score is the last "a-b" in the result; for tech falls that's the nested one.
    scores = re.findall(r"(\d+)-(\d+)", result or "")
    time = re.search(r"\b(\d+:\d\d)\b", result or "")
    win_type = _win_type(result) or _HOW.get((bout.group("how") or "").split(" - ")[0].strip())
    return MatchResult(
        round=round_name, weight_class=weight_class,
        winner=_competitor(bout, "winner"),
        loser=_competitor(bout, "loser"),
        win_type=win_type,
        result=result,
        winner_score=int(scores[-1][0]) if scores and win_type != "forfeit" else None,
        loser_score=int(scores[-1][1]) if scores and win_type != "forfeit" else None,
        time=time.group(1) if time else None,
        text=text,
    )


def _parse_placement(text: str) -> Optional[Placement]:
    match = re.match(r"^\s*(\d+)\w{2} Place - (.+?)\s*$", text)
    if not match:
        return None
    # "Luke Lilledahl of Penn State"; team tournaments list just the team.
    name, sep, team = match.group(2).partition(" of ")
    return Placement(place=int(match.group(1)), name=name.strip(), team=team.strip() or None if sep else None)


def _list_items(section: Tag) -> List[str]:
    # Team tournaments leave <li>s unclosed and separate them with <br>, which html.parser
    # nests; take each item's own text only.
    items = []
    for li in section.find_all("li"):
        own = re.sub(r"\s+", " ", "".join(li.find_all(string=True, recursive=False))).strip()
        # Empty bracket slots ("() received a bye") and bouts not yet wrestled are placeholders.
        if own and not re.search(r"(^|- )\(\) received a bye|has not been wrestled yet", own):
            items.append(own)
    return items


def _parse_results(html: str) -> List[WeightResults]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for block in soup.select("section.tw-list"):
        heading = block.find("h1")
        weight = heading.get_text(" ", strip=True) if heading else ""
        entry = WeightResults(weight_class=weight)

        for section in block.find_all("section"):
            title_tag = section.find("h2")
            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            for item in _list_items(section):
                if title == "Guaranteed Places":
                    placement = _parse_placement(item)
                    if placement:
                        entry.placements.append(placement)
                else:
                    entry.matches.append(parse_match_line(item, round_name=title, weight_class=weight))

        results.append(entry)

    return results


def _parse_round_results(html: str) -> List[MatchResult]:
    """Round results group by round (h1) then weight (h2), or the other way round."""
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    for block in soup.select("section.tw-list"):
        h1 = block.find("h1")
        first = h1.get_text(" ", strip=True) if h1 else None
        # Each h2 heads the list that follows it; a block may hold several.
        groups = []
        for h2 in block.find_all("h2"):
            ul = h2.find_next_sibling("ul")
            if ul is not None:
                groups.append((h2.get_text(" ", strip=True), ul))
        if not groups:
            groups = [(None, block)]
        for second, container in groups:
            for item in _list_items(container):
                match = parse_match_line(item)
                # Whichever heading isn't the line's own round prefix is the weight.
                if match.round and match.round == first:
                    match.weight_class = second
                elif match.round:
                    match.weight_class = second if second != match.round else first
                else:
                    match.round, match.weight_class = first, second
                matches.append(match)
    return matches


def _parse_select(html: str, name: str) -> List[Option]:
    select = BeautifulSoup(html, "html.parser").find("select", attrs={"name": name})
    if select is None:
        return []
    options = []
    for option in select.find_all("option"):
        value = option.get("value", "").strip()
        if not value:
            continue
        group = option.find_parent("optgroup")
        options.append(Option(
            id=int(value) if value.isdigit() else value,
            name=option.get_text(" ", strip=True),
            group=group.get("label") if group else None,
        ))
    return options


@ttl_cache(60)
async def get_results(tournament_type: EventType, tournament_id: int) -> List[WeightResults]:
    html = await _fetch(tournament_type, tournament_id, "TournamentResults.jsp")
    return _parse_results(html)


@ttl_cache(300)
async def get_round_options(tournament_type: EventType, tournament_id: int) -> RoundOptions:
    html = await _fetch(tournament_type, tournament_id, "RoundResults.jsp")
    return RoundOptions(
        rounds=_parse_select(html, "roundIdBox"),
        weight_classes=_parse_select(html, "groupIdBox"),
    )


@ttl_cache(60)
async def get_round_results(tournament_type: EventType, tournament_id: int,
                            round_id: Optional[int] = None,
                            weight_class_id: Optional[int] = None) -> List[MatchResult]:
    html = await _fetch(tournament_type, tournament_id, "RoundResults.jsp", {
        "displayResult": "Y",
        "roundId": round_id or "",
        "groupId": weight_class_id or "",
        "displayFormatBox": "1",
        "includeByesBox": "Y",
        "fontSizeBox": "10",
        "patternBox": "",
    })
    return _parse_round_results(html)


# ---------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------

STATS_PAGES = {
    "individual": "IndividualStats.jsp",
    "team": "TeamStats.jsp",
    "weight": "WeightClassStats.jsp",
    "division": "DivisionStats.jsp",
}


@ttl_cache(60)
async def get_stats(tournament_type: EventType, tournament_id: int, kind: str,
                    stat: Optional[str] = None, team_id: Optional[int] = None,
                    weight_class_id: Optional[int] = None) -> StatsTable:
    if (team_id or weight_class_id) and not stat:
        stat = "mostPinsLeastTime"  # the page's own default; filters only apply with a stat
    params = {"statType": stat} if stat else {}
    if stat and kind == "individual":
        params.update({"division": "", "team": team_id or "", "weight": weight_class_id or "", "grade": ""})
    html = await _fetch(tournament_type, tournament_id, STATS_PAGES[kind], params)

    selected = re.search(r'var statType = "(\w+)"', html)
    records = _read_table(html)
    for record in records:
        record.pop("", None)
    return StatsTable(
        stat=selected.group(1) if selected else (stat or ""),
        available_stats=_parse_select(html, "statList"),
        rows=records,
    )
