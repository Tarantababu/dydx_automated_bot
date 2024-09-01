from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market, since_now
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json
from datetime import datetime
import logging
from pprint import pprint

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cancel Order
async def cancel_order(client, order_id):
    try:
        order = await get_order(client, order_id)
        market = Market((await client.indexer.markets.get_perpetual_markets(order["ticker"]))["markets"][order["ticker"]])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        market_order_id.client_id = int(order["clientId"])
        market_order_id.clob_pair_id = int(order["clobPairId"])
        current_block = await client.node.latest_block_height()
        good_til_block = current_block + 1 + 10
        cancel = await client.node.cancel_order(
            client.wallet,
            market_order_id,
            good_til_block=good_til_block
        )
        logger.info(f"Attempted to cancel order for: {order['ticker']}. Please check dashboard to ensure cancelled.")
        return cancel
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise

# Get Account
async def get_account(client):
    try:
        account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return account["subaccount"]
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        raise

# Get Open Positions
async def get_open_positions(client):
    try:
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return response["subaccount"]["openPerpetualPositions"]
    except Exception as e:
        logger.error(f"Error getting open positions: {e}")
        raise

# Get Existing Order
async def get_order(client, order_id):
    try:
        return await client.indexer_account.account.get_order(order_id)
    except Exception as e:
        logger.error(f"Error getting order: {e}")
        raise

# Get existing open positions
async def is_open_positions(client, market):
    try:
        time.sleep(0.2)  # Protect API
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        open_positions = response["subaccount"]["openPerpetualPositions"]
        return any(token == market for token in open_positions.keys())
    except Exception as e:
        logger.error(f"Error checking open positions: {e}")
        raise

# Check order status
async def check_order_status(client, order_id):
    try:
        order = await client.indexer_account.account.get_order(order_id)
        return order.get("status", "FAILED")
    except Exception as e:
        logger.error(f"Error checking order status: {e}")
        raise

# Place market order
async def place_market_order(client, market, side, size, price, reduce_only=False):
    try:
        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                side = Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size = float(size),
                price = float(price),
                time_in_force = Order.TIME_IN_FORCE_FILL_OR_KILL,
                reduce_only = reduce_only,
                good_til_block = good_til_block + 10,
            ),
        )

        time.sleep(1.5)
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 
            0, 
            ticker, 
            return_latest_orders = "true",
        )

        order_id = next((order["id"] for order in orders 
                         if int(order["clientId"]) == market_order_id.client_id 
                         and int(order["clobPairId"]) == market_order_id.clob_pair_id), "")

        if order_id == "":
            sorted_orders = sorted(orders, key=lambda x: int(x["createdAtHeight"]), reverse=True)
            logger.warning(f"Unable to detect latest order. Last order: {sorted_orders[0]}")
            raise Exception("Unable to detect latest order")

        if "code" in str(order):
            logger.error(f"Error in order response: {order}")

        return (order, order_id)
    except Exception as e:
        logger.error(f"Error placing market order: {e}")
        raise

# Get Open Orders
async def cancel_all_orders(client):
    try:
        orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status = "OPEN")
        if orders:
            for order in orders:
                await cancel_order(client, order["id"])
            logger.warning("You have open orders. Please check the Dashboard to ensure they are cancelled as testnet order requests appear not to be cancelling")
    except Exception as e:
        logger.error(f"Error cancelling all orders: {e}")
        raise

# Abort all open positions
async def abort_all_positions(client):
    try:
        await cancel_all_orders(client)
        time.sleep(0.5)  # Protect API
        markets = await get_markets(client)
        time.sleep(0.5)  # Protect API
        positions = await get_open_positions(client)

        close_orders = []
        for item, pos in positions.items():
            market = pos["market"]
            side = "SELL" if pos["side"] == "LONG" else "BUY"
            price = float(pos["entryPrice"])
            accept_price = price * 1.7 if side == "BUY" else price * 0.3
            tick_size = markets["markets"][market]["tickSize"]
            accept_price = format_number(accept_price, tick_size)

            order, order_id = await place_market_order(
                client, 
                market,
                side,
                pos["sumOpen"],
                accept_price,
                True
            )
            close_orders.append(order)
            time.sleep(0.2)  # Protect API

        # Update bot_agents.json
        bot_agents = []
        with open("bot_agents.json", "w") as f:
            json.dump(bot_agents, f)

        return close_orders
    except Exception as e:
        logger.error(f"Error aborting all positions: {e}")
        raise

# Example usage (uncomment if needed)
# if __name__ == "__main__":
#     import asyncio
#     async def main():
#         # Initialize your client here
#         # client = ...
#         # await abort_all_positions(client)
#     asyncio.run(main())