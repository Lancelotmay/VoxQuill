# Track 2: IPC & Messaging

## Goal
Implement a Unix Domain Socket-based IPC mechanism to allow a CLI client (triggered by a global hotkey) to communicate with the main PyQt6 application.

## Tasks
1. [ ] **IPC Server (`core/ipc_server.py`)**
   - Implement `IPCServer` class using `socket.socket(socket.AF_UNIX)`.
   - Listen on `$XDG_RUNTIME_DIR/aiinputbox.socket`.
   - Define a simple JSON-based protocol:
     - `{"command": "toggle"}`
     - `{"command": "show"}`
     - `{"command": "hide"}`
2. [ ] **IPC Client (`cli.py`)**
   - Implement a lightweight CLI script to send commands to the socket.
   - Example usage: `python cli.py --command toggle`.
3. [ ] **App Integration**
   - Connect the IPC server to the PyQt6 main window (to be implemented in Track 3).

## Implementation Details
- **Socket Path**: Defaults to `/run/user/<uid>/aiinputbox.socket`.
- **Threading**: The server should run in its own thread to avoid blocking the UI.

## Success Criteria
- [ ] Running `cli.py` sends a message successfully to the background server.
- [ ] Server correctly parses commands and prints them to the console.
