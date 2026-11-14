import os
from google import genai
from google.genai import types
from models.alerts import ScoredPlay
from models.regime import RegimeState
from config.settings import config

def generate_trade_thesis(ticker: str, regime: RegimeState, play: ScoredPlay) -> str:
    """
    Leverages the Google GenAI SDK to synthesize a 1-2 sentence quantitative thesis 
    based on the structured single-leg output of the Expectancy Scorer.
    """
    client = genai.Client(api_key=config.google_api_key)
    
    system_instruction = (
        "You are an expert quantitative options trading assistant. "
        "Your task is to write a concise, 1-2 sentence webhook alert summarizing a directional options trade. "
        "Explicitly state WHY the trade was selected by connecting the GEX regime to the chosen contract delta and its defined risk-to-reward targets. "
        "Do not offer financial advice; maintain a strictly quantitative and professional tone."
    )
    
    strategy = play.structure.strategy_type.replace('_', ' ').title()
    
    prompt_payload = f"""
    Ticker: {ticker}
    Macro Regime: {regime.regime_type} (Net GEX: ${regime.net_gex:,.0f}, IV Rank: {regime.iv_rank}%)
    Structure: {strategy}
    Target Strike: {play.structure.contract.strike}
    Entry Premium: ${play.structure.entry_premium:.2f}
    Stop-Loss Trigger: ${play.structure.stop_loss_premium:.2f} (Invalidation)
    Take-Profit Target: ${play.structure.target_exit_premium:.2f}
    Max Risk per Contract: ${play.structure.max_risk_per_contract:.2f}
    Mathematical Expectancy (R-Multiple): {play.score:.2f}
    Net Delta Exposure: {play.structure.net_delta:.2f}
    
    Generate the alert thesis now.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt_payload,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,  
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"System alert generated for {ticker} {strategy} based on {regime.regime_type} metrics. (LLM synthesis failed: {e})"