"""RoundResults.jsp. Invented wrestlers; result codes as the site writes them."""
import pytest

from parsers.results import parse_results


def bout(winner: str, loser: str, result: str, verb: str = "won by decision",
         label: str = "Champ. Round 1") -> str:
    return (f"<li>{label} - {winner} (North High) 25-0 {verb} over "
            f"{loser} (South High) 19-7 ({result})</li>")


def section(round_name: str, **weights: str) -> str:
    blocks = "".join(f"<h2>{w.lstrip('_')}</h2><ul>{items}</ul>" for w, items in weights.items())
    return f"<section class='tw-list'><h1>{round_name}</h1>{blocks}</section>"


def only(line: str):
    [result] = parse_results(section("R1", _125=line)).results
    return result


def test_fields():
    r = only(bout("Alex Sample", "Jordan Example", "Dec 2-1", label="1st Place Match"))
    assert r.parsed
    assert (r.round, r.weight, r.bout_label) == ("R1", "125", "1st Place Match")
    assert (r.winner, r.winner_school, r.winner_record) == ("Alex Sample", "North High", "25-0")
    assert (r.loser, r.loser_school, r.loser_record) == ("Jordan Example", "South High", "19-7")
    assert (r.method, r.result, r.result_code, r.result_detail) == ("decision", "Dec 2-1", "Dec", "2-1")


@pytest.mark.parametrize("verb, result, code, detail", [
    ("won by decision", "Dec 2-1", "Dec", "2-1"),
    ("won by major decision", "MD 10-2", "MD", "10-2"),
    ("won by fall", "Fall 4:11", "Fall", "4:11"),
    ("won by tech fall", "TF-1.5 5:13 (20-4)", "TF-1.5", "5:13 (20-4)"),
    ("won in sudden victory - 1", "SV-1 4-1", "SV-1", "4-1"),
    ("won in sudden victory - 2", "SV-2 4-1", "SV-2", "4-1"),
    ("won in tie breaker - 1", "TB-1 6-5", "TB-1", "6-5"),
    ("won in tie breaker - 2", "TB-2 (RT) 2-2", "TB-2", "(RT) 2-2"),
    ("won in double overtime", "2-OT 2-2", "2-OT", "2-2"),
    ("won by injury default", "Inj. 4:10", "Inj.", "4:10"),
    ("won by disqualification", "DQ", "DQ", None),
    # The same outcome written two ways; kept verbatim.
    ("won by medical forfeit", "M. For.", "M. For.", None),
    ("won by medical forfeit", "MFFL", "MFFL", None),
    ("won by forfeit", "For", "For", None),
])
def test_result_codes(verb, result, code, detail):
    r = only(bout("Alex Sample", "Jordan Example", result, verb))
    assert (r.method, r.result_code, r.result_detail) == (verb.split(" ", 2)[2], code, detail)


def test_school_with_brackets():
    r = only("<li>R1 - Casey Test (North Central (IL)) 20-3 won by fall over Pat Doe (Loras) 10-9 (Fall 1:02)</li>")
    assert (r.winner_school, r.loser_school) == ("North Central (IL)", "Loras")


def test_markup_inside_a_line():
    r = only("<li>R1 - <b>Alex Sample</b> (North High) 25-0 won by decision over "
             "<a href='#'>Jordan Example</a> (South High) 19-7 (Dec 3-2)</li>")
    assert (r.winner, r.loser) == ("Alex Sample", "Jordan Example")


@pytest.mark.parametrize("text", [
    "something TrackWrestling has never printed before",
    "R1 - Alex Sample (North High) 25-0 received a bye",
    "R1 - Alex Sample (North High) 25-0 won by decision against Jordan Example",
])
def test_unreadable_line_is_kept_not_dropped(text):
    results = parse_results(section("R1", _125=f"<li>{text}</li>"))
    assert (results.bout_count, results.unparsed) == (1, 1)
    assert not results.results[0].parsed
    assert results.results[0].text == text


def test_every_weight_in_a_round_and_every_round():
    html = (section("Champ. Round 1",
                    _125=bout("A", "B", "Dec 2-1") + bout("C", "D", "Fall 1:00", "won by fall"),
                    _133=bout("E", "F", "MD 9-1", "won by major decision"))
            + section("Quarterfinal", _125=bout("A", "C", "Dec 1-0")))
    results = parse_results(html)
    assert results.bout_count == 4
    assert results.unparsed == 0
    assert results.rounds == ["Champ. Round 1", "Quarterfinal"]
    assert results.weights == ["125", "133"]
    assert [(r.round, r.weight, r.winner) for r in results.results] == [
        ("Champ. Round 1", "125", "A"), ("Champ. Round 1", "125", "C"),
        ("Champ. Round 1", "133", "E"), ("Quarterfinal", "125", "A"),
    ]


def test_empty_results_container():
    # What the page renders when displayFormatBox is missing: the shell, no sections.
    results = parse_results("<html><div id='results'></div></html>")
    assert (results.bout_count, results.unparsed, results.rounds, results.weights) == (0, 0, [], [])
