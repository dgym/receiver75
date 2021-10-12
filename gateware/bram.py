# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

from migen import *


class BRAM(Module):
    def __init__(self, width, depth, init=None, cd_read='sys', cd_write='sys'):
        self.width = width
        self.depth = depth

        self.specials.mem = Memory(width, depth, init=init)
        self.specials.read = self.mem.get_port(clock_domain=cd_read, mode=READ_FIRST)
        self.specials.write = self.mem.get_port(write_capable=True, clock_domain=cd_write)
