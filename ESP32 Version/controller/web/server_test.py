# userver.py Demo of simple uasyncio-based echo server

# Released under the MIT licence
# Copyright (c) Peter Hinch 2019-2020

import usocket as socket
import uasyncio as asyncio
import uselect as select
import ujson


class Server:

    def __init__(self, controller_status, host='0.0.0.0', port=8123, backlog=5, timeout=20):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.timeout = timeout
        self.controller_status = controller_status

    async def run(self):
        print('Awaiting client connection.')
        self.cid = 0
        self.server = await asyncio.start_server(self.run_client, self.host, self.port, self.backlog)
        while True:
            await asyncio.sleep(100)

    async def run_client(self, sreader, swriter):
        self.cid += 1
        print('Got connection from client', self.cid)
        try:
            while True:
                try:
                    res = await asyncio.wait_for(sreader.readline(), self.timeout)
                except asyncio.TimeoutError:
                    res = b''
                if res == b'':
                    raise OSError

                if res.decode('ascii').find("toto") != -1:
                    swriter.write(ujson.dumps(self.sendJsonData()))
                    await swriter.drain()

                print('Received {} from client {}'.format(res.rstrip().decode('ascii'), self.cid))
                await swriter.drain()  # Echo back
        except OSError:
            pass
        print('Client {} disconnect.'.format(self.cid))
        await sreader.wait_closed()
        print('Client {} socket closed.'.format(self.cid))

    def close(self):
        print('Closing server')
        self.server.close()
        await self.server.wait_closed()
        print('Server closed')

    def sendJsonData(self):
        data = "\"start_time\":{start_time}".format(start_time=self.controller_status.get_dailytimer_current_start_time())
        json = "{" + data + "}"
        return json

