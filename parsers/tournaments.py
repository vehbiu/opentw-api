import re
import logging
from bs4 import BeautifulSoup
from typing import Iterable, List, Tuple
from utils import _get_timestamp
from datetime import datetime, date
from models.ttypes import Tournament, Wrestler, Match, Team, EventType, Status, Template, Weight, BracketType, BracketPage, BracketData, Division
from utils.session_manager import session_manager

_log = logging.getLogger(__name__)

def _parse_date_range(date_str: str) -> tuple[date | None, date | None]:
    """Parse TrackWrestling's date range into (start, end).

    Two shapes are in use and both appear on live pages:

        03/19/2026 - 03/21/2026     both years given
        03/19 - 03/21/2026          start omits the year, which the END carries

    When the start borrows the end's year, a range that crosses New Year
    ("12/30 - 01/02/2027") would put the start after the end, so the start rolls back a year.

    The second is why the tournament hub reported a null start date: it fed the bare
    "03/19" to a %m/%d/%Y parse, which fails, and the failure was swallowed.

    Unparseable parts come back as None rather than raising. A tournament with an odd
    date is still a tournament, and the search used to drop the whole row for it.
    """
    parts = [p.strip() for p in date_str.split(" - ") if p.strip()]

    if not parts:
        return None, None

    start_str, end_str = parts[0], parts[1] if len(parts) > 1 else None

    # Borrow the year from the end date when the start omits it.
    borrowed_year = bool(end_str) and len(start_str.split("/")) == 2
    if borrowed_year:
        start_str = f"{start_str}/{end_str.split('/')[-1]}"

    def parse(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError:
            return None

    start, end = parse(start_str), parse(end_str)

    if borrowed_year and start and end and start > end:
        start = start.replace(year=start.year - 1)

    return start, end


def _parse_venue_address(address_text: str) -> tuple[str, str, str, str, str]:
    lines = [line.strip() for line in address_text.split("\n") if line.strip()]

    venue_name = lines[0] if len(lines) > 0 else None
    street = lines[1] if len(lines) > 1 else None

    city = state = zip_code = None
    if len(lines) > 2:
        city_state_zip = lines[2].split(",")
        if len(city_state_zip) == 2:
            city = city_state_zip[0].strip()
            state_zip = city_state_zip[1].strip().split()
            if len(state_zip) >= 2:
                state = state_zip[0]
                zip_code = state_zip[1]

    return venue_name, street, city, state, zip_code


def _split_js_args(raw: str) -> List[str]:
    """Split the arguments of a JavaScript call, respecting quotes.

    `eventSelected(123,'Some Open, 3rd-4th Grade',1,'logo.png')` has FOUR arguments, but a
    plain `.split(",")` sees six and hands "3rd-4th Grade'" to int(). That dropped every
    tournament whose name contains a comma — silently, because the loop swallowed the
    ValueError.

    Quotes are consumed here, so callers get the bare value. A backslash inside quotes
    escapes the next character, so 'St. Mary\'s Open' comes back as St. Mary's Open.
    """
    args: List[str] = []
    current: List[str] = []
    quote: str | None = None
    escaped = False

    for ch in raw:
        if escaped:
            current.append(ch)
            escaped = False
        elif quote:
            if ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            else:
                current.append(ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ",":
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    args.append("".join(current).strip())
    return args


def _parse_tournaments(html_content: str) -> List[Tournament]:
    soup = BeautifulSoup(html_content, "html.parser")
    tournaments = []

    tournament_items = soup.select(".tournament-ul > li")

    for item in tournament_items:
        try:
            anchor = item.select_one('a[href*="eventSelected"]')
            onclick = anchor.get("href", "")
            # GREEDY to the last ")", anchored on the statement's end. A lazy match stops at
            # the first ")", which for a name like "2026 NCAA League Tournament (Boys)" is
            # inside the quoted argument — and truncated the row to two arguments.
            event_info = re.search(r"eventSelected\((.*)\)\s*;?\s*$", onclick)
            if not event_info:
                continue

            params = _split_js_args(event_info.group(1))

            if len(params) < 4:
                raise ValueError(
                    f"eventSelected() had {len(params)} arguments, expected 4: {params}"
                )

            tournament_id = int(params[0])
            name = params[1]
            event_type = EventType.from_id(int(params[2]))
            logo_url = params[3]

            date_span = item.select_one("div:nth-child(2) span:nth-child(2)")
            if not date_span:
                continue
            start_date, end_date = _parse_date_range(date_span.text.strip())

            venue_div = item.select_one("div:nth-child(3) span")
            venue_name = _ = city = state = zip_code = None
            if venue_div:
                venue_name, _, city, state, zip_code = _parse_venue_address(
                    venue_div.text
                )

            links_div = item.select_one("div:nth-child(4)")
            event_flyer_url = website_url = None
            if links_div:
                flyer_link = links_div.select_one('a[href*="uploads"]')
                website_link = links_div.select_one('a[href*="Website"]')
                if flyer_link:
                    event_flyer_url = flyer_link["href"]
                if website_link:
                    website_url = website_link["href"]

            tournament = Tournament(
                id=tournament_id,
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                venue_name=venue_name,
                # venue_address=street,
                venue_city=city,
                venue_state=state,
                venue_zip=zip_code,
                logo_url=logo_url if logo_url != "null" else None,
                event_flyer_url=event_flyer_url,
                website_url=website_url,
            )
            tournaments.append(tournament)

        except Exception as exc:
            # A malformed row should not take the whole search down with it — but it should
            # not vanish without trace either. Silently dropping four of thirty-one results
            # is indistinguishable from TrackWrestling having only twenty-seven.
            _log.warning(
                "skipped a tournament row: %s: %s", type(exc).__name__, exc, exc_info=False
            )
            continue

    return tournaments


def _parse_wrestler_data(wrestler_element) -> Wrestler:
    """Pull one wrestler out of a mat-assignment cell.

    The markup is three spans carrying `data-short-title`, in document order:

        <span data-short-title="A.">        <span>Aaly</span>        </span>
        <span data-short-title="Borbuev">   <span>Borbuev</span>     </span>
        , 0-2 (
        <span data-short-title="MW">        <span>Maine West</span> </span>
        )

    so first name, last name, team — with the attribute holding the abbreviation and the
    text holding the full value.

    They used to be picked by the LENGTH of the abbreviation (two characters meant a first
    name, more meant a surname) and the team by the first span whose PARENT contained a
    "(" — which is every span, since the parent holds the whole cell. That handed the team
    the first name's initial, so every wrestler's team came back as "A." or "J.". Position
    is what the markup actually guarantees.
    """
    wrestler_id = wrestler_element.get("data-wrestler-id", "")
    team_id = wrestler_element.get("data-team-id", "")

    titled = [s for s in wrestler_element.find_all("span") if s.get("data-short-title")]

    first_name_span = titled[0] if len(titled) > 0 else None
    last_name_span = titled[1] if len(titled) > 1 else None
    team_span = titled[2] if len(titled) > 2 else None

    full_text = wrestler_element.text

    record = None
    record_match = re.search(r"(\d+-\d+)", full_text)
    if record_match:
        record = record_match.group(1)

    year = None
    year_match = re.search(r"\b(Sr|Jr|So|Fr)\b", full_text)
    if year_match:
        year = year_match.group(1)

    # The full team name is the parenthesised part; the span's attribute is its abbreviation.
    team_match = re.search(r"\((.*?)\)", full_text)
    team_full_name = (
        team_span.text.strip() if team_span
        else (team_match.group(1).strip() if team_match else "")
    )
    team_short_name = team_span.get("data-short-title", "") if team_span else ""

    return Wrestler(
        id=wrestler_id,
        first_name=first_name_span.text.strip() if first_name_span else "",
        last_name=last_name_span.text.strip() if last_name_span else "",
        record=record,
        year=year,
        team=Team(id=team_id, name=team_full_name, shortName=team_short_name),
    )


def _parse_match_data(match_row) -> Match:
    tds = match_row.find_all("td")
    status_td, mat_td, details_td = tds

    mat_text = mat_td.text
    mat_number = (
        int(re.search(r"Mat (\d+)", mat_text).group(1))
        if re.search(r"Mat (\d+)", mat_text)
        else 0
    )
    bout_number = (
        int(re.findall(r"(\d+)", mat_text)[1])
        if len(re.findall(r"(\d+)", mat_text)) > 1
        else 0
    )

    weight_class_div = details_td.find("div", attrs={"data-short-title": True})
    weight_class = weight_class_div.text.strip() if weight_class_div else ""

    # Find the div containing both weight and round info
    info_div = details_td.find("div", {"style": "display: table; width: 100%;"})
    if info_div:
        # Get the right-aligned div which contains only the round information
        round_div = info_div.find(
            "div", {"style": "display: table-cell; text-align: right;"}
        )
        round_text = round_div.text.strip() if round_div else ""
    else:
        round_text = ""

    wrestler_fonts = details_td.find_all("font")
    wrestler1 = (
        _parse_wrestler_data(wrestler_fonts[0]) if len(wrestler_fonts) > 0 else None
    )
    wrestler2 = (
        _parse_wrestler_data(wrestler_fonts[1]) if len(wrestler_fonts) > 1 else None
    )

    status_color = status_td.get("style", "").lower()
    status: Status = "in_hole"

    if "00ff66" in status_color:
        status = "in_progress"
    elif any(
        color in status_color for color in ["yellow", "ffff00", "rgb(255, 255, 0)"]
    ):
        status = "on_deck"

    return Match(
        mat=mat_number,
        bout=bout_number,
        status=status,
        weight_class=weight_class,
        round=round_text,
        wrestler1=wrestler1,
        wrestler2=wrestler2,
    )


def _parse_tournament_matches(html: str) -> List[Match]:
    soup = BeautifulSoup(html, "html.parser")
    match_rows = [
        tr
        for tr in soup.find_all("tr")
        if len(tr.find_all("td")) == 3 and tr.find("td")
    ]
    return [_parse_match_data(row) for row in match_rows]


async def search_tournaments(query: str = None) -> List[Tournament]:
    """Search for tournaments by query

    Args:
        query (str, optional): Search query. Defaults to None.

    Returns:
        List[Tournament]: A list of Tournament objects representing the search results
    """
    async with session_manager.get_session() as session:
        async with session.get(
            "https://www.trackwrestling.com/Login.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tName": query or "",
                "state": "",
                "sDate": "",
                "eDate": "",
                "lastName": "",
                "firstName": "",
                "teamName": "",
                "sfvString": "",
                "city": "",
                "gbId": "",
                "camps": "false",
            },
        ) as response:
            html_content = await response.text()
            return _parse_tournaments(html_content)


async def get_mat_assignment(
    tournament_type: EventType, tournament_id: int
) -> List[Match]:
    """Get mat assignments for a tournament

    Args:
        tournament_type (EventType): The type of tournament (provided from the event_type field in Tournament)
        tournament_id (int): The ID of the tournament

    Returns:
        List[Match]: A list of Match objects representing the mat assignments
    """
    # return _parse_tournament_matches(open("htmls/mat-schedule.html", "r").read())
    async with session_manager.get_session(tournament_id) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/MB_MatAssignmentDisplay.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": tournament_id,
            },
        ) as response:
            html = await response.text()
            return _parse_tournament_matches(html)


async def get_tournament_info(
    tournament_type: EventType, tournament_id: int
) -> Tournament:
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/TournamentHub.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": str(tournament_id),
            },
        ) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            # Find the info content section
            content_div = soup.select_one(".hub-nav > ul > li:first-child .content")
            if not content_div:
                return None

            # Get tournament name
            name_elem = content_div.select_one("h3")
            name = name_elem.text.strip() if name_elem else ""

            # Get logo URL
            logo_img = content_div.select_one(".logo-icon img")
            logo_url = logo_img["src"] if logo_img else None

            # Parse date information
            date_p = content_div.select("p")[0]
            date_text = date_p.text.strip()

            # One date parser, not two. The hub's own could not read "03/19 - 03/21/2026"
            # and returned null starts for every multi-day tournament.
            start_date, end_date = _parse_date_range(date_text)

            # Parse venue information
            address_p = (
                content_div.select("p")[1] if len(content_div.select("p")) > 1 else None
            )
            venue_info = parse_venue_info(address_p.text) if address_p else {}

            # Look for URLs in the nav sections
            flyer_link = soup.select_one('a[href*="event_flyer"]')
            event_flyer_url = flyer_link["href"] if flyer_link else None

            website_link = soup.select_one('a[href*="website"]')
            website_url = website_link["href"] if website_link else None

            # Determine event type from the badge/class
            event_type_elem = soup.select_one(
                '[class*="bg-purple-"], [class*="bg-green-"], [class*="bg-blue-"], [class*="bg-orange-"], [class*="bg-pink-"]'
            )
            event_type = (
                EventType.from_id(determine_event_type(event_type_elem))
                if event_type_elem
                else tournament_type
            )  # Default to Predefined

            return Tournament(
                id=tournament_id,
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                venue_name=venue_info.get("name"),
                venue_city=venue_info.get("city"),
                venue_state=venue_info.get("state"),
                venue_zip=venue_info.get("zip"),
                logo_url=logo_url,
                event_flyer_url=event_flyer_url,
                website_url=website_url,
            )


def parse_venue_info(address_text: str) -> dict:
    """Parse venue information from address text block"""
    lines = [line.strip() for line in address_text.split("\n") if line.strip()]
    venue_info = {
        "name": lines[0] if lines else None,
        "city": None,
        "state": None,
        "zip": None,
    }

    if len(lines) > 1:
        # Last line typically contains City, State ZIP
        location_parts = lines[-1].split(",")
        if len(location_parts) == 2:
            venue_info["city"] = location_parts[0].strip()
            # Split state and ZIP
            state_zip = location_parts[1].strip().split()
            if len(state_zip) == 2:
                venue_info["state"] = state_zip[0]
                venue_info["zip"] = state_zip[1]

    return venue_info

async def get_brackets(tournament_type: EventType, tournament_id: int) -> BracketData:
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/BracketViewer.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": tournament_id,
            },
        ) as response:
            html = await response.text()
            # open("yeah.html", "w").write(html)
            # print("Got url " + response.url.__str__())
            return parse_bracket_data(html)    

def _pile_payloads(script_content: str) -> List[str]:
    """Every `str = "..."` payload in the Pile script, in document order.

    A regex rather than `.split('str = "')` because the spacing around `=` is not ours to
    rely on, and because splitting silently produces a different number of parts when it
    changes — which is how this broke the first time.
    """
    return re.findall(r'str\s*=\s*"([^"]*)"', script_content)


def _parse_templates(payload: str) -> List[Template]:
    """Templates: 7 fields each — bracketId, templateId, name, width, height, font, pages."""
    templates: List[Template] = []
    if not payload:
        return templates

    entries = payload.split('~')

    for i in range(0, len(entries) - 6, 7):
        # The pages field is itself a comma-separated list of (id, name) pairs.
        pages_data = entries[i + 6].split(',')
        pages = [
            BracketPage(
                page_index=j // 2,
                page_id=int(pages_data[j]),
                page_name=pages_data[j + 1],
                show_page=(pages_data[j] in ('1', '2', '4', '6')),
            )
            for j in range(0, len(pages_data) - 1, 2)
        ]

        templates.append(Template(
            template_index=len(templates),
            bracket_id=int(entries[i + 0]),
            template_id=int(entries[i + 1]),
            template_name=entries[i + 2],
            bracket_width=entries[i + 3],
            bracket_height=entries[i + 4],
            bracket_font=entries[i + 5],
            pages=pages,
        ))

    return templates


def _parse_divisions(payload: str) -> List[Division]:
    """Divisions: 2 fields each — id, name. Absent from current TrackWrestling pages."""
    divisions: List[Division] = []
    if not payload:
        return divisions

    entries = payload.split('~')

    for i in range(0, len(entries) - 1, 2):
        divisions.append(Division(
            division_index=len(divisions),
            division_id=int(entries[i]),
            division_name=entries[i + 1],
        ))

    return divisions


def _parse_weights(payload: str, with_division: bool) -> List[Weight]:
    """Weights, in the shape the page layout says they are in.

    Three fields - weightId, name, bracketId - is what TrackWrestling serves now.
    Four fields - divisionId, weightId, name, bracketId - is the older shape, which came
    with a divisions block; the division id went away when that block did.

    The shape is decided by that layout, not by trying field counts against the data.
    Weight names are usually numeric ("125"), so a list of 12 entries fits both shapes and
    a guess picks wrong for one of them.
    """
    weights: List[Weight] = []
    if not payload:
        return weights

    entries = payload.split('~')
    stride = 4 if with_division else 3

    if len(entries) % stride != 0:
        raise ValueError(
            f"Weights payload has {len(entries)} entries, not a multiple of {stride}: "
            f"{entries[:8]}"
        )

    for i in range(0, len(entries), stride):
        row = entries[i:i + stride]
        division_id = int(row.pop(0)) if with_division else None
        weight_id, weight_name, bracket_id = row
        weights.append(Weight(
            weight_index=len(weights),
            division_id=division_id,
            weight_id=int(weight_id),
            weight_name=weight_name,
            bracket_id=int(bracket_id),
        ))

    return weights


def _parse_bracket_types(payload: str) -> List[BracketType]:
    """Bracket types: a bare comma-separated list of ids."""
    return [
        BracketType(bracket_id=int(value))
        for value in payload.split(',')
        if value.strip().isdigit()
    ]


def parse_bracket_data(html_content: str) -> BracketData:
    """Parse the BracketViewer page's inline data into structured dataclasses.

    The page builds its dropdowns from a handful of tilde-delimited strings assigned to a
    variable called `str` inside a script that constructs a `Pile()`. The number of those
    strings is NOT stable: TrackWrestling used to emit four (templates, divisions, weights,
    bracket types) and now emits three, having dropped divisions and the division id that
    went with each weight.

    So the blocks are identified by their ROLE rather than their index — first is templates,
    last is bracket types, and whatever sits between them is divisions-then-weights or just
    weights. Positional indexing is what made this raise IndexError against the live site.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    script_content = None
    for script in soup.find_all('script'):
        if script.string and 'new Pile()' in script.string:
            script_content = script.string
            break

    if not script_content:
        raise ValueError("Could not find bracket data in HTML")

    payloads = _pile_payloads(script_content)

    if len(payloads) < 3:
        raise ValueError(
            f"BracketViewer gave {len(payloads)} data blocks; expected at least 3 "
            "(templates, weights, bracket types)"
        )

    templates = _parse_templates(payloads[0])
    bracket_types = _parse_bracket_types(payloads[-1])
    middle = payloads[1:-1]

    if len(middle) == 1:
        divisions = []
        weights = _parse_weights(middle[0], with_division=False)
    elif len(middle) == 2:
        divisions = _parse_divisions(middle[0])
        weights = _parse_weights(middle[1], with_division=True)
    else:
        raise ValueError(
            f"Unrecognised BracketViewer layout: {len(payloads)} data blocks"
        )

    return BracketData(
        divisions=divisions,
        weights=weights,
        templates=templates,
        bracket_types=bracket_types,
    )


def generate_bracket_url(
        tournament_type: EventType,
        weight_id: int,
        template: Template | None = None,
        pages: Iterable[int] | None = None,
        tw_session_id: str = "zyxwvutsrq") -> str:
    """Build a viewable Bracket.jsp URL for one weight class.

    The parameter names matter and were wrong: this sent chartId/chartWidth/chartHeight/
    chartFontSize, which Bracket.jsp ignores. The page wants groupId with
    bracketWidth/bracketHeight/bracketFontSize, plus includePages and templateId.

    Dimensions come from the TEMPLATE when one is supplied — BracketViewer publishes them
    per tournament (700x590 at font 8 for the NCAA Division I bracket) — rather than the
    670x870 that was hardcoded here.

    `pages` selects which parts of the bracket to render, using the page ids the template
    carries: 0 Prelims, 2 Championship Bracket, 3 Consolation Bracket. Omitting it lets
    TrackWrestling decide.
    """
    params = {
        "TIM": _get_timestamp(),
        "twSessionId": tw_session_id,
        "groupId": weight_id,
        "bracketWidth": template.bracket_width if template else 700,
        "bracketHeight": template.bracket_height if template else 590,
        "bracketFontSize": template.bracket_font if template else 8,
        "includePages": ",".join(str(p) for p in pages) if pages else "",
        "templateId": template.template_id if template and template.template_id else "",
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())

    return f"https://www.trackwrestling.com/{tournament_type.tournament_type}/Bracket.jsp?{query}"


async def get_bracket_data_html(tournament_type: EventType, tournament_id: int, group_id: int, pages: Tuple[int] = None) -> str:
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/AjaxFunctions.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "function": "getBracket",
                "groupId": group_id,
                "chartId": group_id,
                "width": 670,
                "height": 870,
                "font": 8,
                "includePages": ",".join((str(p) for p in pages)) if pages else "",
                # 4 = bottom, 5 = top
                # "includePages": "5",
                "templateId": 0,
            },
        ) as response:
            return await response.text()

def determine_event_type(element) -> int:
    """Determine event type based on CSS classes"""
    if "bg-purple" in str(element):
        return 1  # Predefined
    if "bg-green" in str(element):
        return 2  # Open
    if "bg-blue" in str(element):
        return 3  # Team
    if "bg-orange" in str(element):
        return 4  # Freestyle
    if "bg-pink" in str(element):
        return 5  # Season
    return 1  # Default to Predefined


async def cleanup():
    await session_manager.cleanup()
