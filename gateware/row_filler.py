# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

'''
Fills the row memories from a DMA source.
'''
from migen import *
from litex.soc.interconnect import csr, stream

from csr_mixin import CSRMixin
from batch_limiter import BatchLimiter
from utils import FastLatch


class StreamCounter(Module):
    def __init__(self, layout):
        name, nbits = layout[0]
        self.source = stream.Endpoint(layout)

        # Interface
        self.submodules._begin = FastLatch()
        self.start = Signal(nbits)
        self.count = Signal(32)
        self.busy = Signal()

        # State
        state = Signal()
        counter = Signal(32)

        self.comb += [
            self.busy.eq(self._begin.out),
            self.source.valid.eq(state),
        ]

        attr = getattr(self.source, name)

        self.sync += If(~state,
            If(self._begin.out,
                attr.eq(self.start),
                counter.eq(0),
                state.eq(1),
            ),
        ).Elif(self.source.ready,
            attr.eq(attr+1),
            If(counter == (self.count-1),
                self._begin.reset.send(),
                state.eq(0),
            ).Else(
                counter.eq(counter+1),
            ),
        )

    def begin(self):
        return self._begin.set.send()


class Demultiplexer(Module):
    def __init__(self, layout, sources):
        self.sink = stream.Endpoint(layout)
        self.sel = Signal(max=max(len(sources), 2))

        self.comb += Case(self.sel, {
            i: self.sink.connect(source)
            for i, source in enumerate(sources)
        })


class RowFiller(Module, csr.AutoCSR):
    def __init__(self, dma, sinks, depth=48):
        # Interface
        self.submodules.begin = FastLatch()
        self.busy = Signal()
        self.base_addr = Signal(32)
        self.row = Signal(5)
        self.bank = Signal()

        # State
        count = len(sinks)
        self.state = Signal(max=(2*count)+1)
        self.addr = Signal(max=depth*2)

        if depth == 64:
            scale = lambda s: (s<<6)
        elif depth == 48:
            scale = lambda s: (s<<5) + (s<<4)
        else:
            raise ValueError()

        # Stream reading
        layout = [('address', dma.sink.address.nbits)]
        self.dma = dma
        self.submodules.addr_counter = StreamCounter(layout)
        self.submodules.delay = BatchLimiter(layout, 257, 12, 12, True)

        # Stream writing
        self.sinks = sinks
        self.submodules.dem = Demultiplexer(
            [
                ('address', 32),
                ('data', 32),
            ],
            sinks,
        )

        self.comb += [
            self.busy.eq(self.begin.out | (self.state != 0)),

            self.addr_counter.source.connect(self.delay.sink),
            self.delay.source.connect(self.dma.sink),
            self.dma.source.connect(self.dem.sink, omit=['address']),
            self.dem.sink.address.eq(
                self.addr + scale(self.bank<<1)
            ),
        ]

        # State
        memcpys = []
        for idx in range(count):
            panel = idx >> 1
            line = idx & 1
            offset_0 = scale((panel*4 + line) << 5)
            offset_1 = scale((panel*4 + line + 2) << 5)
            memcpys.append((
                idx,
                scale(self.row) + offset_0 + self.base_addr,
            ))
            memcpys.append((
                idx,
                scale(self.row) + offset_1 + self.base_addr,
            ))

        cases = {}
        tf_busy = self.addr_counter.busy | (self.dma.rsv_level != 0)

        for idx, (d, s) in enumerate(memcpys):
            if idx == 0:
                test = self.begin.out
            else:
                test = ~tf_busy

            next = [
                self.addr_counter.begin(),
                self.addr_counter.start.eq(s),
                self.addr_counter.count.eq(depth),
                self.dem.sel.eq(d),
                self.state.eq(idx+1),
            ]

            cases[idx] = If(test, *next)

        cases[len(memcpys)] = If(~tf_busy,
            self.begin.reset.send(),
            self.state.eq(0),
        )

        self.sync += Case(self.state, cases)

        self.sync += If(self.dem.sink.valid & self.dem.sink.ready,
            If(self.addr == 2*depth - 1,
                self.addr.eq(0),
            ).Else(
                self.addr.eq(self.addr+1),
            )
        )
