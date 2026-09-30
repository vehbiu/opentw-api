"""BracketViewer.jsp's inline data: templates, divisions, weights, bracket types."""
import pytest

from models.ttypes import EventType, Template
from parsers.tournaments import (
    _parse_bracket_types,
    _parse_templates,
    _parse_weights,
    generate_bracket_url,
    parse_bracket_data,
)

TEMPLATE = "4~0~Default Template~670~870~8~4,Top Bracket,5,Bottom Bracket"


def viewer(*payloads: str) -> str:
    body = "\n".join(f'str = "{p}";' for p in payloads)
    return f"<html><script>var p = new Pile();\n{body}\n</script></html>"


def test_templates():
    [t] = _parse_templates(TEMPLATE)
    assert (t.bracket_id, t.template_id, t.template_name) == (4, 0, "Default Template")
    assert (t.bracket_width, t.bracket_height, t.bracket_font) == ("670", "870", "8")
    assert [(p.page_id, p.page_name, p.show_page) for p in t.pages] == [
        (4, "Top Bracket", True), (5, "Bottom Bracket", False),
    ]


def test_several_templates_are_indexed():
    templates = _parse_templates(TEMPLATE + "~" + TEMPLATE.replace("4~0~Default", "106~7~Other"))
    assert [(t.template_index, t.bracket_id, t.template_id) for t in templates] == [(0, 4, 0), (1, 106, 7)]


def test_bracket_types():
    assert [b.bracket_id for b in _parse_bracket_types("4,106,163")] == [4, 106, 163]
    assert _parse_bracket_types("") == []


def test_weights_current_shape():
    weights = _parse_weights("11~125~5~12~133~5~13~141~5~14~149~5", with_division=False)
    assert [(w.weight_index, w.weight_id, w.weight_name, w.bracket_id, w.division_id) for w in weights] == [
        (0, 11, "125", 5, None), (1, 12, "133", 5, None), (2, 13, "141", 5, None), (3, 14, "149", 5, None),
    ]


def test_weights_older_shape():
    # Twelve entries fit both a 3- and a 4-field reading when names are numeric; the shape
    # has to come from the layout, not from the data.
    weights = _parse_weights("1~11~125~5~1~12~133~5~1~13~141~5", with_division=True)
    assert [(w.division_id, w.weight_id, w.weight_name, w.bracket_id) for w in weights] == [
        (1, 11, "125", 5), (1, 12, "133", 5), (1, 13, "141", 5),
    ]


def test_weights_non_numeric_names():
    weights = _parse_weights("11~Heavyweight~5~12~106 lbs~5", with_division=False)
    assert [w.weight_name for w in weights] == ["Heavyweight", "106 lbs"]


def test_weights_that_do_not_divide_raise():
    with pytest.raises(ValueError, match="not a multiple of 3"):
        _parse_weights("11~125~5~12~133", with_division=False)


def test_weights_empty():
    assert _parse_weights("", with_division=False) == []


def test_three_block_layout():
    data = parse_bracket_data(viewer(TEMPLATE, "11~125~4~12~133~4~13~141~4~14~149~4", "4"))
    assert data.divisions == []
    assert [w.weight_name for w in data.weights] == ["125", "133", "141", "149"]
    assert len(data.templates) == 1
    assert [b.bracket_id for b in data.bracket_types] == [4]


def test_four_block_layout():
    data = parse_bracket_data(viewer(TEMPLATE, "1~Varsity~2~JV", "1~11~125~4~2~12~133~4~1~13~141~4", "4"))
    assert [(d.division_id, d.division_name) for d in data.divisions] == [(1, "Varsity"), (2, "JV")]
    assert [(w.division_id, w.weight_name) for w in data.weights] == [(1, "125"), (2, "133"), (1, "141")]


def test_spacing_around_assignment_does_not_matter():
    html = viewer(TEMPLATE, "11~125~4", "4").replace('str = "', 'str="')
    assert [w.weight_name for w in parse_bracket_data(html).weights] == ["125"]


def test_page_without_data_raises():
    with pytest.raises(ValueError, match="Could not find bracket data"):
        parse_bracket_data("<html><script>nothing here</script></html>")


def test_too_few_blocks_raises():
    with pytest.raises(ValueError, match="expected at least 3"):
        parse_bracket_data(viewer(TEMPLATE, "4"))


def test_too_many_blocks_raises():
    with pytest.raises(ValueError, match="Unrecognised"):
        parse_bracket_data(viewer(TEMPLATE, "a", "b", "c", "4"))


def test_bracket_url_uses_the_template():
    template = Template(0, 4, 7, "T", 700, 590, 8, [])
    url = generate_bracket_url(EventType.OPEN, 123, template, pages=[0, 2])
    assert url.startswith("https://www.trackwrestling.com/opentournaments/Bracket.jsp?")
    for part in ("groupId=123", "bracketWidth=700", "bracketHeight=590", "bracketFontSize=8",
                 "includePages=0,2", "templateId=7"):
        assert part in url


def test_bracket_url_defaults():
    url = generate_bracket_url(EventType.PREDEFINED, 123)
    for part in ("bracketWidth=700", "bracketHeight=590", "bracketFontSize=8", "includePages=&", "templateId="):
        assert part in url
    assert "chartWidth" not in url
