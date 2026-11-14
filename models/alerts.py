from pydantic import BaseModel
from models.regime import RegimeState
from models.structures import OptionStructure

class ScoredPlay(BaseModel):
    """
    The final packaged trade alert that gets pushed to the webhook.
    """
    ticker: str
    regime: RegimeState
    structure: OptionStructure
    expectancy_score: float = 0.0