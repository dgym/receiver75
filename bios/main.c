// SPDX-FileCopyrightText: 2021 Jim Bailey <dgym.bailey@gmail.com>
// SPDX-License-Identifier: MIT

#include <irq.h>
#include <uart.h>

#include <generated/csr.h>

#include <liblitedram/sdram.h>


static uint32_t spi_flash_read(uint32_t addr) {
    // select
    spiflash_spi_cs_write(1);

    // set mosi
    csr_write_simple(0x03, CSR_SPIFLASH_SPI_MOSI_ADDR);
    csr_write_simple(addr<<8, CSR_SPIFLASH_SPI_MOSI_ADDR + 4);

    // transfer
    spiflash_spi_control_write((40 << 8) | 1);

    while (!(spiflash_spi_status_read() & 1)) {
    }

    return csr_read_simple(CSR_SPIFLASH_SPI_MISO_ADDR + 4);
}


int main(int i, char **c)
{
#ifdef CONFIG_CPU_HAS_INTERRUPT
    irq_setmask(0);
    irq_setie(1);
#endif
#ifdef CSR_UART_BASE
    uart_init();
#endif

    uint32_t config_idx = 4000000;

    uint32_t ip_addr = 0;
    ip_addr = spi_flash_read(config_idx++) & 0xff; ip_addr <<= 8;
    ip_addr |= spi_flash_read(config_idx++) & 0xff; ip_addr <<= 8;
    ip_addr |= spi_flash_read(config_idx++) & 0xff; ip_addr <<= 8;
    ip_addr |= spi_flash_read(config_idx++) & 0xff;

    uint64_t mac_addr = 0;
    mac_addr = spi_flash_read(config_idx++) & 0xff; mac_addr <<= 8;
    mac_addr |= spi_flash_read(config_idx++) & 0xff; mac_addr <<= 8;
    mac_addr |= spi_flash_read(config_idx++) & 0xff; mac_addr <<= 8;
    mac_addr |= spi_flash_read(config_idx++) & 0xff; mac_addr <<= 8;
    mac_addr |= spi_flash_read(config_idx++) & 0xff; mac_addr <<= 8;
    mac_addr |= spi_flash_read(config_idx++) & 0xff;

    hub75_soc_mac_address_write(mac_addr);
    hub75_soc_ip_address_write(ip_addr);

    sdram_init();

    while(1) {
    }

    return 0;
}


void isr(void) {
}
