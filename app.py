from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import asyncio
from dbinterface import DBInterface

app = FastAPI()

# Keep track of connected WebSocket clients
clients = []
db = DBInterface()

# Fetch data from the database
async def get_data():
    try:
        await db.init_pool()
        sql = "SELECT id, status_bc FROM user_kaleidoskop_new"
        query = await db.queries(sql)
        return query
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        await db.close_pool()

# Broadcast data to all connected clients
async def broadcast_to_clients(data):
    for client in clients:
        try:
            await client.send_json(data)
        except Exception as e:
            print(f"Failed to send data to client: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            # Fetch real-time data from the database
            data = await get_data()
            if data:
                # Prepare data to send
                for record in data:
                    message = {
                        "user_id": record['id'],
                        "status": record['status_bc']
                    }
                    await websocket.send_json(message)
            await asyncio.sleep(1)  # Adjust the interval as needed
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Remove disconnected client
        clients.remove(websocket)

@app.get("/")
async def get():
    return HTMLResponse("""
        <html>
            <head>
                <title>WebSocket Test</title>
            </head>
            <body>
                <h1>WebSocket server running.</h1>
                <script>
                    const socket = new WebSocket('ws://localhost:8000/ws');
                    socket.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        console.log("Received:", data);
                    };
                    socket.onclose = () => {
                        console.log("WebSocket closed");
                    };
                </script>
            </body>
        </html>
    """)
