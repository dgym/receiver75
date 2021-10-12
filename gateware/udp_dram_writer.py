# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *

from liteeth.common import convert_ip, stream, eth_udp_user_description
from litedram.frontend.dma import LiteDRAMDMAWriter
from litex.gen.common import reverse_bytes
from litex.soc.interconnect import csr

from batch_limiter import BatchLimiter


class UdpDramWriter(Module, csr.AutoCSR):
    def __init__(self, sdram, udp, port_num):
        udp_port = udp.crossbar.get_port(port_num, dw=32)

        self.sink = sink = stream.Endpoint(eth_udp_user_description(32))
        renamer = ClockDomainsRenamer({'write': 'eth_rx', 'read': 'eth_rx', 'sys': 'eth_rx'})
        fifo_layout = [("data", 32), ("end", 1)]
        self.submodules.fifo = fifo = renamer(stream.AsyncFIFO(fifo_layout, 256*4))
        self.submodules.udp_delay = renamer(BatchLimiter(fifo_layout, 257, 256, 128, True))

        self.comb += udp_port.source.connect(sink)

        valid = Signal()
        self.comb += [
            valid.eq(sink.dst_port == port_num),
            fifo.sink.valid.eq(sink.valid & valid),
            fifo.sink.data.eq(sink.data),
            fifo.sink.end.eq(sink.last),
            sink.ready.eq(fifo.sink.ready),
            fifo.source.connect(self.udp_delay.sink),
        ]

        sdram_port = sdram.crossbar.get_port(mode='write', data_width=32, clock_domain='eth_rx')
        self.submodules.dma = renamer(LiteDRAMDMAWriter(sdram_port, fifo_depth=1, fifo_buffered=False))
        self.set_up_dma(self.udp_delay, self.dma)

    def set_up_dma(self, fifo, dma):
        stream = Signal()
        address = Signal(18)

        self.comb += [
            dma.sink.valid.eq(stream & fifo.source.valid),
            dma.sink.data.eq(reverse_bytes(fifo.source.data)),
            dma.sink.address.eq(address),
            fifo.source.ready.eq((~stream) | dma.sink.ready),
        ]

        self.sync.eth_rx += If(fifo.source.valid,
            If(~stream,
                address.eq(fifo.source.data[:18]),
                stream.eq(1),
            ).Elif(fifo.source.valid & dma.sink.ready,
                address.eq(address + 1),
                If(fifo.source.end,
                    stream.eq(0),
                ),
            ),
        )
