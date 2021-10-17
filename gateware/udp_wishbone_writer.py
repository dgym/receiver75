# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *

from litex.soc.cores.dma import WishboneDMAWriter
from litex.soc.interconnect import wishbone, stream
from litex.gen.common import reverse_bytes
from liteeth.common import convert_ip, eth_udp_user_description


class UdpWishboneWriter(Module):
    def __init__(self, bus, udp, port_num):
        udp_port = udp.crossbar.get_port(port_num, dw=32)

        self.sink = sink = stream.Endpoint(eth_udp_user_description(32))
        renamer = ClockDomainsRenamer({'write': 'eth_rx', 'read': 'sys'})
        self.submodules.fifo = fifo = renamer(stream.AsyncFIFO([("data", 32), ("end", 1)], 64))

        self.comb += udp_port.source.connect(sink)

        valid = Signal()
        self.comb += [
            valid.eq(sink.dst_port == port_num),

            # Push data if it is valid.
            fifo.sink.valid.eq(sink.valid & valid),
            fifo.sink.data.eq(sink.data),
            fifo.sink.end.eq(sink.last),

            # Ready to accept data?
            sink.ready.eq(fifo.sink.ready),
        ]

        self.wb = wishbone.Interface(data_width=bus.data_width, adr_width=bus.address_width)
        bus.add_master('udp_wishbone_writer', self.wb)
        self.submodules.dma = WishboneDMAWriter(self.wb)
        self.set_up_dma(fifo, self.dma)

    def set_up_dma(self, fifo, dma):
        stream = Signal()
        inc = Signal()

        self.comb += [
            # Push data+addr if streaming and valid.
            dma.sink.valid.eq(stream & fifo.source.valid),
            # Data is always the fifo source data.
            dma.sink.data.eq(reverse_bytes(fifo.source.data)),
            fifo.source.ready.eq((~stream) | (fifo.source.valid & dma.sink.ready)),
            If(stream & fifo.source.valid & dma.sink.ready,
                inc.eq(1),
            ),
        ]

        self.sync += If(fifo.source.valid,
            If(~stream,
                dma.sink.address.eq(fifo.source.data),
                stream.eq(1),
            ).Elif(dma.sink.ready,
                If(fifo.source.end,
                    stream.eq(0),
                ),
            ),
        )
        self.sync += If(inc,
            dma.sink.address.eq(dma.sink.address + 1),
        )
