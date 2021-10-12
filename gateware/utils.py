# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *


class Pulse(Module):
    def __init__(self):
        self.inp = Signal()
        self.out = Signal()
        self.last = Signal()

        self.comb += self.out.eq(self.inp != self.last)
        self.sync += self.last.eq(self.inp)

    def send(self):
        return self.inp.eq(~self.inp)


class FastLatch(Module):
    def __init__(self):
        self.submodules.set = Pulse()
        self.submodules.reset = Pulse()
        self.out = Signal()
        self.back = Signal()

        self.comb += If(self.reset.out,
            self.out.eq(0),
        ).Elif(self.set.out,
            self.out.eq(1),
        ).Else(
            self.out.eq(self.back),
        )

        self.sync += self.back.eq(self.out)
