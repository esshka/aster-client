#!/usr/bin/env python
"""
Send Trade - Send trade commands to the ZMQ Trade Listener.

Usage:
    # BUY trade with TP/SL
    poetry run python examples/send_trade.py SOLUSDT buy --sl_percent=0.5 --tp_percent=1.0
    
    # SELL trade
    poetry run python examples/send_trade.py BTCUSDT sell --sl_percent=0.5
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
import zmq


def load_config():
    """Load configuration from config.yml"""
    config_path = Path(__file__).parent.parent / "config.yml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}


def main():
    config = load_config()
    zmq_config = config.get("zmq", {})
    
    parser = argparse.ArgumentParser(description="Send trade commands to ZMQ listener")
    parser.add_argument("symbol", help="Trading symbol (e.g., SOLUSDT)")
    parser.add_argument("side", choices=["buy", "sell"], help="Trade side")
    
    parser.add_argument("--quantity", type=float, help="Order quantity (e.g., 0.01)")
    parser.add_argument("--tp_percent", type=float, help="Take profit percentage (e.g., 1.0 for 1%%)")
    parser.add_argument("--sl_percent", type=float, default=0.5, help="Stop loss percentage (e.g., 0.5 for 0.5%%)")
    parser.add_argument("--ticks_distance", type=int, default=0, help="BBO offset in ticks")
    
    parser.add_argument("--zmq_url", default=zmq_config.get("url", "tcp://127.0.0.1:5556"))
    parser.add_argument("--topic", default=zmq_config.get("topic", "orders"))
    
    args = parser.parse_args()
    
    # Build trade message (accounts will be loaded from config by the listener)
    message = {
        "type": "trade",
        "symbol": args.symbol,
        "side": args.side,
        "sl_percent": args.sl_percent,
        "ticks_distance": args.ticks_distance,
    }
    
    if args.quantity is not None:
        message["quantity"] = args.quantity
    if args.tp_percent is not None:
        message["tp_percent"] = args.tp_percent
    
    # Send message
    ctx = zmq.Context()
    socket = ctx.socket(zmq.PUB)
    socket.bind(args.zmq_url)
    
    # Give subscriber time to connect
    time.sleep(0.5)
    
    # Send as multipart: [topic, payload]
    topic = args.topic.encode()
    payload = json.dumps(message).encode()
    
    socket.send_multipart([topic, payload])
    
    print(f"📤 Sent {args.side.upper()} trade command:")
    print(json.dumps(message, indent=2))
    
    socket.close()
    ctx.term()


if __name__ == "__main__":
    main()
