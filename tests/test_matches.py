"""Mat assignments (MB_MatAssignmentDisplay.jsp). Invented wrestlers throughout."""
import pytest

from parsers.tournaments import _parse_tournament_matches


def wrestler(wrestler_id: int, first: str, last: str, record: str, team_short: str, team: str, year: str = "") -> str:
    return (
        f'<font data-team-id="{wrestler_id + 100}" data-wrestler-id="{wrestler_id}">'
        f'<span data-short-title="{first[0]}."><span>{first}</span></span> '
        f'<span data-short-title="{last}"><span>{last}</span></span>, {year} {record} '
        f'(<span data-short-title="{team_short}"><span>{team}</span></span>)</font>'
    )


def match_row(color: str = "#00FF66", mat: str = "Mat 1", bout: str = "255",
              weight: str = "106", round_: str = "Round 3", wrestlers: str = None) -> str:
    if wrestlers is None:
        wrestlers = (wrestler(21, "Alex", "Sample", "0-2", "NHS", "North High", "Jr") + " vs "
                     + wrestler(22, "Jordan", "Example", "1-1", "SHS", "South High"))
    return f"""<tr>
      <td style="background-color: {color}; width: 4px;"></td>
      <td><div>{mat}</div><div><div>Bout</div><div>{bout}</div></div></td>
      <td valign="top">
        <div><div style="display: table; width: 100%;">
          <div data-short-title="{weight}" style="display: table-cell;"><span>{weight}</span></div>
          <div style="display: table-cell; text-align: right;">{round_}</div>
        </div></div>
        <div>{wrestlers}</div>
      </td></tr>"""


def parse(*rows: str):
    return _parse_tournament_matches(f"<table>{''.join(rows)}</table>")


def test_full_row():
    [m] = parse(match_row())
    assert (m.mat, m.bout, m.status, m.weight_class, m.round) == (1, 255, "in_progress", "106", "Round 3")
    w1, w2 = m.wrestler1, m.wrestler2
    assert (w1.id, w1.first_name, w1.last_name, w1.record, w1.year) == ("21", "Alex", "Sample", "0-2", "Jr")
    assert (w2.first_name, w2.last_name, w2.record, w2.year) == ("Jordan", "Example", "1-1", None)


def test_team_is_the_team_not_the_first_name_initial():
    [m] = parse(match_row())
    assert (m.wrestler1.team.id, m.wrestler1.team.shortName, m.wrestler1.team.name) == ("121", "NHS", "North High")
    assert (m.wrestler2.team.shortName, m.wrestler2.team.name) == ("SHS", "South High")


@pytest.mark.parametrize("color, status", [
    ("#00FF66", "in_progress"),
    ("yellow", "on_deck"),
    ("#FFFF00", "on_deck"),
    ("rgb(255, 255, 0)", "on_deck"),
    ("#FFFFFF", "in_hole"),
])
def test_status_from_colour(color, status):
    [m] = parse(match_row(color=color))
    assert m.status == status


def test_one_wrestler_yet():
    [m] = parse(match_row(wrestlers=wrestler(21, "Alex", "Sample", "0-2", "NHS", "North High")))
    assert m.wrestler1.last_name == "Sample"
    assert m.wrestler2 is None


def test_no_mat_or_bout():
    [m] = parse(match_row(mat="TBD", bout=""))
    assert (m.mat, m.bout) == (0, 0)


def test_several_rows_and_non_match_rows():
    rows = match_row(bout="1") + "<tr><td>header</td></tr>" + match_row(bout="2", mat="Mat 3")
    assert [(m.mat, m.bout) for m in parse(rows)] == [(1, 1), (3, 2)]


def test_empty_page():
    assert parse() == []
