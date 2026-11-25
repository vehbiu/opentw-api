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
    venue_street: Optional[str] = None
    registration_url: Optional[str] = None
    # Where the data came from: "trackwrestling", or "flowrestling" for tournaments
    # TrackWrestling has handed over (then the FloWrestling event id and page are set too).
    source: str = "trackwrestling"
    flowrestling_event_id: Optional[str] = None
    flowrestling_url: Optional[str] = None

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
class TeamScore(BaseClass):
    rank: int
    team: str
    score: float
    # Open tournaments only.
    abbreviation: Optional[str] = None
    # FloWrestling only: the team's id, and the standings group when a tournament scores
    # several (one per division on open tournaments).
    team_id: Optional[str] = None
    group: Optional[str] = None


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
    # Freestyle tournaments only.
    bracket_rows: Optional[int] = None

@dataclass
class Division(BaseClass):
    division_index: int
    division_id: int | str
    division_name: str

@dataclass
class Weight(BaseClass):
    weight_index: int
    weight_id: int | str
    weight_name: str
    bracket_id: int | str

    # Only open tournaments send divisions, so only their weights carry a division id.
    # Predefined and team tournaments leave it as None.
    division_id: Optional[int | str] = None

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


