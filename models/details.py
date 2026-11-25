from dataclasses import dataclass, field
from typing import List, Optional

from models.ttypes import BaseClass


@dataclass
class TournamentTeam(BaseClass):
    id: Optional[int | str]
    name: str
    abbreviation: Optional[str] = None
    season_team: Optional[str] = None
    wrestler_count: Optional[int] = None
    points: Optional[float] = None


@dataclass
class Participant(BaseClass):
    id: Optional[int | str]
    name: str
    first_name: Optional[str]
    last_name: Optional[str]
    team: Optional[str] = None
    team_id: Optional[int | str] = None
    weight_class: Optional[str] = None
    weight_class_id: Optional[int | str] = None
    # Open tournaments group wrestlers into classes ("Junior Boys", "16U Boys").
    division: Optional[str] = None
    division_id: Optional[int | str] = None
    weight: Optional[str] = None
    grade: Optional[str] = None
    record: Optional[str] = None
    scoring: Optional[bool] = None
    qualifying_tournament: Optional[str] = None
    qualifying_place: Optional[str] = None
    # FloWrestling only: final placing ("1".."8"), or None if the wrestler didn't place.
    placement: Optional[str] = None


@dataclass
class WeightClass(BaseClass):
    id: Optional[int | str]
    name: str
    max_weight: Optional[str] = None
    wrestler_count: Optional[int] = None
    bracket_type: Optional[str] = None
    seeds_saved: Optional[bool] = None
    bracket_built: Optional[bool] = None


@dataclass
class TournamentClass(BaseClass):
    """An open tournament's class: an age/gender group with its own weights."""
    id: Optional[int | str]
    name: str
    wrestler_count: Optional[int] = None
    birth_date_range: Optional[str] = None
    style: Optional[str] = None
    pre_registration_fee: Optional[str] = None
    onsite_fee: Optional[str] = None
    registration_limit: Optional[str] = None
    match_length: Optional[str] = None


@dataclass
class Competitor(BaseClass):
    name: str
    team: Optional[str] = None
    record: Optional[str] = None
    # FloWrestling only.
    id: Optional[str] = None
    team_id: Optional[str] = None
    team_abbreviation: Optional[str] = None
    seed: Optional[int] = None


@dataclass
class MatchResult(BaseClass):
    """One bout, or one dual meet in a team tournament (then competitors are teams)."""
    round: Optional[str]
    weight_class: Optional[str]
    winner: Optional[Competitor]
    loser: Optional[Competitor]
    # decision, major_decision, tech_fall, fall, forfeit, medical_forfeit, injury_default,
    # disqualification, sudden_victory, tie_breaker, overtime, bye, dual; None if unrecognised.
    win_type: Optional[str]
    # As TrackWrestling prints it: "Dec 2-1", "Fall 4:11", "TF-1.5 5:45 (19-3)", "M. For."
    result: Optional[str]
    winner_score: Optional[int] = None
    loser_score: Optional[int] = None
    time: Optional[str] = None
    text: str = ""
    # FloWrestling only.
    id: Optional[str] = None
    bout_number: Optional[str] = None


@dataclass
class Placement(BaseClass):
    place: int
    name: str
    team: Optional[str] = None
    # FloWrestling only.
    id: Optional[str] = None


@dataclass
class WeightResults(BaseClass):
    """Placements and bouts for one weight class (or one bracket of a team tournament)."""
    weight_class: str
    placements: List[Placement] = field(default_factory=list)
    matches: List[MatchResult] = field(default_factory=list)


@dataclass
class Option(BaseClass):
    id: int | str
    name: str
    group: Optional[str] = None


@dataclass
class RoundOptions(BaseClass):
    rounds: List[Option]
    weight_classes: List[Option]


@dataclass
class StatsTable(BaseClass):
    stat: str
    available_stats: List[Option]
    rows: List[dict]


@dataclass
class BracketSide(BaseClass):
    id: Optional[str]
    name: str
    team: Optional[str] = None
    team_abbreviation: Optional[str] = None
    seed: Optional[int] = None
    score: Optional[int] = None
    winner: bool = False


@dataclass
class BracketBout(BaseClass):
    id: str
    bout_number: Optional[str]
    round: Optional[str]
    mat: Optional[str]
    state: Optional[str]
    result: Optional[str]
    win_type: Optional[str]
    time: Optional[str]
    top: Optional[BracketSide]
    bottom: Optional[BracketSide]
    # Where the winner and loser go next (other bouts' ids), for drawing the bracket.
    winner_to: Optional[str] = None
    loser_to: Optional[str] = None
    # Column and row in FloWrestling's bracket layout.
    x: Optional[int] = None
    y: Optional[int] = None


@dataclass
class BracketSheet(BaseClass):
    """A whole bracket as data (FloWrestling); TrackWrestling brackets are HTML."""
    id: str
    name: str
    participant_type: Optional[str]
    wrestler_count: Optional[int]
    bouts: List[BracketBout]
    placements: List[Placement]
