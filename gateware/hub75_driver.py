# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *

from csr_mixin import CSRMixin
from partial_shifter import PartialShifter
from utils import FastLatch


class MultiRowReader(Module):
    '''
    Reads RGB data from multiple row memories.
    Outputs a clk signal for the HUB75 connectors.

    Everything is done in the 'read' clock domain.
    '''

    def __init__(self, mem_reads, count=128):
        # Interface
        self.busy = Signal()
        self.addr = Signal(mem_reads[0].adr.nbits)
        self.clk = Signal()
        self.outputs = [Signal(24) for _ in mem_reads]

        # State
        self.outputting = Signal()
        self.specials.mem_reads = mem_reads
        renamer = ClockDomainsRenamer({'sys': 'read'})
        self.submodules.shifters = [
            renamer(PartialShifter(mem_read, 24))
            for mem_read in self.mem_reads
        ]

        for output, shifter in zip(self.outputs, self.shifters):
            self.comb += [
                shifter.start.eq(self.addr),
                shifter.count.eq(count),
                output.eq(shifter.output),
            ]

        self.comb += [
            self.clk.eq(self.busy & self.outputting & ~ClockSignal('read')),
            self.busy.eq(self.shifters[0].busy),
        ]

        self.sync.read += self.outputting.eq(self.busy)

    def start(self):
        return [
            shifter.begin() for shifter in self.shifters
        ]


class HUB75DataDriver(Module, CSRMixin):
    def __init__(self, ports, mem_reads,
            with_csr=False, cd_read='sys', pixel_count=128):
        self.plane = Signal(3)
        self.clk = Signal()
        self.lat = Signal()
        self.lat_wait = Signal()
        self.submodules.begin = FastLatch()
        self.busy = Signal()

        self.prelatch_cycles = Signal(8, reset=1)
        self.latch_cycles = Signal(8, reset=3)
        self.postlatch_cycles = Signal(8, reset=1)

        # Create a MultiRowReader
        renamer = ClockDomainsRenamer({'read': cd_read})
        self.submodules.multi_row_reader = renamer(MultiRowReader(
            mem_reads,
            pixel_count,
        ))

        for idx, port in enumerate(ports):
            m0 = self.multi_row_reader.shifters[idx*2]
            m1 = self.multi_row_reader.shifters[idx*2+1]
            self.comb += port[0].eq((m0.output>>self.plane)[16])
            self.comb += port[1].eq((m0.output>>self.plane)[8])
            self.comb += port[2].eq((m0.output>>self.plane)[0])
            self.comb += port[3].eq((m1.output>>self.plane)[16])
            self.comb += port[4].eq((m1.output>>self.plane)[8])
            self.comb += port[5].eq((m1.output>>self.plane)[0])

        state = Signal(2)
        counter = Signal(8)

        self.comb += [
            self.busy.eq(self.begin.out),
            self.clk.eq(self.multi_row_reader.clk),
        ]

        self.sync += Case(state, {
            0: [ # Idle
                If(self.begin.out,
                    state.eq(1),
                    counter.eq(1),
                    self.multi_row_reader.start(),
                ),
            ],
            1: [ # Send data + pre latch
                If(~self.multi_row_reader.busy,
                    If(counter >= self.prelatch_cycles,
                        If(~self.lat_wait,
                            state.eq(2),
                            counter.eq(1),
                            self.lat.eq(1),
                        ),
                    ).Else(
                        counter.eq(counter+1),
                    ),
                ),
            ],
            2: [ # Latch
                If(counter >= self.latch_cycles,
                    state.eq(3),
                    counter.eq(1),
                    self.lat.eq(0),
                ).Else(
                    counter.eq(counter+1),
                ),
            ],
            3: [ # Post latch
                self.lat.eq(0),
                If(counter >= self.postlatch_cycles,
                    state.eq(0),
                    counter.eq(0),
                    self.begin.reset.send(),
                ).Else(
                    counter.eq(counter+1),
                ),
            ],
        })

        if with_csr:
            self.add_csrs()

    def start(self):
        return self.begin.set.send()

    def add_csrs(self):
        self.add_storage_csrs(
            'prelatch_cycles',
            'latch_cycles',
            'postlatch_cycles',
        )


class HUB75EnableDriver(Module, CSRMixin):
    def __init__(self, with_csr=False):
        self.plane = Signal(3)
        self.next_addr = Signal(5)
        self.addr = Signal(5)
        self.oen = Signal(reset=1)
        self.submodules.begin = FastLatch()
        self.busy = Signal()

        self.output_cycles = Signal(16, reset=6)
        self.addr_switch_cycles = Signal(16, reset=1)

        counter = Signal(32)
        state = Signal(2)

        self.comb += [
            self.busy.eq(self.begin.out),
        ]

        self.sync += Case(state, {
            0: [ # Idle
                If(self.begin.out,
                    state.eq(1),
                    counter.eq(1),
                    self.oen.eq(0),
                ),
            ],
            1: [ # OEN
                If((counter >> self.plane) >= self.output_cycles,
                    If(self.next_addr != self.addr,
                        state.eq(2),
                        counter.eq(1),
                    ).Else(
                        state.eq(0),
                        self.begin.reset.send(),
                    ),
                    self.oen.eq(1),
                ).Else(
                    counter.eq(counter+1),
                ),
            ],
            2: [ # Addr switch
                If(counter >= self.addr_switch_cycles,
                    state.eq(0),
                    self.begin.reset.send(),
                    self.addr.eq(self.next_addr),
                ).Else(
                    counter.eq(counter+1),
                ),
            ],
        })

        if with_csr:
            self.add_csrs()

    def start(self):
        return self.begin.set.send()

    def add_csrs(self):
        self.add_storage_csrs(
            'output_cycles',
            'addr_switch_cycles',
        )


class Hub75Driver(Module, CSRMixin):
    '''Drives output for a single row'''
    def __init__(self, data_driver, enable_driver):
        self.submodules.data_driver = data_driver
        self.submodules.enable_driver = enable_driver
        self.submodules.begin = FastLatch()
        self.busy = self.begin.out
        self.next_addr = Signal(5)

        state = Signal(2)
        plane = Signal(3)

        self.comb += [
            self.data_driver.lat_wait.eq(self.enable_driver.busy),
            self.data_driver.plane.eq(plane),
        ]

        self.sync += Case(state, {
            0: [ # Idle / still sending enable
                If(self.begin.out,
                    state.eq(1),
                    plane.eq(7),
                    self.data_driver.start(),
                ),
            ],
            1: [ # Sending data
                If(~self.data_driver.busy,
                    state.eq(2),
                    self.enable_driver.plane.eq(plane),
                    self.enable_driver.start(),
                    If(plane == 0,
                        self.enable_driver.next_addr.eq(self.next_addr),
                    ),
                ),
            ],
            2: [ # Sending enable
                    If(plane == 0,
                        state.eq(0),
                        self.begin.reset.send(),
                    ).Else(
                        state.eq(1),
                        plane.eq(plane-1),
                        self.data_driver.start(),
                    ),
            ],
        })

    def start(self):
        return self.begin.set.send()
