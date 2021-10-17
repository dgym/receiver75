# Receiver75 - open source software/gateware for the Colorlight 5A-75B v8

This project is a replacement for the stock gateware on a 5A-75B card. Its
purpose is the same - to receive frames over ethernet and drive LED matricies.

## Notable differences

The stock gateware uses the same MAC address on every card, so only 1 receiver
card can be present on a physical network. This gateware uses a configurable
MAC address.

The stock gateware receives the framebuffer in raw ethernet frames. This
gateware uses UDP packets. The IP address is confgurable.

This gateware is currently hardcoded for panels with 64x64 LEDs. Patches to
improve this would be welcome.

This gateware is currently hardcoded to drive only two panels per
connector. This is to enable a refresh rate of 400Hz. Again, making this
configurable would be nice.

This gateware exposes some configuration registers. These can be set by
sending UDP packets.

One of these configuration registers is for the base address of the
framebuffer. This makes it possible to double buffer the display data and
have tighter synchronization when using multiple receiver cards.

## General operation

Once the gateware and the MAC+IP addresses have been flashed, the sender
sends the first frame to the card, then sends the enable command. For single
buffering the sender sends the next frame to the same area of memory. For
double buffering the sender sends the next frame to a different area of
memory, then sends a command to update which area of memory to display.

## Design overview

The UdpDramWriter module receives UDP packets and writes their content to DRAM.

Configuration and status registers can be set using UDP packets.

The Hub75Controller reads frames from DRAM into row buffers. Hub75Drivers
send the row buffers to the panels. Then the Hub75Controller drives the latch,
row address, and output enable signals.

# Installation

To flash the prebuilt bit file to the board use a JTAG programmer and
compatible software.

For example, it is possible to use an FTDI 232 breakout board and
openFPGALoader: `openFPGALoader -cft232 --freq 10M --write-flash
prebuilt/colorlight_5a_75b.bit`

Then generate a config file to specify the IP Address: `python3
tools/make_config.py --eth-ip 192.168.0.39 --format bin`

And finally flash the config to the board at address 4000000: `openFPGALoader
-cft232 --freq 10M --write-flash --offset 4000000 config.bin`

# Testing

Once the gateware and config have been flashed, the board should be on
available on the network. This can be tested with ping e.g. `ping 192.168.0.39`

The display can be enabled with the sender75.py tool: `./tools/sender75.py
--eth-ip 192.168.0.39 --enable`

The sender75.py tool can also send some test patterns: `./tools/sender75.py
--eth-ip 192.168.0.39 --solid 0xffffff`
