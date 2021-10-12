# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from litex.soc.interconnect import stream, csr
from migen import *


class BatchLimiter(Module, csr.AutoCSR):
    def __init__(self, layout, max=256, allow=1, sleep=1, with_csr=False):
        self.sink = stream.Endpoint(layout)
        self.source = stream.Endpoint(layout)
        self.allow = Signal(max=max, reset=allow)
        self.sleep = Signal(max=max, reset=sleep)

        counter = Signal(max=max, reset=1)
        sleeping = Signal()

        self.comb += [
            If(~sleeping,
                self.sink.connect(self.source),
            ),
        ]

        self.sync += If(sleeping,
            If(counter == self.sleep,
                counter.eq(1),
                sleeping.eq(0),
            ).Else(
                counter.eq(counter+1),
            )
        ).Elif(self.source.valid & self.source.ready,
            If(counter == self.allow,
                counter.eq(1),
                sleeping.eq(1),
            ).Else(
                counter.eq(counter+1),
            )
        )

        if with_csr:
            self.add_csrs()

    def add_csrs(self):
        self._allow = csr.CSRStorage(self.allow.nbits, self.allow.reset.value)
        self._sleep = csr.CSRStorage(self.sleep.nbits, self.sleep.reset.value)
        self.comb += [
            self.allow.eq(self._allow.storage),
            self.sleep.eq(self._sleep.storage),
        ]
