import zmq
import json
import time
import random
import os
from dotenv import load_dotenv

def main():
    load_dotenv()
    port = os.getenv("ZMQ_PORT", "5555")
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{port}")
    
    print(f"ZMQ Publisher started on tcp://*:{port}")
    print("Waiting for subscribers...")
    time.sleep(1)  # Allow time for connection
    
    # Sample trade message
    message = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "tp_percent": 1.0,
        "sl_percent": 0.5,
        "ticks_distance": 2,
        "accounts": [
            {
                "id": "acc1",
                "api_key": "DEMO_KEY_1_0000000000000000000000000000000000000000000000000",
                "api_secret": "DEMO_SECRET_1_000000000000000000000000000000000000000000000",
                "quantity": "0.001",
                "simulation": True
            },
            {
                "id": "acc2",
                "api_key": "DEMO_KEY_2_0000000000000000000000000000000000000000000000000",
                "api_secret": "DEMO_SECRET_2_000000000000000000000000000000000000000000000",
                "quantity": "0.002",
                "simulation": True
            }
        ]
    }
    
    print(f"Sending trade command for {message['symbol']}...")
    socket.send_json(message)
    print("Sent!")
    time.sleep(1) # Give time to send


if __name__ == "__main__":
    main()
