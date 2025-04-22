# Author: Adapted from Peter Hinch's MicroPython example
# License: AGPL 3.0 (initial project), MIT for original demo

import asyncio
import json


class Server:

    def __init__(self, controller_status, host='0.0.0.0', port=8123, backlog=5, timeout=20):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.timeout = timeout
        self.controller_status = controller_status
        self.cid = 0
        self.server = None

    async def run(self):
        print('Awaiting client connection.')
        self.server = await asyncio.start_server(self.run_client, self.host, self.port, backlog=self.backlog)
        async with self.server:
            await self.server.serve_forever()

    async def run_client(self, reader, writer):
        self.cid += 1
        addr = writer.get_extra_info('peername')
        print(f'Client {self.cid} connected from {addr}')

        try:
            while True:
                try:
                    res = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                except asyncio.TimeoutError:
                    print(f"Client {self.cid} timeout")
                    break

                if not res:
                    break  # connection closed

                decoded = res.decode('utf-8').strip()
                print(f'Received from client {self.cid}: {decoded}')

                if "toto" in decoded:
                    response = self.send_json_data()
                    writer.write((json.dumps(response) + "\n").encode('utf-8'))
                    await writer.drain()
                else:
                    # echo back
                    writer.write((decoded + "\n").encode('utf-8'))
                    await writer.drain()

        except Exception as e:
            print(f"Error with client {self.cid}: {e}")

        print(f'Client {self.cid} disconnected.')
        writer.close()
        await writer.wait_closed()
        print(f'Client {self.cid} socket closed.')

    def send_json_data(self):
        return {
            "start_time": self.controller_status.get_dailytimer_current_start_time()
        }

    async def close(self):
        print('Closing server')
        self.server.close()
        await self.server.wait_closed()
        print('Server closed')
