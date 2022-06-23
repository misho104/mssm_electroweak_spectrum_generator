import logging
import re
from typing import Dict, List, TypeVar

import yaslha.block

logger = logging.getLogger(__name__)
T = TypeVar("T")


def check_result(title, match: List[T]) -> T:
    if len(match) == 0:
        logger.error(f"Cannot find {title} in micrOMEGAs output.")
        exit(1)
    elif len(match) > 1:
        logger.warning(f"Multiple {title} found in output; first is used.")
    return match[0]


class MicromegasOutput:
    NUM = r"([-+]?(?:\d*\.\d+|\d+)(?:[eEdD][-+]?\d+)?)"
    RE_OMEGA = re.compile(r"relic density.*$\s+^.*Omega\s*=\s*" + NUM, re.M)
    RE_PROTON = re.compile(r"\s+".join(["proton", "SI", NUM, "SD", NUM]), re.M)
    RE_NEUTRON = re.compile(r"\s+".join(["neutron", "SI", NUM, "SD", NUM]), re.M)

    @classmethod
    def parse_output(cls, output: str) -> Dict[str, float]:
        """Parse micromegas output."""
        omega = check_result("omega_DM", cls.RE_OMEGA.findall(output))
        proton = check_result("proton", cls.RE_PROTON.findall(output))
        neutron = check_result("proton", cls.RE_NEUTRON.findall(output))
        return {
            "omega_h2": float(omega),
            "proton_si": float(proton[0]),
            "proton_sd": float(proton[1]),
            "neutron_si": float(neutron[0]),
            "neutron_sd": float(neutron[1]),
        }

    def __init__(self, output_lines: str) -> None:
        result = self.parse_output(output_lines)
        self.omega_h2 = result["omega_h2"]
        self.proton_si = result["proton_si"]  # [pb]
        self.proton_sd = result["proton_sd"]  # [pb]
        self.neutron_si = result["neutron_si"]  # [pb]
        self.neutron_sd = result["neutron_sd"]  # [pb]

    def to_slha_block(self, block_name: str = "DM") -> yaslha.block.Block:
        """Convert to SLHA block."""
        block = yaslha.block.Block(block_name)
        block.head.comment = "calculated by micrOMEGAs"
        # Motoi's convention?
        block[1] = self.omega_h2
        block[2] = self.proton_si
        block[3] = self.proton_sd
        block[4] = self.neutron_si
        block[5] = self.neutron_sd
        block.comment[1] = "OmegaDM h^2"
        block.comment[2] = "proton SI [pb]"
        block.comment[3] = "proton SD [pb]"
        block.comment[4] = "neutron SI [pb]"
        block.comment[5] = "neutron SD [pb]"
        return block


class GM2CalcOutput:
    NUM = r"([-+]?(?:\d*\.\d+|\d+)[eE][-+]?\d+)"
    RE_2L = re.compile(
        r"amu \(1-loop \+ 2-loop best\)\s*=\s*" + NUM + r"\s*\+-\s*" + NUM
    )
    RE_START_WITH_ALPHA_NUM = re.compile(r"^\w")
    RE_NUM_LINE = re.compile(r"^\s*" + NUM)
    RE_NORMAL_LINE = re.compile(r"^\s*(.+?)\s+" + NUM)

    @classmethod
    def parse_output(cls, output: str) -> Dict[str, float]:
        """Parse GM2Calc output."""
        # get the 2-loop value
        best_value = check_result("1L+2L", cls.RE_2L.findall(output))
        # collect blocks
        blocks: Dict[str, Dict[str, float]] = {}
        tag = ""
        for line in output.split("\n"):
            if cls.RE_START_WITH_ALPHA_NUM.match(line):
                tag = re.sub(r"[^A-Z0-9 ]", "", line.strip().upper())
                blocks[tag] = {}
            elif tag and (match := cls.RE_NUM_LINE.match(line)):
                blocks[tag]["NO KEY"] = float(match[1])
            elif tag and (match := cls.RE_NORMAL_LINE.match(line)):
                blocks[tag][match[1]] = float(match[2])

        result: Dict[str, float] = {}
        result["1L+2L"] = best_value[0]
        result["1L+2L_unc"] = best_value[1]
        result["1L"] = blocks["FULL 1L WITH TANBETA RESUMMATION"]["sum"]
        result["1L_no_resum"] = blocks["FULL 1L WITHOUT TANBETA RESUMMATION"]["NO KEY"]
        result["WHN"] = blocks["1L APPROXIMATION WITH TANBETA RESUMMATION"]["W-H-nu"]
        result["WHL"] = blocks["1L APPROXIMATION WITH TANBETA RESUMMATION"]["W-H-muL"]
        result["BHL"] = blocks["1L APPROXIMATION WITH TANBETA RESUMMATION"]["B-H-muL"]
        result["BHR"] = blocks["1L APPROXIMATION WITH TANBETA RESUMMATION"]["B-H-muR"]
        result["BLR"] = blocks["1L APPROXIMATION WITH TANBETA RESUMMATION"]["B-muL-muR"]
        result["2L"] = blocks["2L BEST WITH TANBETA RESUMMATION"]["NO KEY"]
        result["2L_no_resum"] = blocks["2L BEST WITHOUT TANBETA RESUMMATION"]["NO KEY"]
        result["2L_photonic"] = blocks["PHOTONIC WITH TANBETA RESUMMATION"]["sum"]
        result["2L_fermion"] = blocks[
            "FERMIONSFERMION APPROXIMATION WITH TANBETA RESUMMATION"
        ]["sum"]
        result["2L_a"] = blocks[
            "2LA 1L INSERTIONS INTO 1L SM DIAGRAM WITH TANBETA RESUMMATION"
        ]["sum"]

        result["1L+2L_no_resum"] = result["1L_no_resum"] + result["2L_no_resum"]

        # calculate tanbeta correction
        tb_cor = blocks["TANBETA CORRECTION"]["amu(1L) * (1 / (1 + Delta_mu) - 1) ="]
        result["delta_mu"] = 1 / (tb_cor / result["1L_no_resum"] + 1) - 1
        return result

    def __init__(self, output_lines: str, version: str = "Unknown") -> None:
        self.data = self.parse_output(output_lines)
        self.version = version

    def to_slha_block(self, block_name: str = "GM2") -> yaslha.block.Block:
        """Convert to SLHA block."""
        block = yaslha.block.Block(block_name)
        block.head.comment = f"calculated by GM2Calc v{self.version}"
        convention = [
            (1, "1L", "1-loop result"),
            (2, "1L+2L", "2-loop result"),
            (9, "1L+2L_unc", "uncertainty for 2-loop result"),
            (10, "1L_no_resum", "1-loop without resummation"),
            (20, "1L+2L_no_resum", "2-loop without resummation"),
            (100, "delta_mu", "delta_mu"),
            (101, "WHN", "MI-approx W-H-nu"),
            (102, "WHL", "MI-approx W-H-L"),
            (103, "BHL", "MI-approx B-H-L"),
            (104, "BHR", "MI-approx B-H-R"),
            (105, "BLR", "MI-approx B-L-R"),
            (201, "2L_photonic", "2-loop photonic"),
            (202, "2L_fermion", "2-loop fermion/sfermion"),
            (203, "2L_a", "2-loop (a)"),
        ]
        for i, key, comment in convention:
            block[i] = self.data[key]
            block.comment[i] = comment
        return block
