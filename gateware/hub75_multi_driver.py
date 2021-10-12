from migen import *

from litex.soc.interconnect import csr

from bram import BRAM
from hub75_driver import HUB75DataDriver, HUB75EnableDriver, Hub75Driver
from utils import FastLatch


class Hub75MultiDriver(Module, csr.AutoCSR):
    def __init__(self, addrs, clk, lat, oen, ports, cd_read='sys', dbl_buf=False, with_csr=False):
        self.ports = ports
        self.dbl_buf = dbl_buf

        self.submodules.begin = FastLatch()
        self.addr = addrs

        self.submodules.mems = [
            BRAM(32, 128 * (2 if dbl_buf else 1), cd_read='read')
            for _ in range(2*len(ports))
        ]
        renamer = ClockDomainsRenamer({'read': cd_read})
        data_driver = HUB75DataDriver(
            ports,
            [mem.read for mem in self.mems],
            with_csr=with_csr,
            cd_read=cd_read,
        )
        enable_driver = HUB75EnableDriver(
            with_csr=with_csr,
        )
        self.submodules.driver = Hub75Driver(data_driver, enable_driver)

        self.bank = Signal(1)
        if dbl_buf:
            self.comb += If(self.bank,
                data_driver.multi_row_reader.addr.eq(128 * 24 // 32),
            ).Else(
                data_driver.multi_row_reader.addr.eq(0),
            )

        state = Signal()

        self.comb += [
            addrs.eq(enable_driver.addr),
            clk.eq(data_driver.clk),
            lat.eq(data_driver.lat),
            oen.eq(enable_driver.oen),
        ]

        self.sync += If(state == 0,
            If(self.begin.out,
                self.driver.next_addr.eq(addrs+1),
                self.driver.start(),
                state.eq(1),
            ),
        ).Else(
            If(~self.driver.busy,
                state.eq(0),
                self.begin.reset.send(),
            ),
        )


