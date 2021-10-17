# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *
from migen.genlib.cdc import MultiReg

from liteeth.common import convert_ip, eth_udp_user_description
from litedram.frontend.dma import LiteDRAMDMAWriter
from litex.gen.common import reverse_bytes
from litex.soc.interconnect import csr, stream

from batch_limiter import BatchLimiter
from utils import FastLatch


class Conv32to64(Module):
    def __init__(self, source, sink, reverse=False):
        partial = Signal(32)
        bit = Signal()
        rbit = Signal()
        self.submodules._reset = FastLatch()

        if reverse:
            conv = reverse_bytes
        else:
            conv = lambda x: x

        self.comb += [
            rbit.eq(bit & ~self._reset.out),
            sink.valid.eq(source.valid & rbit),
            sink.data[:32].eq(conv(partial)),
            sink.data[32:].eq(conv(source.data)),
            source.ready.eq(sink.ready | ~rbit),
        ]

        self.sync += If(source.valid,
            If(~rbit,
                partial.eq(source.data),
                bit.eq(1),
                If(self._reset.out, self._reset.reset.send()),
            ).Elif(sink.ready,
                bit.eq(0),
            ),
        )

    def reset(self):
        return self._reset.set.send()


class ProtocolHandler(Module):
    def __init__(self, source, sink):
        state = Signal(2)
        STREAM = 1
        SKIP = 2
        address = Signal(18)

        sink32 = stream.Endpoint([("data", 32), ("address", 32)])
        self.submodules.conv = Conv32to64(sink32, sink, reverse=True)
        self.comb += [
            sink.address.eq(sink32.address[1:19]),
        ]

        self.comb += [
            sink32.valid.eq((state == STREAM) & source.valid),
            sink32.data.eq(source.data),
            sink32.address.eq(address),
            source.ready.eq((state != STREAM) | sink32.ready),
        ]

        self.sync += If(source.valid,
            If(state == 0,
                address.eq(source.data[0:18]),
                state.eq(STREAM),
                self.conv.reset(),
            ).Elif(state==SKIP,
                If(source.end,
                    state.eq(0),
                ),
            ).Elif(sink32.ready,
                address.eq(address + 1),
                If(source.end,
                    state.eq(0),
                ),
            ),
        )


class UdpDramWriter(Module, csr.AutoCSR):
    def __init__(self, sdram, udp, port_num):
        # UDP port -> (eth_rx) FIFO (sys) -> UpConverter -> Limiter -> DMA writer
        udp_port = udp.crossbar.get_port(port_num, dw=32)

        # FIFO
        renamer = ClockDomainsRenamer({'write': 'eth_rx', 'read': 'sys'})
        fifo_layout = [("data", 32), ("end", 1)]
        self.submodules.fifo = fifo = renamer(stream.AsyncFIFO(fifo_layout, 512, buffered=True))
        self.connect_udp_to_fifo(udp_port.source, fifo, port_num)

        # Converter
        dma_layout = [("data", 64), ("address", 32)]
        converter = stream.Endpoint(dma_layout)
        self.submodules.handler = ProtocolHandler(fifo.source, converter)

        # Limiter
        self.submodules.udp_delay = BatchLimiter(dma_layout, 257, 256, 1, True)
        self.connect_converter_to_limiter(converter, self.udp_delay)

        # DMA writer
        sdram_port = sdram.crossbar.get_port(mode='write', data_width=64)
        self.submodules.dma = LiteDRAMDMAWriter(sdram_port, fifo_depth=1, fifo_buffered=False)
        self.connect_limiter_to_dma(self.udp_delay.source, self.dma.sink)
        #self.connect_limiter_to_dma(converter, self.dma.sink)

    def connect_udp_to_fifo(self, udp, fifo, port_num):
        valid = Signal()
        self.comb += [
            valid.eq(udp.dst_port == port_num),
            fifo.sink.valid.eq(udp.valid & valid),
            fifo.sink.data.eq(udp.data),
            fifo.sink.end.eq(udp.last),
            udp.ready.eq(fifo.sink.ready),
        ]

    def connect_converter_to_limiter(self, converter, limiter):
        self.comb += [
            converter.connect(limiter.sink),
        ]

    def connect_limiter_to_dma(self, source, sink):
        self.comb += [
            source.connect(sink)
        ]
