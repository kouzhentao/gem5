#!/usr/bin/env python3
"""Full-system baremetal: Andes MinorCPU+RVV + optional TimingSimple warmup.

Warmup (default): TimingSimpleCPU fills system L1, m5_switch_cpu → Minor
(takeOverFrom keeps warmed L1). --no-warmup / --atomic as alternatives.
"""

import argparse
import os

import m5
from m5.objects import (
    AddrRange,
    AtomicSimpleCPU,
    BadAddr,
    Bridge,
    DDR3_1600_8x8,
    Frequency,
    HiFive,
    IOXBar,
    MemCtrl,
    PMAChecker,
    RiscvBareMetal,
    RiscvISA,
    RiscvMinorCPU,
    RiscvRTC,
    RiscvSemihosting,
    RiscvTimingSimpleCPU,
    Root,
    SrcClockDomain,
    System,
    SystemXBar,
    VoltageDomain,
)

from andes_46mpv_scalar import (
    apply_andes_scalar_cpu,
    configure_andes_mem_ctrl,
    make_andes_l1_dcache,
    make_andes_l1_icache,
)


def make_isa(vlen, elen):
    return RiscvISA(enable_rvv=True, vlen=vlen, elen=elen)


def make_atomic_cpu(cpu_id, isa):
    cpu = AtomicSimpleCPU(cpu_id=cpu_id)
    cpu.isa = [isa]
    return cpu


def make_timing_cpu(cpu_id, isa):
    cpu = RiscvTimingSimpleCPU(cpu_id=cpu_id)
    cpu.isa = [isa]
    # Same PMP structure as Minor (cfg NDS_PMP_ENTRIES=4); warmup only.
    cpu.mmu.pmp.pmp_entries = 4
    return cpu


def make_minor_cpu(cpu_id, isa, switched_out=False):
    cpu = RiscvMinorCPU(cpu_id=cpu_id, switched_out=switched_out)
    cpu.isa = [isa]
    apply_andes_scalar_cpu(cpu)
    return cpu


def attach_pma(cpu, system):
    # cfg NDS_UNALIGNED_ACCESS=yes → HW unaligned load/store (no trap).
    # gem5: nonempty PMAChecker.misaligned skips strict vaddr align and
    # allows paddr misalign in those ranges. Does not model multi-beat
    # split latency (RTL may take extra cycles on una).
    cpu.mmu.pma_checker = PMAChecker(
        uncacheable=[
            *system.platform._on_chip_ranges(),
            *system.platform._off_chip_ranges(),
        ],
        misaligned=list(system.mem_ranges),
    )


def attach_cpu_to_l1(cpu, system):
    cpu.createThreads()
    cpu.icache_port = system.l1i.cpu_side
    cpu.dcache_port = system.l1d.cpu_side
    cpu.mmu.connectWalkerPorts(
        system.membus.cpu_side_ports, system.membus.cpu_side_ports
    )
    cpu.createInterruptController()
    attach_pma(cpu, system)


parser = argparse.ArgumentParser()
parser.add_argument("-b", "--binary", required=True)
parser.add_argument("-v", "--vlen", type=int, default=1024)
parser.add_argument("-e", "--elen", type=int, default=64)
parser.add_argument("--atomic", action="store_true")
parser.add_argument("--no-warmup", action="store_true")
parser.add_argument(
    "--score-ticks",
    type=int,
    default=5_000_000_000,
    help="After Timing→Minor switch, simulate at most this many ticks "
    "then exit (dump stats). Avoids multi-minute CoreMark teardown hang. "
    "0 = unbounded.",
)
args = parser.parse_args()

binary = os.path.abspath(args.binary)
if not os.path.isfile(binary):
    raise SystemExit(f"binary not found: {binary}")

warmup = not args.atomic and not args.no_warmup

system = System()
system.mem_mode = "atomic" if args.atomic else "timing"
system.voltage_domain = VoltageDomain()
system.clk_domain = SrcClockDomain(
    clock="1GHz", voltage_domain=system.voltage_domain
)
system.mem_ranges = [AddrRange(start=0x80000000, size="512MB")]

if args.atomic:
    system.cpu = [make_atomic_cpu(0, make_isa(args.vlen, args.elen))]
elif warmup:
    system.cpu = [make_timing_cpu(0, make_isa(args.vlen, args.elen))]
    system.switch_cpus = [
        make_minor_cpu(0, make_isa(args.vlen, args.elen), switched_out=True)
    ]
else:
    system.cpu = [make_minor_cpu(0, make_isa(args.vlen, args.elen))]

system.membus = SystemXBar()
system.membus.badaddr_responder = BadAddr()
system.membus.default = system.membus.badaddr_responder.pio
system.system_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
configure_andes_mem_ctrl(system.mem_ctrl)
system.mem_ctrl.port = system.membus.mem_side_ports

system.l1i = make_andes_l1_icache()
system.l1d = make_andes_l1_dcache()
system.l1i.mem_side = system.membus.cpu_side_ports
system.l1d.mem_side = system.membus.cpu_side_ports

system.platform = HiFive()
system.platform.rtc = RiscvRTC(frequency=Frequency("100MHz"))
system.platform.clint.int_pin = system.platform.rtc.int_pin
system.platform.setNumCores(1)

system.iobus = IOXBar()
system.bridge = Bridge(delay="50ns")
system.bridge.mem_side_port = system.iobus.cpu_side_ports
system.bridge.cpu_side_port = system.membus.mem_side_ports
system.bridge.ranges = system.platform._off_chip_ranges()

system.iobus.cpu_side_ports = system.platform.pci_host.up_request_port()
system.iobus.mem_side_ports = system.platform.pci_host.up_response_port()
system.platform.pci_bus.cpu_side_ports = (
    system.platform.pci_host.down_request_port()
)
system.platform.pci_bus.default = system.platform.pci_host.down_response_port()
system.platform.pci_bus.config_error_port = (
    system.platform.pci_host.config_error.pio
)

system.platform.attachOnChipIO(system.membus)
system.platform.attachOffChipIO(system.iobus)
system.platform.attachPlic()

for cpu in system.cpu:
    attach_cpu_to_l1(cpu, system)

if warmup:
    for cpu in system.switch_cpus:
        cpu.clk_domain = system.cpu[0].clk_domain
        cpu.createThreads()
        cpu.mmu.connectWalkerPorts(
            system.membus.cpu_side_ports, system.membus.cpu_side_ports
        )
        attach_pma(cpu, system)

system.workload = RiscvBareMetal(
    bootloader=binary,
    bare_metal=True,
    semihosting=RiscvSemihosting(),
)

root = Root(full_system=True, system=system)
m5.instantiate()
print(
    f"Minor+RVV BM: binary={binary} vlen={args.vlen} elen={args.elen} "
    f"atomic={args.atomic} warmup={warmup}",
    flush=True,
)

switch_list = [(system.cpu[0], system.switch_cpus[0])] if warmup else None
do_warmup = warmup
# After switch: optional bounded score window (dump stats without teardown hang).
score_ticks = args.score_ticks if warmup else 0

while True:
    if (not do_warmup) and score_ticks:
        exit_event = m5.simulate(score_ticks)
    else:
        exit_event = m5.simulate()
    cause = exit_event.getCause()
    if do_warmup and cause == "switchcpu":
        print(
            f"Warmup done @ tick {m5.curTick()}: TimingSimple → Minor",
            flush=True,
        )
        m5.switchCpus(system, switch_list)
        m5.stats.reset()
        print("Stats reset after CPU switch; scoring on Minor", flush=True)
        do_warmup = False
        switch_list = None
        continue
    print(f"Exiting @ tick {m5.curTick()} because {cause}", flush=True)
    break
