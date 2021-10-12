# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *
from litex.soc.interconnect import csr, stream


class MemStreamReader(Module):
    def __init__(self, rport):
        self.sink = sink = stream.Endpoint([
            ('address', rport.adr.nbits),
        ])
        self.source = source = stream.Endpoint([
            ('data', rport.dat_r.nbits),
        ])

        hold = Signal()
        hold_data = Signal(rport.dat_r.nbits)
        blocking = source.valid & ~source.ready

        self.comb += [
            sink.ready.eq(
                sink.valid & ~blocking
            ),
            rport.adr.eq(sink.address),
            If(hold,
                source.data.eq(hold_data),
            ).Else(
                source.data.eq(rport.dat_r),
            ),
        ]

        self.sync += [
            If(sink.valid | blocking,
                source.valid.eq(1),
            ).Else(
                source.valid.eq(0),
            ),
            If(blocking,
                hold.eq(1),
                hold_data.eq(source.data),
            ).Else(
                hold.eq(0),
            ),
        ]


class MemStreamWriter(Module):
    def __init__(self, wrport):
        self.sink = sink = stream.Endpoint([
            ('address', wrport.adr.nbits),
            ('data', wrport.dat_w.nbits),
        ])

        self.comb += [
            sink.ready.eq(sink.valid),
            wrport.we.eq(sink.valid),
            wrport.adr.eq(sink.address),
            wrport.dat_w.eq(sink.data),
        ]
