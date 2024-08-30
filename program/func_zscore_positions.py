from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions
from func_messaging import send_message

# Send z-scores of all open positions
async def send_zscores_of_open_positions(client):
    # Get all open positions
    open_positions = await get_open_positions(client)
    
    if not open_positions:
        send_message("No open positions to calculate z-scores.")
        return

    message = "Z-Scores of Open Positions:\n"
    
    for position in open_positions:
        market_1 = position["market_1"]
        market_2 = position["market_2"]
        hedge_ratio = position["hedge_ratio"]

        # Get recent candles
        series_1 = await get_candles_recent(client, market_1)
        series_2 = await get_candles_recent(client, market_2)
        
        if len(series_1) > 0 and len(series_1) == len(series_2):
            # Calculate z-score
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]
            message += f"{market_1}/{market_2}: Z-Score = {z_score:.2f}\n"
        else:
            message += f"Error fetching data for {market_1}/{market_2}\n"

    # Send message with z-scores
    send_message(message)
