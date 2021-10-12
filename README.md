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

Configuration and status registers are exposed using Etherbone.

The Hub75Controller reads frames from DRAM into row buffers. Hub75Drivers
send the row buffers to the panels. Then the Hub75Controller drives the latch,
row address, and output enable signals.
