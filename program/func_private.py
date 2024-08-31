from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from dydx_v4_client.node.message import cancel_order as dydx_cancel_order
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json
from datetime import datetime
from pprint import pprint
from requests.exceptions import HTTPError

# Cache for order IDs
order_cache = {}

# Cancel Order
async def cancel_order(client, wallet, order_id, good_til_block, good_til_block_time):
    if not order_id:
        print("Invalid order ID. Cannot cancel order.")
        return

    try:
        # Cancel order using dydx_cancel_order function
        cancel_order_msg = dydx_cancel_order(
            order_id,
            good_til_block,
            good_til_block_time
        )
        response = await client.node.cancel_order(
            wallet,
            order_id,
            good_til_block=good_til_block,
            good_til_block_time=good_til_block_time
        )
        print(response)
        print(f"Attempted to cancel order for ID {order_id}.")
    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID {order_id} not found during cancellation: {e}")
            order_cache.pop(order_id, None)
        else:
            print(f"HTTP error cancelling order: {e}")
    except Exception as e:
        print(f"Error cancelling order: {e}")

# Get Account
async def get_account(client):
    account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return account["subaccount"]

# Get Open Positions
async def get_open_positions(client):
    response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return response["subaccount"]["openPerpetualPositions"]

# Get Specific Order Details
async def get_order_details(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot get order details.")
        return {}
    try:
        return await client.indexer_account.account.get_order(order_id)
    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID {order_id} not found during retrieval: {e}")
            order_cache.pop(order_id, None)
            return {}
        else:
            print(f"HTTP error getting order details: {e}")
            return {}
    except Exception as e:
        print(f"Error getting order details: {e}")
        return {}

# Check Order Status
async def check_order_status(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot check order status.")
        return "FAILED"

    try:
        order = await get_order_details(client, order_id)
        return order["status"] if "status" in order else "FAILED"
    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID {order_id} not found during status check: {e}")
            order_cache.pop(order_id, None)
            return "NOT_FOUND"
        else:
            print(f"HTTP error checking order status: {e}")
            return "FAILED"
    except Exception as e:
        print(f"Error checking order status: {e}")
        return "FAILED"

# Place Market Order
async def place_market_order(client, wallet, market, side, size, price, reduce_only):
    try:
        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10
        good_til_block_time = time.time() + 60  # Example: 60 seconds from now
        
        order = await client.node.place_order(
            wallet,
            market.order(
                market_order_id,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price),
                time_in_force=Order.TIME_IN_FORCE_UNSPECIFIED,
                reduce_only=reduce_only,
                good_til_block=good_til_block,
                good_til_block_time=good_til_block_time
            ),
        )
        
        # Add the order ID to the cache
        order_id = None
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 
            0, 
            ticker, 
            return_latest_orders="true",
        )
        
        for order in orders:
            client_id = int(order["clientId"])
            clob_pair_id = int(order["clobPairId"])
            if client_id == market_order_id.client_id and clob_pair_id == market_order_id.clob_pair_id:
                order_id = order["id"]
                order_cache[order_id] = order
                break

        if not order_id:
            raise Exception("Order ID could not be determined.")
        
        return (order, order_id)
    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID not found during placement: {e}")
            return (None, None)
        else:
            print(f"HTTP error placing order: {e}")
            return (None, None)
    except Exception as e:
        print(f"Error placing order: {e}")
        return (None, None)

# Get Open Orders
async def cancel_all_orders(client, wallet):
    try:
        orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status="OPEN")
        if len(orders) > 0:
            current_block = await client.node.latest_block_height()
            good_til_block = current_block + 1 + 10
            good_til_block_time = time.time() + 60  # Example: 60 seconds from now

            for order in orders:
                await cancel_order(client, wallet, order["id"], good_til_block, good_til_block_time)
            print("You have open orders. Please check the Dashboard to ensure they are cancelled as testnet order requests appear not to be cancelling")
    except Exception as e:
        print(f"Error cancelling all orders: {e}")

# Check if there are open positions for a specific market
async def is_open_positions(client, market):
    open_positions = await get_open_positions(client)
    return any(pos["market"] == market for pos in open_positions.values())

# Abort all open positions
async def abort_all_positions(client, wallet):
    try:
        # Cancel all orders
        await cancel_all_orders(client, wallet)

        time.sleep(0.5)

        # Get markets for reference of tick size
        markets = await get_markets(client)

        time.sleep(0.5)

        # Get all open positions
        positions = await get_open_positions(client)

        close_orders = []
        if len(positions) > 0:
            for item in positions.keys():
                pos = positions[item]
                market = pos["market"]
                side = "BUY" if pos["side"] == "LONG" else "SELL"
                price = float(pos["entryPrice"])
                accept_price = price * 1.7 if side == "BUY" else price * 0.3
                tick_size = markets["markets"][market]["tickSize"]
                accept_price = format_number(accept_price, tick_size)

                (order, order_id) = await place_market_order(
                    client, 
                    wallet,
                    market,
                    side,
                    pos["sumOpen"],
                    accept_price,
                    True
                )

                if order and order_id:
                    close_orders.append(order)
                else:
                    print(f"Failed to place close order for {market}. Skipping.")

                time.sleep(0.2)

            # Override json file with empty list
            bot_agents = []
            with open("bot_agents.json", "w") as f:
                json.dump(bot_agents, f)

        return close_orders
    except Exception as e:
        print(f"Error aborting all positions: {e}")
