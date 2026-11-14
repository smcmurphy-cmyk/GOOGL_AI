import asyncio
from config.settings import config

# Import pipeline states
from data_ingestion.schwab_fetcher import get_live_market_data as get_schwab_data, get_valid_access_token
from data_ingestion.cboe_fetcher import get_market_data as get_cboe_data #[cite: 5] FIX: Added alias
from core_logic.regime_classifier import classify_regime
from core_logic.structure_builder import generate_structures
from core_logic.expectancy_scorer import evaluate_and_rank
from core_logic.portfolio_risk import portfolio_gatekeeper
from synthesis.agent_llm import generate_trade_thesis
from dissemination.sheet_webhook import post_to_sheet

# Hardcoded for the test run. Later, move this to config/universe.py
MEGA_CAP_TICKERS = ["TSLA", "QQQ", "SPY"] #[cite: 5]

async def run_pipeline(ticker: str, session_open_risk_usd: float, access_token: str = None):
    print(f"\n--- Starting Pipeline for {ticker} ---")
    print("[1/6] Ingesting Market Data...")
    
    # 1. Route the data ingestion
    if config.use_live_schwab_data:
        # Pass the token through to the fetcher
        chain = await get_schwab_data(ticker, access_token=access_token) 
    else:
        print("  [Data] Using delayed CBOE feed (Weekend/Testing mode)...")
        chain = get_cboe_data(ticker)
        
    if not chain or not chain.contracts:
        return session_open_risk_usd

    print("[2/6] Classifying Macro Regime...")
    # Mocking historical IV for the test run. You will need to wire this to a historical DB later.
    mock_iv_low, mock_iv_high = 0.20, 0.60  #[cite: 5]
    regime = classify_regime(chain, mock_iv_low, mock_iv_high) #[cite: 5]
    print(f"      -> {regime.regime_type} (GEX: ${regime.net_gex:,.0f})") #[cite: 5]

    if not regime.is_tradeable:
        print(f"[-] {ticker} regime is UNCERTAIN. Skipping.") #[cite: 5]
        return session_open_risk_usd #[cite: 5] FIX: matched variable name

    # STATE 3: STRUCTURE GENERATION
    print("[3/6] Generating Defined-Risk Structures...")
    structures = generate_structures(chain, regime) #[cite: 5]
    if not structures:
        print(f"[-] No valid structures found for {ticker} in current regime.") #[cite: 5]
        return session_open_risk_usd #[cite: 5] FIX: matched variable name

    # STATE 4: EXPECTANCY SCORING
    print(f"[4/6] Scoring Expectancy on {len(structures)} candidate structures...") #[cite: 5]
    # Assuming a $10,000 account for the risk calculations
    scored_plays = evaluate_and_rank(structures, account_balance=10000.0) #[cite: 5]
    
    if not scored_plays:
        print("[-] No structures passed the strict R-Multiple and Risk limits.") #[cite: 5]
        return session_open_risk_usd #[cite: 5] FIX: matched variable name
        
    top_play = scored_plays[0] #[cite: 5]
    print(f"      -> Top Play: {top_play.structure.strategy_type} | Score: {top_play.score:.2f}R") #[cite: 5]

    # STATE 5: PORTFOLIO GATEKEEPER
    print("[5/6] Checking Portfolio Risk Budget...")
    if not portfolio_gatekeeper(top_play, session_open_risk_usd, account_balance=10000.0): #[cite: 5] FIX: matched variable name
        print("[-] Trade rejected: Executing this would breach maximum daily risk.") #[cite: 5]
        return session_open_risk_usd #[cite: 5] FIX: matched variable name

    # STATE 6: SYNTHESIS & DISSEMINATION
    print("[6/6] Synthesizing LLM Thesis and Dispatching Webhook...")
    thesis = generate_trade_thesis(ticker, regime, top_play) #[cite: 5]
    
    # POST to webhook (Ensure your .env has WEBHOOK_URL defined)
    success = await post_to_sheet(ticker, regime, top_play, thesis) #[cite: 5]
    
    if success:
        print("[+] Alert successfully dispatched!") #[cite: 5]
        # Add the new risk to our running total
        return session_open_risk_usd + top_play.account_risk_usd #[cite: 5] FIX: matched variable name
    else:
        print("[-] Failed to dispatch webhook.") #[cite: 5]
        return session_open_risk_usd #[cite: 5] FIX: matched variable name

async def main():
    print("INITIALIZING MEGA-CAP OPTIONS AGENT...")
    
    # Fetch the Access Token ONCE per session to avoid rate limits
    session_access_token = None
    if config.use_live_schwab_data:
        print("[+] Authenticating with Schwab API...")
        session_access_token = await get_valid_access_token()
        print("[+] Live Token Acquired.")

    # Track accumulated risk across the session to feed the gatekeeper
    session_open_risk_usd = 0.0 
    
    for ticker in MEGA_CAP_TICKERS:
        # Pass the generated token into the pipeline
        session_open_risk_usd = await run_pipeline(
            ticker, 
            session_open_risk_usd, 
            access_token=session_access_token
        ) 
        await asyncio.sleep(2) 
        
    print("\nSESSION COMPLETE.") 
    print(f"Total Projected Risk Allocated: ${session_open_risk_usd:,.2f}")

if __name__ == "__main__":
    asyncio.run(main()) #[cite: 5]