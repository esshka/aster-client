"""
Send Signal - Send test signals to the ZMQ Signal Listener.

Usage:
    # ENTRY signal
    python examples/send_signal.py ENTRY LONG SOLUSDT 150.0 --sl=148.0 --size_r=20
    
    # EXIT signal
    python examples/send_signal.py EXIT LONG SOLUSDT 155.0 --reason="ML Exit"
    
    # PARTIAL_EXIT signal (50% close with SL to BE)
    python examples/send_signal.py PARTIAL_EXIT LONG SOLUSDT 152.0 --exit_pct=0.5 --move_sl_to_be
"""

import argparse
import json
import sys
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
    
    parser = argparse.ArgumentParser(description="Send test signals to ZMQ listener")
    parser.add_argument("action", choices=["ENTRY", "EXIT", "PARTIAL_EXIT"])
    parser.add_argument("direction", choices=["LONG", "SHORT"])
    parser.add_argument("symbol", help="Trading symbol (e.g., SOLUSDT)")
    parser.add_argument("price", type=float, help="Current price")
    
    parser.add_argument("--sl", type=float, help="Stop loss price")
    parser.add_argument("--tp", type=float, help="Take profit price")
    parser.add_argument("--size_r", type=float, default=20.0, help="Position size in R units")
    parser.add_argument("--exit_pct", type=float, default=0.5, help="Exit percentage for PARTIAL_EXIT")
    parser.add_argument("--remaining_pct", type=float, help="Remaining percentage after exit")
    parser.add_argument("--move_sl_to_be", action="store_true", help="Move SL to break-even")
    parser.add_argument("--reason", help="Reason for signal")
    parser.add_argument("--confidence", type=float, help="Model confidence (0-1)")
    
    parser.add_argument("--zmq_url", default=zmq_config.get("url", "tcp://127.0.0.1:5556"), help="ZMQ URL")
    parser.add_argument("--topic", default=zmq_config.get("topic", "orders"), help="ZMQ topic")
    
    args = parser.parse_args()
    
    # Build message
    message = {
        "type": "signal",
        "action": args.action,
        "direction": args.direction,
        "symbol": args.symbol,
        "price": args.price,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if args.sl:
        message["stop_loss"] = args.sl
    if args.tp:
        message["take_profit"] = args.tp
    if args.action == "ENTRY":
        message["position_size_r"] = args.size_r
    if args.action == "PARTIAL_EXIT":
        message["exit_pct"] = args.exit_pct
        if args.remaining_pct:
            message["remaining_pct"] = args.remaining_pct
        message["move_sl_to_be"] = args.move_sl_to_be
    if args.reason:
        message["reason"] = args.reason
    if args.confidence is not None:
        message["confidence"] = args.confidence
    
    # Send message
    ctx = zmq.Context()
    socket = ctx.socket(zmq.PUB)
    socket.bind(args.zmq_url)
    
    # Give subscriber time to connect
    import time
    time.sleep(0.5)
    
    # Send as multipart: [topic, payload]
    topic = args.topic.encode()
    payload = json.dumps(message).encode()
    
    socket.send_multipart([topic, payload])
    
    print(f"📤 Sent {args.action} signal:")
    print(json.dumps(message, indent=2))
    
    socket.close()
    ctx.term()


if __name__ == "__main__":
    main()
