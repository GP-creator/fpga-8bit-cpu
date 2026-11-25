# 8-bit CPU -- Icarus Verilog simulation
#
#   make sim     compile + run the testbench
#   make wave    open the VCD in GTKWave
#   make verify  randomized verification vs. golden Python model (N=3000)
#   make mutate  mutation testing: inject 10 RTL bugs, check the suite catches them
#   make clean   remove build products

IVERILOG ?= iverilog
VVP      ?= vvp
GTKWAVE  ?= gtkwave

RTL   := rtl/cpu.v
TB    := sim/cpu_tb.v
VVPF  := sim/cpu_tb.vvp
VCD   := sim/cpu_tb.vcd

.PHONY: sim wave verify mutate clean

verify:
	python3 verify/run_random.py

mutate:
	python3 verify/mutate.py

sim:
	$(IVERILOG) -o $(VVPF) $(RTL) $(TB)
	$(VVP) $(VVPF)

wave: sim
	$(GTKWAVE) $(VCD)

clean:
	rm -f $(VVPF) $(VCD)
	rm -rf verify/work verify/__pycache__
