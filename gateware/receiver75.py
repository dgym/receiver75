#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

import os
import argparse

from migen import *

from litex_boards.platforms import colorlight_5a_75b, colorlight_5a_75e
from litex_boards.targets import colorlight_5a_75x
from litex.build.generic_platform import Pins

from litex.build.lattice.trellis import trellis_args, trellis_argdict
from litex.soc.cores.spi_flash import ECP5SPIFlash
from litex.soc.integration.soc_core import (
    SoCCore, soc_core_args, soc_core_argdict,
)
from litex.soc.integration.builder import (
    Builder, builder_args, builder_argdict,
)
from litex.soc.interconnect import csr
from litex.soc.interconnect.csr import AutoCSR

from litedram.modules import M12L64322A
from litedram.phy import GENSDRPHY, HalfRateGENSDRPHY
from litedram.frontend.dma import LiteDRAMDMAReader

from liteeth.common import convert_ip
from liteeth.core import LiteEthUDPIPCore
from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from liteeth.phy.model import LiteEthPHYModel

from clockdiv3 import ClockDiv3
from hub75_multi_driver import Hub75MultiDriver
from hub75_controller import Hub75Controller
from row_filler import RowFiller
from mem_stream import MemStreamWriter
from udp_dram_writer import UdpDramWriter


class _CRG(colorlight_5a_75x._CRG):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add a sys/3 clock.
        self.submodules.cd3 = ClockDiv3()
        self.clock_domains.cd_sys_div3 = ClockDomain(reset_less=True)
        self.comb += [
            self.cd_sys_div3.clk.eq(self.cd3.out),
        ]


class Receiver75(SoCCore):
    def __init__(self, board, revision, sys_clk_freq=60e6, with_ethernet=False,
            with_etherbone=True, eth_ip="192.168.0.39", eth_phy=0,
            use_internal_osc=True, sdram_rate="1:1", **kwargs):
        if board == "5a-75b":
            platform = colorlight_5a_75b.Platform(revision=revision)
        elif board == "5a-75e":
            platform = colorlight_5a_75e.Platform(revision=revision)

        # SoCCore with integrated RAM
        SoCCore.__init__(self, platform, int(sys_clk_freq),
            ident = "Receiver75 on Colorlight " + board,
            ident_version = True,
            integrated_main_ram_size=0x1000,
            **kwargs)

        # CRG
        self.submodules.crg = _CRG(
            platform, sys_clk_freq,
            use_internal_osc=use_internal_osc,
            with_usb_pll=False,
            with_rst=False,
            sdram_rate=sdram_rate,
        )

        # SDRAM - not used directly by the CPU
        sdrphy_cls = HalfRateGENSDRPHY if sdram_rate == "1:2" else GENSDRPHY
        self.submodules.sdrphy = sdrphy_cls(platform.request("sdram"), sys_clk_freq)
        sdram_cls  = M12L64322A
        self.add_sdram("sdram",
            phy           = self.sdrphy,
            module        = sdram_cls(sys_clk_freq, sdram_rate),
            l2_cache_size = kwargs.get("l2_size", 1024),
            with_soc_interconnect=False,
        )

        # CSR
        class CSRS(Module, AutoCSR):
            pass
        self.submodules.hub75_soc = CSRS()
        self.hub75_soc.mac_address = csr.CSRStorage(6*8, 0x10e2d5000000, name='mac_address')
        self.hub75_soc.ip_address = csr.CSRStorage(4*8, convert_ip(eth_ip))

        # Etherbone
        if with_ethernet or with_etherbone:
            self.submodules.ethphy = LiteEthPHYRGMII(
                clock_pads = self.platform.request("eth_clocks", eth_phy),
                pads       = self.platform.request("eth", eth_phy),
                tx_delay   = 0e-9)
            if with_ethernet:
                self.add_ethernet(phy=self.ethphy)

            if with_etherbone:
                self.add_etherbone(phy=self.ethphy,
                    mac_address=self.hub75_soc.mac_address.storage,
                    ip_address=self.hub75_soc.ip_address.storage)
            else:
                self.add_udp(phy=self.ethphy,
                    mac_address=self.hub75_soc.mac_address.storage,
                    ip_address=self.hub75_soc.ip_address.storage)

        # Hub75
        conns = platform.constraint_manager.connector_manager.connector_table
        _, _, _, _, _, _, _, a4, a0, a1, a2, a3, clk, lat, oen, _ = conns['j1']
        j1r0, j1g0, j1b0, _, _, _, _, _ = conns['j1'][:8]
        def get_rgbs(conn):
            pins = conns[conn]
            return Pins(*(pins[:3] + pins[4:7]))
        platform.add_extension([
            ('hub75_addr', 0, Pins(a0, a1, a2, a3, a4)),
            ('hub75_clk', 0, Pins(clk)),
            ('hub75_lat', 0, Pins(lat)),
            ('hub75_oen', 0, Pins(oen)),
        ] + [
            (f'hub75_j{i}', 0, get_rgbs(f'j{i}')) for i in range(1, 9)
        ])

        hub75_driver = Hub75MultiDriver(
            platform.request('hub75_addr'),
            platform.request('hub75_clk'),
            platform.request('hub75_lat'),
            platform.request('hub75_oen'),
            [
                platform.request('hub75_j1'),
                platform.request('hub75_j2'),
                platform.request('hub75_j3'),
                platform.request('hub75_j4'),
                platform.request('hub75_j5'),
                platform.request('hub75_j6'),
                platform.request('hub75_j7'),
                platform.request('hub75_j8'),
            ],
            cd_read='sys_div3',
            with_csr=True,
            dbl_buf=True,
        )

        port = self.sdram.crossbar.get_port(data_width=32)
        self.submodules.dma_reader = LiteDRAMDMAReader(port, 8)

        self.submodules.writers = [
            MemStreamWriter(mem.write)
            for mem in hub75_driver.mems
        ]

        row_filler = RowFiller(
            self.dma_reader,
            [w.sink for w in self.writers],
        )

        c = self.submodules.hub75_controller = Hub75Controller(
            hub75_driver, row_filler,
            with_csr=True,
        )

        # UDP -> memory
        if with_ethernet or with_etherbone:
            self.submodules.mem_streamer = UdpDramWriter(
                self.sdram, self.ethcore.udp, 4343,
            )

        # SPI flash for config
        self.submodules.spiflash = ECP5SPIFlash(
            pads         = platform.request("spiflash"),
            sys_clk_freq = sys_clk_freq,
            spi_clk_freq = 5e6,
        )
        self.add_csr("spiflash")

    def add_udp(self, name="etherbone", phy=None, phy_cd="eth",
        mac_address=0x10e2d5000000,
        ip_address="192.168.0.39"):

        self.check_if_exists(name)
        ethcore = LiteEthUDPIPCore(
            phy         = phy,
            mac_address = mac_address,
            ip_address  = ip_address,
            clk_freq    = self.clk_freq,
            with_icmp=False)

        ethcore = ClockDomainsRenamer({
            "eth_tx": phy_cd + "_tx",
            "eth_rx": phy_cd + "_rx",
            "sys":    phy_cd + "_rx"})(ethcore)
        self.submodules.ethcore = ethcore

        eth_rx_clk = getattr(phy, "crg", phy).cd_eth_rx.clk
        eth_tx_clk = getattr(phy, "crg", phy).cd_eth_tx.clk
        if not isinstance(phy, LiteEthPHYModel):
            self.platform.add_period_constraint(eth_rx_clk, 1e9/phy.rx_clk_freq)
            self.platform.add_period_constraint(eth_tx_clk, 1e9/phy.tx_clk_freq)
            self.platform.add_false_path_constraints(self.crg.cd_sys.clk, eth_rx_clk, eth_tx_clk)


class BiosBuilder(Builder):
    def add_software_package(self, name, src_dir=None):
        if name == 'bios':
            src_dir = os.path.join(os.getcwd(), '../bios')
        super().add_software_package(name, src_dir)


def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Colorlight 5A-75X")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build bitstream",
    )
    parser.add_argument(
        "--board",
        default="5a-75b",
        help="Board type: 5a-75b (default) or 5a-75e",
    )
    parser.add_argument(
        "--revision",
        default="8.0",
        help="Board revision",
    )
    parser.add_argument(
        "--sys-clk-freq",
        default=64e6,
        help="System clock frequency (default: 64MHz)",
    )
    parser.add_argument(
        "--eth-ip",
        default="192.168.0.39",
        help="Ethernet/Etherbone IP address (overwritten by config)",
    )
    parser.add_argument(
        "--eth-phy",
        default=0,
        type=int,
        help="Ethernet PHY: 0 (default) or 1",
    )
    parser.add_argument(
        "--sdram-rate",
        default="1:1",
        help="SDRAM Rate: 1:1 Full Rate, 1:2 Half Rate",
    )
    builder_args(parser)
    soc_core_args(parser)
    trellis_args(parser)

    # Override some defaults
    parser.set_defaults(
        cpu_type='serv',
        uart_name='bridge',
    )

    args = parser.parse_args()
    args_dict = soc_core_argdict(args)

    soc = Receiver75(board=args.board, revision=args.revision,
        sys_clk_freq=int(float(args.sys_clk_freq)),
        with_ethernet=False,
        with_etherbone=True,
        eth_ip=args.eth_ip,
        eth_phy=args.eth_phy,
        use_internal_osc=True,
        sdram_rate=args.sdram_rate,
        **soc_core_argdict(args)
    )
    builder = BiosBuilder(soc, **builder_argdict(args))
    if args.build:
        builder.build(**trellis_argdict(args), run=args.build)


if __name__ == "__main__":
    main()
