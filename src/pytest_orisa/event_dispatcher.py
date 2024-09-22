import asyncio
import json
import socket
import threading
from typing import Callable

from pytest_orisa.domain import Event


class EventDispatcher:
    def __init__(self, host="localhost", port=1337) -> None:
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.shutdown_flag = threading.Event()
        self.client_threads = []
        self.event_handlers = {}
        self.event_data = {}
        self.lock = threading.Lock()
        print(f"Server started on {self.host}:{self.port}")

    def register_handler(self, event_type: str, handler: Callable) -> None:
        print(f"Registered handler for event type: {event_type}")
        with self.lock:
            self.event_handlers[event_type] = handler

    def handle_client(self, client_socket):
        buffer = ""
        while not self.shutdown_flag.is_set():
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8")

                while True:
                    try:
                        # Try to decode the buffer as JSON
                        event = json.loads(buffer)
                        event_type: str = event.get("type")
                        data = event.get("data")

                        with self.lock:
                            handler = self.event_handlers.get(event_type)

                        if handler:
                            handler(data)

                        # Store the data if no handler is specified
                        if event_type not in self.event_handlers:
                            self.event_data[event_type] = data

                        # Clear the buffer after processing
                        buffer = ""
                        break
                    except json.JSONDecodeError:
                        # If JSON is incomplete, break and wait for more data
                        break
            except ConnectionResetError:
                break

        client_socket.close()

    def start(self) -> None:
        while not self.shutdown_flag.is_set():
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Connection from {addr}")
                client_thread = threading.Thread(
                    target=self.handle_client, args=(client_socket,)
                )
                self.client_threads.append(client_thread)
                client_thread.start()
            except socket.timeout:
                continue

    def stop(self) -> None:
        self.shutdown_flag.set()
        self.server_socket.close()
        for thread in self.client_threads:
            thread.join()
        print("Server stopped")

    def get_event_data(self, event_type: str):
        with self.lock:
            return self.event_data.get(event_type, None)


def send_event(event: Event) -> None:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(("localhost", 1337))
    client_socket.sendall(event.deserialize().encode("utf-8"))
    client_socket.close()


async def wait_for_server(host, port, max_retries=5, retry_delay=0.1) -> None:
    for attempt in range(max_retries):
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except (OSError, asyncio.TimeoutError):
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise Exception("Server is not available after multiple retries")
