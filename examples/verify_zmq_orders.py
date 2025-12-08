import asyncio
import zmq
import zmq.asyncio
import json
import os
import random
from dotenv import load_dotenv

async def main():
    load_dotenv()
    zmq_url = os.environ.get("ZMQ_URL", "tcp://127.0.0.1:5555")
    ctx = zmq.asyncio.Context()
    socket = ctx.socket(zmq.PUB)
    socket.bind(zmq_url)
    
    # Give it a moment to connect
    await asyncio.sleep(1)
    
    print(f"Publisher bound to {zmq_url}")
    
    # Get credentials from env
    api_key = os.environ.get("ASTER_API_KEY", "")
    api_secret = os.environ.get("ASTER_API_SECRET", "")
    
    if not api_key or len(api_key) < 20:
        print("WARNING: ASTER_API_KEY not found or too short in .env, using dummy key (will fail validation)")
        api_key = "dummy_key_that_is_long_enough_to_pass_length_check_xxxxxxxx"
    
    if not api_secret:
        api_secret = "dummy_secret"

    # Test BBO Order
    bbo_msg = {
        "type": "order",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "bbo",
        "ticks_distance": 1,
        "accounts": [
            {
                "id": "acc_1",
                "api_key": api_key, 
                "api_secret": api_secret,
                "quantity": 0.001,
                "simulation": True
            }
        ]
    }
    
    print("Sending BBO order...")
    await socket.send_string(json.dumps(bbo_msg))
    await asyncio.sleep(1)

    # Test Limit Order
    limit_msg = {
        "type": "order",
        "symbol": "BTCUSDT",
        "side": "sell",
        "order_type": "limit",
        "price": 99000.0,
        "time_in_force": "gtc",
        "accounts": [
            {
                "id": "acc_1",
                "api_key": api_key, 
                "api_secret": api_secret,
                "quantity": 0.001,
                "simulation": True
            }
        ]
    }
    
    print("Sending Limit order...")
    await socket.send_string(json.dumps(limit_msg))
    await asyncio.sleep(1)

    socket.close()
    ctx.term()
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
