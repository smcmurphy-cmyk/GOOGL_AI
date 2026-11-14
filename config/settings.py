from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Config:
    use_live_schwab_data: bool = True  # Set to True when trading live
    schwab_app_key: str = "YOUR_KEY"

class Settings(BaseSettings):
    # API & External Endpoints
    google_api_key: str = Field(..., description="Google GenAI SDK API Key")
    webhook_url: str = Field(..., description="Discord/Slack or Google Sheet Webhook URL")
    use_live_schwab_data: bool = True
    schwab_app_key: str
    schwab_app_secret: str
    schwab_refresh_token: str
    # Portfolio & Risk Limits
    max_daily_risk_pct: float = Field(0.05, description="Maximum total portfolio risk per day (e.g., 0.02 for 2%)")
    max_trade_risk_pct: float = Field(0.03, description="Maximum risk per single structure (e.g., 0.01 for 1%)")
    min_volume: int = Field(500, description="Minimum daily volume for liquidity filter")
    min_open_interest: int = Field(1000, description="Minimum open interest for liquidity filter")
    max_bid_ask_spread: float = Field(0.15, description="Maximum allowable spread in dollars")

    # Load from the local .env file
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

# Instantiate a global settings object to import across modules
config = Settings()