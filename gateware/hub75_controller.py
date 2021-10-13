# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *

from litex.soc.interconnect import csr

from csr_mixin import CSRMixin


class Hub75Controller(Module, CSRMixin):
    def __init__(self, driver, row_filler, base=0, with_csr=False):
        self.submodules.driver = driver
        self.submodules.row_filler = row_filler

        self.base_addr = Signal(32, reset=base)

        filler_state = Signal()
        row = Signal(5)
        bank = Signal(1)
        self.enable = Signal()
        cycle_counter = Signal(32)
        self.cycle_length = Signal(32, reset=5100)

        self.buffers_written = Signal(2)
        self.buffers_read = Signal(2)
        self.buffers_av = Signal(2)
        max_buffers = 2 if driver.dbl_buf else 1

        self.comb += [
            self.row_filler.base_addr.eq(self.base_addr),
            self.row_filler.row.eq(row),
            self.driver.bank.eq(bank),
            self.buffers_av.eq(self.buffers_written - self.buffers_read),
        ]

        # Filler
        self.sync += If(filler_state == 0,
            If(self.enable & (self.buffers_av < max_buffers),
                self.row_filler.begin.set.send(),
                filler_state.eq(1),
            ).Elif(~self.enable,
                self.buffers_written.eq(0),
                self.row_filler.bank.eq(0),
                row.eq(driver.addr),#+1),
            ),
        ).Elif(~self.row_filler.busy,
            self.buffers_written.eq(self.buffers_written+1),
            self.row_filler.bank.eq(~self.row_filler.bank),
            row.eq(row+1),
            filler_state.eq(0),
        )

        # Sender
        sender_state = Signal(2)

        self.sync += If(sender_state == 0,
            If(self.enable,
                If(self.buffers_av > 0,
                    driver.begin.set.send(),
                    sender_state.eq(1),
                    cycle_counter.eq(0),
                )
            ).Else(
                self.buffers_read.eq(0),
                bank.eq(0),
            ),
        ).Elif(sender_state == 1,
            cycle_counter.eq(cycle_counter+1),
            If(~driver.begin.out,
                sender_state.eq(2),
                self.buffers_read.eq(self.buffers_read+1),
                bank.eq(~bank),
            ),
        ).Else(
            cycle_counter.eq(cycle_counter+1),
            If(cycle_counter >= self.cycle_length,
                sender_state.eq(0),
            ),
        )

        if with_csr:
            self.add_csrs()

    def add_csrs(self):
        self._enable = csr.CSRStorage()
        self.comb += [
            self.enable.eq(self._enable.storage),
        ]
        self.add_storage_csrs('cycle_length', 'base_addr')

    def get_csrs(self):
        csrs = super().get_csrs()
        for csr in csrs:
            csr.name = csr.name.replace('driver_driver_data_driver_', '')
            csr.name = csr.name.replace('driver_driver_enable_driver_', '')
        return csrs
