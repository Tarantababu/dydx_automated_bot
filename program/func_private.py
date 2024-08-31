from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json
from datetime import datetime
from dydx_v4_client.exceptions import HTTPError
import asyncio

# Cache for storing order IDs and details
order_cache = {}

# Function to cancel an order
async def cancel_order(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot cancel order.")
        return
    try:
        order = await get_order_details(client, order_id)
        market = Market((await client.indexer.markets.get_perpetual_markets(order["ticker"]))["markets"][order["ticker"]])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        market_order_id.client_id = int(order["clientId"])
        market_order_id.clob_pair_id = int(order["clobPairId"])
        current_block = await client.node.latest_block_height()
        good_til_block = current_block + 1 + 10

        response = await client.node.cancel_order(
            client.wallet,
            order_id,
            good_til_block=good_til_block,
            good_til_block_time=None  # Optional parameter if needed
        )
        print(f"Cancel response: {response}")
        print(f"Attempted to cancel order for: {order['ticker']}. Please check dashboard to ensure cancelled.")
    except HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID {order_id} not found during cancellation: {e}")
            order_cache.pop(order_id, None)
        else:
            print(f"HTTP error cancelling order: {e}")
    except Exception as e:
        print(f"Error cancelling order: {e}")

# Function to get account details
async def get_account(client):
    account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return account["subaccount"]

# Function to get open positions
async def get_open_positions(client):
    response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return response["subaccount"]["openPerpetualPositions"]

# Function to get order details
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

# Function to place a market order
async def place_market_order(client, market, side, size, price, reduce_only):
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
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price),
                time_in_force=Order.TIME_IN_FORCE_UNSPECIFIED,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            ),
        )

        time.sleep(1.5)
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 
            0, 
            ticker, 
            return_latest_orders="true",
        )

        order_id = ""
        for order in orders:
            client_id = int(order["clientId"])
            clob_pair_id = int(order["clobPairId"])
            order["createdAtHeight"] = int(order["createdAtHeight"])
            if client_id == market_order_id.client_id and clob_pair_id == market_order_id.clob_pair_id:
                order_id = order["id"]
                break

        if order_id == "":
            sorted_orders = sorted(orders, key=lambda x: x["createdAtHeight"], reverse=True)
            print("last order:", sorted_orders[0])
            print("Warning: Unable to detect latest order. Please check dashboard")
            return None, None

        if "code" in str(order):
            print(order)

        return (order, order_id)

    except Exception as e:
        print(f"Error placing order: {e}")
        return None, None

# Function to cancel all open orders
async def cancel_all_orders(client):
    try:
        orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status="OPEN")
        if len(orders) > 0:
            for order in orders:
                await cancel_order(client, order["id"])
                print("You have open orders. Please check the Dashboard to ensure they are cancelled as testnet order requests appear not to be cancelling")
                exit(1)
    except Exception as e:
        print(f"Error cancelling all orders: {e}")

# Function to abort all open positions
async def abort_all_positions(client):
    try:
        await cancel_all_orders(client)
        time.sleep(0.5)
        markets = await get_markets(client)
        time.sleep(0.5)
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
                    market,
                    side,
                    pos["sumOpen"],
                    accept_price,
                    True
                )

                close_orders.append(order)
                time.sleep(0.2)

            with open("bot_agents.json", "w") as f:
                json.dump([], f)

            return close_orders
    except Exception as e:
        print(f"Error aborting all positions: {e}")
