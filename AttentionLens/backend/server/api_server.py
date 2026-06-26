import asyncio
import json
import websockets
import threading

class ApiServer:
    def __init__(self, host="localhost", port=8421):
        self.host = host
        self.port = port
        self.clients = set()
        self.latest_state = {
            "attention_score": 0.0,
            "calculated_state": "Deep Work",
            "active_process": "code.exe",
            "active_title": "activity_repository.py - AttentionLens",
            "active_category": "Core_Tool",
            "ml_model_status": "Idle",
            "session_count": 0,
            "recent_sessions": [],
            "current_alert": None,
            "tracker_status": {
                "mode": "live",
                "window_ok": False,
                "input_ok": False,
                "last_flush_at": None,
                "flush_count": 0,
                "events_written": 0,
                "retry_queue_size": 0,
                "last_error": None,
            },
        }
        self.loop = None
        self.server = None
        self.thread = None

    def update_state(self, key, value):
        """Thread-safe update of server state."""
        self.latest_state[key] = value
        self.broadcast_message({"type": "state_update", "data": self.latest_state})

    def trigger_alert(self, alert_json):
        """Thread-safe trigger of focus alerts."""
        self.latest_state["current_alert"] = alert_json
        self.broadcast_message({"type": "attention_alert", "data": alert_json})

    def broadcast_message(self, message_dict):
        """Broadcasts a JSON payload to all connected clients."""
        if not self.loop:
            return
            
        payload = json.dumps(message_dict)
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    async def _broadcast(self, payload):
        if self.clients:
            await asyncio.gather(*[client.send(payload) for client in self.clients])

    async def handler(self, websocket):
        # Register client
        self.clients.add(websocket)
        print(f"Client connected: {websocket.remote_address}. Total: {len(self.clients)}")
        
        # Send initial state
        await websocket.send(json.dumps({
            "type": "state_update",
            "data": self.latest_state
        }))
        
        try:
            async for message in websocket:
                # Handle potential messages from frontend
                try:
                    data = json.loads(message)
                    action = data.get("action")
                    if action == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                except Exception as e:
                    print(f"Error parsing frontend message: {e}")
        except websockets.exceptions.ConnectionClosedOK:
            pass
        finally:
            self.clients.remove(websocket)
            print(f"Client disconnected. Total: {len(self.clients)}")

    def start(self):
        """Starts the server in a separate background thread."""
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _run_server(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        async def start_websocket():
            self.server = await websockets.serve(self.handler, self.host, self.port)
            print(f"WebSocket server listening on ws://{self.host}:{self.port}")

        self.loop.run_until_complete(start_websocket())
        self.loop.run_forever()

    def stop(self):
        if self.loop and self.server:
            self.loop.call_soon_threadsafe(self.server.close)
            self.loop.call_soon_threadsafe(self.loop.stop)
            print("WebSocket server stopped.")
