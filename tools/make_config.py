#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
# SPDX-License-Identifier: MIT

import argparse
import struct


def hex_line(address, record_type, data):
    byte_count = len(data) & 0xff
    record = bytes([byte_count, address >> 8, address & 0xff, record_type]) + data
    chk = sum(record)
    return ':' + ''.join(f'{b:02X}' for b in (record + bytes([-chk & 0xff])))


def write_hex_file(config):
    with open('config.hex', 'w') as stream:
        # Set 32bit address to 4000000.
        stream.write(hex_line(0, 5, struct.pack('!i', 4000000)) + '\n')
        # Data record.
        stream.write(hex_line(0, 0, config) + '\n')
        # EOF record.
        stream.write(hex_line(0, 1, b'') + '\n')


def write_bin_file(config):
    with open('config.bin', 'wb') as stream:
        stream.write(config)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eth-ip",
        default="192.168.0.39",
        help="Ethernet/Etherbone IP address"
    )
    parser.add_argument(
        "--format",
        default="hex",
        choices=['bin', 'hex'],
        help="The type of flash file to write"
    )
    args = parser.parse_args()

    # Get the IP address components.
    parts = args.eth_ip.split('.')
    assert len(parts) == 4

    parts = [int(part) for part in parts]
    assert min(parts) >= 0
    assert max(parts) <= 255

    config = bytes(
        # First the IP address.
        parts +
        # Then the MAC address common prefix.
        [0x06, 0xd5] +
        # Then the MAC address suffix, which is the IP address again.
        parts
    )

    if args.format == 'bin':
        write_bin_file(config)
    elif args.format == 'hex':
        write_hex_file(config)


if __name__ == "__main__":
    main()
