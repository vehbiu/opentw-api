from typing import Optional
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal, List

class BaseClass:
    def as_dict(self):
        data = self.__dict__.copy()
        for key, value in data.items():
            if isinstance(value, BaseClass):
                data[key] = value.as_dict()
            elif isinstance(value, list):
                data[key] = [v.as_dict() if isinstance(v, BaseClass) else v for v in value]
        return data

class EventType(Enum):
    PREDEFINED  = (1, "predefinedtournaments", "predefined")
    OPEN        = (2, "opentournaments", "open")
    TEAM        = (3, "teamtournaments", "team")
    FREESTYLE   = (4, "freestyletournaments", "freestyle")
    SEASON      = (5, "seasontournaments", "season")

    def __init__(self, value: str, tournament_type: str, alias: str) -> "EventType":
        self._value_: str = value
        self.tournament_type: str = tournament_type
        self.alias: str = alias

    
    @classmethod
    def from_id(cls, id: int) -> "EventType":
        for event_type in cls:
            if event_type.value == id:
                return event_type
        raise ValueError(f"Invalid event type ID: {id}")
    
    @classmethod
    def from_alias(cls, alias: str) -> "EventType":
        for event_type in cls:
            if event_type.alias == alias:
                return event_type
        raise ValueError(f"Invalid event type alias: {alias}")

Status = Literal["in_progress", "on_deck", "in_hole"]

@dataclass
class Team(BaseClass):
    id: str
    name: str
    shortName: str

@dataclass
class Wrestler(BaseClass):
    id: str
    first_name: str
    last_name: str
    team: Team
    record: Optional[str] = None
    year: Optional[str] = None

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

@dataclass
class Match(BaseClass):
    mat: int
    bout: int
    status: Status
    weight_class: str
    round: str
    wrestler1: Wrestler
    wrestler2: Wrestler


@dataclass
class Tournament(BaseClass):
    """Represents a wrestling tournament from Trackwrestling"""
    id: int
    name: str
    # event_type: int  # 1=Predefined, 2=Open, 3=Team, 4=Freestyle, 5=Season
    event_type: EventType
    start_date: Optional[date]
    end_date: Optional[date]
    venue_name: Optional[str]
    venue_city: Optional[str] 
    venue_state: Optional[str]
    venue_zip: Optional[str]
    logo_url: Optional[str]
    event_flyer_url: Optional[str]
    website_url: Optional[str]

    def as_dict(self: "Tournament") -> dict:
        return {
            **super().as_dict(),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "event_type": self.event_type.alias,
            # "logo_url": self.logo_url if self.logo_url else "https://via.placeholder.com/600x150?text=No+Logo",
            "logo_url": self.logo_url if self.logo_url else "https://www.trackwrestling.com/images/tw_logo.png",
        }
    

# BRACKETS
# @dataclass
# class Weight(BaseClass):
#     id: int
#     division_id: int
#     bracket_id: int
#     weight_class: str
#     participants: int

# @dataclass
# class Division(BaseClass):
#     division_id: int
#     division_name: str
#     weights: List[Weight]

# @dataclass
# class BracketData(BaseClass):
#     divisions: List[Division]
#     weights: List[Weight]

@dataclass
class BracketPage(BaseClass):
    page_index: int
    page_id: int  
    page_name: str
    show_page: bool

@dataclass
class Template(BaseClass):
    template_index: int
    bracket_id: int
    template_id: int
    template_name: str
    bracket_width: int
    bracket_height: int 
    bracket_font: int
    pages: List[BracketPage]

@dataclass
class Division(BaseClass):
    division_index: int
    division_id: int
    division_name: str

@dataclass
class Weight(BaseClass):
    weight_index: int
    weight_id: int
    weight_name: str
    bracket_id: int

    # TrackWrestling dropped divisions from BracketViewer's payload: weights used to carry a
    # division id and no longer do. Optional rather than removed, so a tournament type that
    # still sends the older four-field shape keeps its value. Nothing downstream reads it.
    division_id: Optional[int] = None

@dataclass
class BracketType(BaseClass):
    bracket_id: int
    default_template_index: int = 0

@dataclass
class BracketData(BaseClass):
    divisions: List[Division]
    weights: List[Weight]
    templates: List[Template]
    bracket_types: List[BracketType]




@dataclass
class BracketEntry(BaseClass):
    """One first-round slot on a bracket sheet, in bracket order.

    `seed` is None where the sheet prints no seed; TrackWrestling renders an unseeded slot with a
    non-breaking space, so "unseeded" comes from the page rather than being inferred.
    `qualifying_rank` is Division III's trailing "(5)" - a regional rank, not a seed.
    """
    wrestler_id: str
    team_id: str
    name: str
    school: str
    seed: Optional[int] = None
    record: Optional[str] = None
    qualifying_rank: Optional[int] = None


@dataclass
class PigtailEntrant(BaseClass):
    """A wrestler the sheet mentions who never holds a first-round slot.

    `partial` is True when the sheet only prints a surname and team abbreviation
    ("Schafer, BLOO") - D1 and D3 do this for pigtail losers - so `name` is not a full name.
    """
    wrestler_id: str
    text: str
    entry: BracketEntry
    partial: bool


Route = Literal["loser_of", "to_top_of", "to_bottom_of"]


@dataclass
class BracketRoute(BaseClass):
    """A routing hint printed on the sheet: "To bottom of 11", "Loser of 19".

    Only pigtails and consolation feeds carry these, and they are the part of a bracket that
    varies by division (D2 sends pigtail winners to seeds 8 and 7, D3 to seeds 1-5).
    """
    kind: Route
    bout: int


@dataclass
class BracketSheet(BaseClass):
    entries: List[BracketEntry]
    bout_numbers: List[int]
    pigtail_entrants: List[PigtailEntrant]
    routes: List[BracketRoute]


@dataclass
class BoutResult(BaseClass):
    """One line of RoundResults.jsp.

    `result_code` is kept exactly as the site writes it (Dec, MD, Fall, TF-1.5, SV-1, TB-2,
    2-OT, Inj., DQ, M. For., MFFL, For). "M. For." and "MFFL" are the same outcome written two
    ways; "For" is a plain forfeit. A line that cannot be read comes back with `parsed` False
    and its `text` intact rather than being dropped.
    """
    round: str
    weight: str
    parsed: bool
    text: str
    bout_label: Optional[str] = None
    winner: Optional[str] = None
    winner_school: Optional[str] = None
    winner_record: Optional[str] = None
    loser: Optional[str] = None
    loser_school: Optional[str] = None
    loser_record: Optional[str] = None
    method: Optional[str] = None
    result: Optional[str] = None
    result_code: Optional[str] = None
    result_detail: Optional[str] = None


@dataclass
class TournamentResults(BaseClass):
    bout_count: int
    unparsed: int
    rounds: List[str]
    weights: List[str]
    results: List[BoutResult]
