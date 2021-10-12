# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *


class ClockDiv3(Module):
    def __init__(self):
        neg = ClockDomain('neg')
        self.clock_domains += [neg]
        self.comb += [
            neg.clk.eq(~ClockSignal()),
            neg.rst.eq(ResetSignal(allow_reset_less=True)),
        ]

        pos_cnt = Signal(2)
        neg_cnt = Signal(2)
        self.out = Signal()

        self.sync.sys += If(pos_cnt == 2,
            pos_cnt.eq(0),
        ).Else(
            pos_cnt.eq(pos_cnt + 1),
        )

        self.sync.neg += If(neg_cnt == 2,
            neg_cnt.eq(0),
        ).Else(
            neg_cnt.eq(neg_cnt + 1),
        )

        self.comb += [
            self.out.eq((pos_cnt == 2) | (neg_cnt == 2))
        ]
