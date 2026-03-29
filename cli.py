import sys
import argparse
from core.ipc import IPCClient

def main():
    parser = argparse.ArgumentParser(description="VoxQuill CLI Client")
    parser.add_argument("--command", type=str, required=True, help="Command to send (toggle, show, hide)")
    args = parser.parse_args()

    client = IPCClient()
    if client.send_command(args.command):
        print(f"Sent command: {args.command}")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
