# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from litex.soc.interconnect import csr, stream
from migen import *


class CSRMixin(csr.AutoCSR):
    def add_storage_csrs(self, *names):
        for name in names:
            signal = getattr(self, name)
            storage = csr.CSRStorage(signal.nbits, signal.reset.value, name=name)
            setattr(self, '_' + name, storage)
            self.comb += signal.eq(storage.storage)
