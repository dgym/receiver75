#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

import argparse
import csv
import os.path
import socket
import struct
import time

try:
    import numpy as np
except:
    np = None


csrs = None


def lookup_csr(name, csv_file=None):
    global csrs

    if csrs is None:
        if csv_file is None:
            csv_file = os.path.join(
                os.path.dirname(__file__),
                '..',
                'prebuilt/csr.csv',
            )

        csrs = {}
        with open(csv_file, 'r') as stream:
            reader = csv.reader(stream)
            for row in reader:
                if len(row) < 3:
                    continue
                if row[0] == 'csr_register':
                    csrs[row[1]] = int(row[2], base=0)

    return csrs[name]


def poke(eth_ip, addr, *vals):
    if isinstance(addr, str):
        addr = lookup_csr(addr)

    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    for val in vals:
        sock.sendto(
            struct.pack('!IIIII', 0x4e6f1044, 0, 0x00ff0100, addr, val),
            (eth_ip, 1234),
        )
        addr += 4


def process_image(im, gamma=2.5, scales=[1, 1, 1]):
    im = im * scales
    if gamma != 1:
        im = (((im / 255) ** gamma) * 255)
    im = np.clip(im, 0, 255)
    return im.astype(np.uint8)


def draw_panel(eth_ip, im, panel=0):
    im = im.reshape((64, 64, 3))

    # Send the data 4 rows as a time, so it fits in a 1500 byte
    # UDP packet.
    ints_per_row = 48
    sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

    for r in range(16):
        offset = (r*4*ints_per_row + panel*64*ints_per_row)
        sock.sendmsg(
            [
                struct.pack('<i', offset),
                im[r*4:r*4+4].flatten(),
            ],
            [],
            0,
            (eth_ip, 4343),
        )

    # Sending data too quickly impacts the output timing, give the
    # card some processing time after each panel's data has been sent.
    time.sleep(0.0001)


def draw_all_panels(eth_ip, im):
    for panel in range(16):
        draw_panel(eth_ip, im, panel)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eth-ip",
        default="192.168.0.39",
        help="Ethernet/Etherbone IP address",
    )
    parser.add_argument('--reset', action='store_true')
    parser.add_argument('--disable', action='store_true')
    parser.add_argument('--enable', action='store_true')
    parser.add_argument('--brightness', type=int)
    if np is not None:
        parser.add_argument('--solid')
    args = parser.parse_args()

    if args.reset:
        poke(args.eth_ip, lookup_csr('ctrl_reset'), 1)
        time.sleep(4)

    if args.disable:
        poke(args.eth_ip, lookup_csr('hub75_controller_enable'), 0)

    if args.brightness is not None:
        val = min(12, max(0, args.brightness))
        poke(args.eth_ip, lookup_csr('hub75_controller_output_cycles'), val)

    if args.solid is not None:
        rgb = int(args.solid, 0)
        im = np.ones((64, 64, 3)) * [
            (rgb >> 16) & 0xff,
            (rgb >> 8) & 0xff,
            rgb & 0xff,
        ]
        im = process_image(im)
        draw_all_panels(args.eth_ip, im)

    if args.enable:
        poke(args.eth_ip, lookup_csr('hub75_controller_enable'), 1)


if __name__ == "__main__":
    main()
