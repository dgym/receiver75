# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *

from utils import FastLatch


class PartialShifterRight(Module):
    def __init__(self, port, output_width):
        # Interface
        self.specials.port = port
        self.start = Signal(port.adr.nbits)
        self.count = Signal(32)
        self.busy = Signal()
        self.output = Signal(output_width)

        # State
        self.submodules._begin = FastLatch()
        src_bits = port.dat_r.nbits

        last = Signal(src_bits)
        level = Signal(8)
        next_level = Signal(8)
        loading = Signal(reset=1)
        self.next_addr = next_addr = Signal(port.adr.nbits)

        state = Signal()
        counter = Signal(port.adr.nbits+1)

        self.comb += [
            self.busy.eq(self._begin.out),
            self.output.eq((port.dat_r << level) | last),
            If(self._begin.set.out,
                port.adr.eq(self.start),
            ).Else(
                port.adr.eq(next_addr),
            ),
            If(loading,
                next_level.eq(level+(src_bits-output_width)),
            ).Else(
                next_level.eq(level-output_width),
            ),
        ]

        self.sync += [
            If(~state,
                If(self._begin.out,
                    state.eq(1),
                    counter.eq(0),
                    level.eq(0),
                    If((output_width << 1) >= src_bits,
                        next_addr.eq(self.start+1),
                    ).Else(
                        next_addr.eq(self.start),
                    ),
                ),
            ).Else(
                level.eq(next_level),

                If(loading,
                    last.eq(port.dat_r>>(output_width-level)),
                ).Else(
                    last.eq(last>>output_width),
                ),

                If(next_level < 40,
                    loading.eq(1),
                    next_addr.eq(next_addr+1),
                ).Else(
                    loading.eq(0),
                ),

                If(counter >= self.count - 1,
                    self._begin.reset.send(),
                    loading.eq(1),
                    state.eq(0),
                ).Else(
                    counter.eq(counter+1),
                ),
            ),
        ]

    def begin(self):
        return self._begin.set.send()


class PartialShifter(Module):
    def __init__(self, port, output_width):
        # Interface
        self.specials.port = port
        self.start = Signal(port.adr.nbits)
        self.count = Signal(32)
        self.busy = Signal()
        self.output = Signal(output_width)

        # State
        self.submodules._begin = FastLatch()
        src_bits = port.dat_r.nbits
        dst_bits = output_width
        buf_bits = 2*src_bits

        last_level = Signal(8)
        last_buffer = Signal(buf_bits)
        buffer = Signal(buf_bits)

        loading = Signal()

        self.next_addr = next_addr = Signal(port.adr.nbits)
        next_level = Signal(8)

        state = Signal()
        counter = Signal(port.adr.nbits+1)

        self.comb += [
            self.busy.eq(self._begin.out),
            If(self._begin.set.out,
                port.adr.eq(self.start),
            ).Else(
                port.adr.eq(next_addr),
            ),
            If(loading,
                buffer.eq(last_buffer + (port.dat_r << ((buf_bits-src_bits) - last_level))),
                next_level.eq(last_level+(src_bits-output_width)),
            ).Else(
                buffer.eq(last_buffer),
                next_level.eq(last_level-output_width),
            ),
            self.output.eq(buffer>>(buf_bits-dst_bits)),
        ]

        self.sync += [
            If(~state,
                If(self._begin.out,
                    state.eq(1),
                    counter.eq(0),
                    last_buffer.eq(0),
                    last_level.eq(0),
                    loading.eq(1),
                    next_addr.eq(self.start + (1 if output_width * 2 >= src_bits else 0)),
                ),
            ).Else(
                last_buffer.eq(buffer<<output_width),
                If(next_level < output_width,
                    loading.eq(1),
                    If(next_level < (output_width*2 - src_bits),
                        next_addr.eq(next_addr+1),
                    ),
                ).Else(
                    loading.eq(0),
                    If(next_level < (output_width*2),
                        next_addr.eq(next_addr+1),
                    ),
                ),
                last_level.eq(next_level),

                If(counter >= self.count - 1,
                    self._begin.reset.send(),
                    loading.eq(1),
                    state.eq(0),
                ).Else(
                    counter.eq(counter+1),
                ),
            ),
        ]

    def begin(self):
        return self._begin.set.send()
