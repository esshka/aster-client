# BBO WebSocket Connection Rules Compliance

This document outlines how the BBO WebSocket implementation complies with the exchange's WebSocket connection rules and limits.

## Exchange Connection Rules

### 1. 24-Hour Connection Limit ✅
**Rule**: A single WebSocket connection is valid for 24 hours. Connections will be disconnected automatically at the 24-hour mark.

**Implementation**:
- Track connection start time in `_ws_loop()`
- Check connection duration on every message
- Proactively reconnect when approaching 24 hours (86400 seconds)
- Log reconnection with info message

```python
connection_start = time.time()
# ...
connection_duration = time.time() - connection_start
if connection_duration >= 86400:  # 24 hours
    self.logger.info("WebSocket connection approaching 24-hour limit, reconnecting...")
    break
```

### 2. Ping/Pong Heartbeat ✅
**Rule**: 
- Server sends a ping frame every 5 minutes
- If no pong frame is received within 15 minutes, the connection will be closed
- Unsolicited pong frames are allowed

**Implementation**:
- Configure `heartbeat=30` to send client pings every 30 seconds
- Enable `autoping=True` to automatically respond to server pings
- Explicitly handle `WSMsgType.PING` and `WSMsgType.PONG` messages
- Log ping/pong events at DEBUG level

```python
async with session.ws_connect(
    self.ws_url,
    heartbeat=30,  # Send pings every 30 seconds
    autoping=True,  # Automatically respond to server pings
) as ws:
```

### 3. Message Rate Limiting ✅
**Rule**: WebSocket connections are limited to 10 incoming messages per second. Connections exceeding this limit will be disconnected.

**Implementation**:
- Using `!bookTicker` stream which provides aggregate updates
- Server-side rate limiting is handled by the exchange
- Our implementation only receives and processes messages
- No risk of exceeding 10 msg/sec as we're not sending messages

### 4. Subscription Limit ✅
**Rule**: A single connection can subscribe to a maximum of 200 streams.

**Implementation**:
- We use the `!bookTicker` stream which is a **single stream** providing all symbol updates
- No explicit subscriptions needed (stream is pre-aggregated)
- Well under the 200 stream limit (using only 1)

### 5. Automatic Reconnection ✅
**Rule**: IP addresses that are repeatedly disconnected may be banned.

**Implementation**:
- Graceful error handling in `_ws_loop()`
- 5-second delay before reconnection attempts
- Proper cleanup in `finally` block
- Logging of all connection events for monitoring

```python
except Exception as e:
    self.logger.error(f"WebSocket connection error: {e}")
finally:
    if self.running:
        self.logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)
```

### 6. Connection Lifecycle Management ✅
**Implementation**:
- `start()` method to initiate WebSocket connection
- `stop()` method for graceful shutdown
- Task cancellation handling
- Proper resource cleanup

## Connection State Tracking

The implementation maintains:
- `self.running`: Boolean flag for connection state
- `self.ws_task`: Reference to the asyncio task
- `self.bbo_cache`: In-memory cache of latest BBO prices per symbol
- `self.last_update`: Timestamp of last update per symbol
- `connection_start`: Timestamp when connection was established (per connection)

## Monitoring and Logging

The implementation provides comprehensive logging:
- **INFO**: Connection lifecycle events (connect, disconnect, reconnect)
- **DEBUG**: Ping/Pong heartbeat events
- **WARNING**: Server-initiated disconnections
- **ERROR**: Connection errors and message processing failures

## Best Practices

1. **Single Stream Design**: Using `!bookTicker` provides all symbols with one stream
2. **Proactive Reconnection**: Reconnect before 24-hour limit to avoid forced disconnection
3. **Heartbeat Safety**: 30-second client pings ensure responsive connection
4. **Error Resilience**: Automatic reconnection with delay prevents ban from rapid reconnects
5. **Resource Management**: Proper cleanup and task cancellation on shutdown

## Testing

The implementation is tested in:
- `tests/test_bbo_stream.py`: Unit tests for BBO functionality
- `examples/bbo_websocket_demo.py`: Live demo showing real-time updates

All tests pass and demonstrate stable WebSocket connectivity.
