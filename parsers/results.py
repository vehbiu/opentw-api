"""Every result in a tournament, from RoundResults.jsp, in one request.

The page emits semantic markup, one section per round with the weights repeated inside it:

    <section class='tw-list'>
      <h1>Champ Round 2</h1>
      <h2>125</h2><ul><li>...</li></ul>
      <h2>133</h2><ul><li>...</li></ul>

How to ask for it, because none of this is guessable and most of it fails silently:

    displayFormatBox   MUST be 1 or 2. Empty renders the page with an EMPTY results container
                       and no error.
    roundId            empty for every round.
    groupId            comma-separated weight ids. A viewer must name a round or a weight, so
                       "everything" is spelled as every weight id.
    POST               ids in the QUERY STRING, the box fields in the BODY - the way the page's
                       own viewSchedule() builds it.

Bout numbers are not in this markup at all.
"""
import html as html_module
import re
from typing import List, Optional

from models.ttypes import BoutResult, EventType, TournamentResults
from utils import _get_timestamp
from utils.session_manager import session_manager

_SECTION = re.compile(r"<section class='tw-list'>(.*?)</section>", re.S)
_ROUND = re.compile(r"<h1>(.*?)</h1>", re.S)
_WEIGHT_BLOCK = re.compile(r"<h2>(.*?)</h2>\s*<ul>(.*?)</ul>", re.S)
_ITEM = re.compile(r"<li>(.*?)</li>", re.S)

# "label - NAME (School) 25-0 won by decision over NAME (School) 19-7 (Dec 2-1)"
#
# Split on the verb rather than matching the line in one go: the phrase varies ("won by fall",
# "won in sudden victory - 1", "won in double overtime").
_VERB = re.compile(r"\s+won\s+(?:by|in)\s+")
_WINNER = re.compile(r"^(?P<label>.+?) - (?P<name>.+?)\s*\((?P<school>.+)\)\s*(?P<record>\d+-\d+)$")
_LOSER = re.compile(
    r"^(?P<name>.+?)\s*\((?P<school>.+)\)\s*(?P<record>\d+-\d+)\s*\((?P<result>.+)\)$")

# The result code and whatever follows it. Forms seen across D1, D2 and women's 2026:
#
#   Dec 2-1   MD 10-2   Fall 4:11   TF-1.5 5:13 (20-4)   SV-1 4-1   TB-2 (RT) 2-2
#   2-OT 2-2  Inj. 4:10 DQ          M. For.   MFFL       For
#
# "2-OT" before the letter form or its leading digit falls out; "M. For." before the general
# form or its full stop ends the token early.
_RESULT = re.compile(
    r"^(?P<code>M\. For\.|Inj\.|\d+-OT|[A-Za-z]+(?:-[0-9.]+)?)\s*(?P<detail>.*)$")


def _text(fragment: str) -> str:
    plain = html_module.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", plain).strip()


def _parse_item(raw: str, round_name: str, weight: str) -> BoutResult:
    """One <li>. Never raises and never drops: an unreadable line keeps its text."""
    text = _text(raw)
    unparsed = BoutResult(round=round_name, weight=weight, parsed=False, text=text)

    halves = _VERB.split(text, maxsplit=1)
    if len(halves) != 2:
        return unparsed

    left, rest = halves
    method, _, right = rest.partition(" over ")
    if not right:
        return unparsed

    won, lost = _WINNER.match(left), _LOSER.match(right)
    if not won or not lost:
        return unparsed

    result = lost.group("result")
    code = _RESULT.match(result)

    return BoutResult(
        round=round_name,
        weight=weight,
        parsed=True,
        text=text,
        bout_label=won.group("label"),
        winner=won.group("name"),
        winner_school=won.group("school"),
        winner_record=won.group("record"),
        loser=lost.group("name"),
        loser_school=lost.group("school"),
        loser_record=lost.group("record"),
        method=method.strip(),
        result=result,
        result_code=code.group("code") if code else None,
        result_detail=(code.group("detail").strip() or None) if code else None,
    )


def parse_results(html: str) -> TournamentResults:
    results: List[BoutResult] = []

    for section in _SECTION.findall(html):
        round_match = _ROUND.search(section)
        round_name = _text(round_match.group(1)) if round_match else ""

        # Every <h2> in the section, not just the first: one section holds one round across
        # every weight asked for.
        for weight, items in _WEIGHT_BLOCK.findall(section):
            weight_name = _text(weight)
            for item in _ITEM.findall(items):
                results.append(_parse_item(item, round_name, weight_name))

    weights = list(dict.fromkeys(r.weight for r in results))

    return TournamentResults(
        bout_count=len(results),
        unparsed=sum(1 for r in results if not r.parsed),
        rounds=list(dict.fromkeys(r.round for r in results)),
        weights=weights,
        results=results,
    )


async def get_results(
        tournament_type: EventType,
        tournament_id: int,
        weight_ids: List[int],
        round_ids: Optional[List[int]] = None) -> TournamentResults:
    """Results for the given weights (and rounds, or every round), in one request."""
    group_id = ",".join(str(w) for w in weight_ids)
    round_id = ",".join(str(r) for r in round_ids) if round_ids else ""

    html = await session_manager.fetch(
        "POST",
        f"https://www.trackwrestling.com/{tournament_type.tournament_type}/RoundResults.jsp",
        tournament_id,
        tournament_type,
        params={
            "TIM": _get_timestamp(),
            "twSessionId": "zyxwvutsrq",
            "displayResult": "Y",
            "roundId": round_id,
            "groupId": group_id,
        },
        data={
            "roundIdBox": round_id,
            "groupIdBox": group_id,
            "fontSizeBox": "10",
            # The parameter that decides whether this endpoint returns anything at all.
            "displayFormatBox": "1",
            "includeByesBox": "Y",
            "patternBox": "1",
        },
    )
    return parse_results(html)
