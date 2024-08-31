from dydx_v4_client import NodeClient  # Updated import
from dydx_v4_client.constants import OrderSide, TimeInForce
from dydx_v4_client.exceptions import ClientError
from constants import DYDX_ADDRESS
import json
import time
import random
import requests

# Cache for order IDs
order_cache = {}

# Initialize client (Make sure to initialize with appropriate credentials and settings)
client = NodeClient()  # Use NodeClient instead of DYDXClient

# Get Order Details
async def get_order(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot get order details.")
        return {}

    try:
        url = f'https://indexer.v4testnet.dydx.exchange/v4/orders/{order_id}'
        response = requests.get(url)
        response.raise_for_status()
        order_details = response.json()
        order_cache[order_id] = order_details
        return order_details
    except requests.exceptions.HTTPError as e:
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

# Cancel Order
async def cancel_order(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot cancel order.")
        return

    try:
        order = await get_order(client, order_id)
        if not order:
            print(f"Order ID {order_id} not found. Cannot cancel.")
            return

        url = f'https://indexer.v4testnet.dydx.exchange/v4/orders/{order_id}/cancel'
        response = requests.post(url)
        response.raise_for_status()
        print(f"Successfully canceled order ID {order_id}.")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID {order_id} not found during cancellation: {e}")
            order_cache.pop(order_id, None)
        else:
            print(f"HTTP error cancelling order: {e}")
    except Exception as e:
        print(f"Error cancelling order: {e}")

# Place Market Order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        # Logic to place the order (you might need to adjust based on API specifics)
        # Example:
        order_data = {
            "market": market,
            "side": side,
            "size": size,
            "price": price,
            "reduce_only": reduce_only
        }
        
        # Mock URL, replace with actual endpoint
        url = 'https://indexer.v4testnet.dydx.exchange/v4/orders'
        response = requests.post(url, json=order_data)
        response.raise_for_status()
        order_response = response.json()

        # Add the order ID to the cache
        order_id = order_response.get("id")
        if order_id:
            order_cache[order_id] = order_response
        else:
            print("Order ID could not be determined.")

        return (order_response, order_id)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Order ID not found during placement: {e}")
            return (None, None)
        else:
            print(f"HTTP error placing order: {e}")
            return (None, None)
    except Exception as e:
        print(f"Error placing order: {e}")
        return (None, None)

# Get Open Positions
async def get_open_positions(client):
    try:
        url = 'https://indexer.v4testnet.dydx.exchange/v4/positions'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error getting open positions: {e}")
        return {}
    except Exception as e:
        print(f"Error getting open positions: {e}")
        return {}

# Cancel All Orders
async def cancel_all_orders(client):
    try:
        orders = await get_open_positions(client)
        if orders:
            for order in orders:
                await cancel_order(client, order["id"])
            print("All open orders attempted to cancel. Please check the Dashboard.")
    except Exception as e:
        print(f"Error cancelling all orders: {e}")

# Check Order Status
async def check_order_status(client, order_id):
    if not order_id:
        print("Invalid order ID. Cannot check order status.")
        return "FAILED"

    try:
        order = await get_order(client, order_id)
        return order.get("status", "FAILED") if order else "FAILED"
    except requests.exceptions.HTTPError as e:
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

# Check if there are open positions for a specific market
async def is_open_positions(client, market):
    open_positions = await get_open_positions(client)
    return any(pos["market"] == market for pos in open_positions.values())

# Abort All Positions
async def abort_all_positions(client):
    try:
        await cancel_all_orders(client)
        time.sleep(0.5)

        # Get markets for reference of tick size
        markets = await get_markets(client)
        time.sleep(0.5)

        # Get all open positions
        positions = await get_open_positions(client)

        close_orders = []
        if positions:
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
