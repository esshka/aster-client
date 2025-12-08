"""
ZMQ Heartbeat Sender Demo

This script demonstrates sending heartbeat messages followed by trade messages
to the ZMQ listener, similar to how the TradesExecutor would behave.
"""

import zmq
import json
import time
from datetime import datetime, timezone
import os
from dotenv import load_dotenv


def main():
    load_dotenv()
    port = os.getenv("ZMQ_PORT", "5555")
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{port}")
    
    print(f"🚀 ZMQ Publisher started on tcp://*:{port}")
    print("⏳ Waiting for subscribers to connect...")
    time.sleep(2)  # Allow time for connection
    
    # Send heartbeat message
    print("\n" + "="*60)
    print("📡 Sending heartbeat message...")
    print("="*60)
    
    heartbeat_message = {
        "type": "heartbeat",
        "status": "connected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "TradesExecutor initialized and ready to send signals",
        "accounts_loaded": 2
    }
    
    socket.send_json(heartbeat_message)
    print("✅ Heartbeat sent:")
    print(json.dumps(heartbeat_message, indent=2))
    
    time.sleep(2)
    
    # Send a trade message
    print("\n" + "="*60)
    print("📊 Sending trade command...")
    print("="*60)
    
    trade_message = {
        "type": "trade",  # Optional: if not specified, defaults to "trade"
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
    
    socket.send_json(trade_message)
    print(f"✅ Trade command sent for {trade_message['symbol']}")
    print(f"   - Side: {trade_message['side']}")
    print(f"   - Accounts: {len(trade_message['accounts'])}")
    print(f"   - TP: {trade_message['tp_percent']}%")
    print(f"   - SL: {trade_message['sl_percent']}%")
    
    time.sleep(1)
    
    print("\n" + "="*60)
    print("✅ All messages sent successfully!")
    print("="*60)
    
    socket.close()
    context.term()


if __name__ == "__main__":
    main()
