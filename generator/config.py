"""Configuration module."""
import logging
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, List, Optional, Tuple, Union

import click
import colorama
import toml
import yaslha.block
import yaslha.slha

from data import GM2CalcOutput, MicromegasOutput

logger = logging.getLogger(__name__)
BLUE = colorama.Fore.BLUE
RESET = colorama.Style.RESET_ALL
PathLike = Union[str, pathlib.Path]

SDECAY_IN = pathlib.Path(__file__).with_name("sdecay.in")
SDECAY_SLHA = "SD_leshouches.in"
SDECAY_OUT = "sdecay_slha.out"


class Config:
    @staticmethod
    def run_process(command, to_print=True, **kwargs):
        # type: (List[str], bool, Any) -> Tuple[int, str]
        logger.info(BLUE + " ".join(command) + RESET)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            **kwargs,
        )
        assert process and process.stdout
        if to_print:
            click.echo(colorama.Style.DIM)
        lines: List[str] = []
        for line in process.stdout:
            if to_print:
                click.echo(line, nl=False)
            lines.append(line)
        return_code = process.wait()
        if to_print:
            click.echo(RESET)
        if return_code != 0:
            logger.error(f"Run failed with exit code {return_code}.")
            logger.info(process.__dict__)
            exit()
        return return_code, "".join(lines)

    def __get_config(self, config: Any, key: str) -> str:
        """Check the value is non-empty string."""
        if (value := config.get(key)) is None:
            logger.error(f"'{key}' is not defined in {self.config_file}")
            sys.exit(1)
        if not (isinstance(value, str) and value):
            logger.error(f"Configuration {key}={value} is not valid.")
            sys.exit(1)
        return value

    def __init__(self, config_file: str = "config.toml") -> None:
        """Initialize the configuration."""
        self.config_file = config_file
        try:
            config = toml.load(config_file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_file}")
            logger.info(f"Consider to run 'cp config.toml.example {config_file}'")
            logger.info("and edit the file to configure this package.")
            sys.exit(1)
        self.calculator = self.__get_config(config["spectrum"], "calculator")
        self.simsusy = self.__get_config(config["external"], "simsusy")
        self.gm2calc = self.__get_config(config["external"], "gm2calc")
        self.sdecay = self.__get_config(config["external"], "sdecay")
        self.micromegas = {
            "make": self.__get_config(config["micromegas"], "make"),
            "dir": self.__get_config(config["micromegas"], "micromegas_dir"),
            "source": self.__get_config(config["micromegas"], "source_file"),
            "executable_name": self.__get_config(
                config["micromegas"], "executable_name"
            ),
        }
        self.micromegas_executable: Optional[Tuple[pathlib.Path, pathlib.Path]] = None
        sinderin_config = config["sinderin"]
        self.sinderin: Optional[Tuple[str, str]] = None
        if all(k in sinderin_config for k in ["converter", "ufo_model"]):
            self.sinderin = (
                self.__get_config(sinderin_config, "converter"),
                self.__get_config(sinderin_config, "ufo_model"),
            )

        self._setup_simsusy()
        self._setup_gm2calc()
        self._setup_micromegas()
        self._setup_sdecay()

    def _setup_simsusy(self) -> None:
        """Check if simsusy is installed and executable."""
        if shutil.which(self.simsusy) is None:
            logger.error(f"simsusy executable '{self.simsusy}' not found. See README.")
            exit(1)
        return

    def _setup_gm2calc(self) -> None:
        """Check if GM2Calc executable is available."""
        self.gm2calc = str(pathlib.Path(self.gm2calc).expanduser().resolve())
        if shutil.which(self.gm2calc) is None:
            logger.error(f"GM2Calc executable '{self.gm2calc}' not found. See README.")
            exit(1)
        return

    def _setup_micromegas(self) -> None:
        """Setup micromegas environment."""
        self.micromegas_executable = None

        # check config
        error = False
        make = self.micromegas["make"]
        dir = pathlib.Path(self.micromegas["dir"]).expanduser().resolve()
        source = pathlib.Path(self.micromegas["source"]).expanduser()
        if shutil.which(make) is None:
            logger.error(f"Make executable '{make}' not found.")
            error = True
        if not dir.is_dir():
            logger.error(f"micrOMEGAs path '{self.micromegas['dir']}' not found.")
            error = True
        if not source.is_file():
            logger.error(f"Source for micrOMEGAs '{source}' not found.")
            error = True
        if error:
            exit(1)

        # compile
        executable_path = (dir / self.micromegas["executable_name"]).resolve()
        new_source_path = executable_path.with_suffix(source.suffix)
        command = [make, "-C", str(dir), f"main={new_source_path.name}"]
        logger.info(
            f"Copy {BLUE}%s{RESET} to {BLUE}%s{RESET} and compile.",
            source,
            new_source_path,
        )
        shutil.copyfile(source, new_source_path)
        self.run_process(command, False)

        # check compile
        if shutil.which(executable_path) is None:
            logger.error(f"Compilation of {executable_path} failed.")
            exit(1)
        logger.info("Compilation of micrOMEGAs code is done successfully.")
        self.micromegas_executable = (dir, executable_path)

    def _setup_sdecay(self) -> None:
        """Check if SDecay executable is available."""
        self.sdecay = str(pathlib.Path(self.sdecay).expanduser().resolve())
        if shutil.which(self.sdecay) is None:
            logger.error(f"SDecay executable '{self.sdecay}' not found. See README.")
            exit(1)
        if not SDECAY_IN.is_file():
            logger.error(f"SDecay input file '{SDECAY_IN}' not found.")
            exit(1)
        if SDECAY_IN.read_text().find("SDECAY INPUT FILE") == -1:
            logger.error(f"SDecay input file '{SDECAY_IN}' seems invalid.")
            exit(1)
        return

    def run_simsusy(self, *args: PathLike) -> None:
        """Run simsusy."""
        command = [self.simsusy, "run", self.calculator] + [str(a) for a in args]
        self.run_process(command, False)

    def run_micromegas(self, slha1: pathlib.Path) -> MicromegasOutput:
        """Run micrOMEGAs."""
        if self.micromegas_executable is None:
            logger.error("micrOMEGAs is not configured.")
            exit(1)
        command = [str(self.micromegas_executable[1]), str(slha1.resolve())]

        _, output = self.run_process(
            command,
            cwd=self.micromegas_executable[0],
        )
        return MicromegasOutput(output)

    def run_gm2calc(self, slha1: pathlib.Path) -> GM2CalcOutput:
        """Run GM2Calc."""
        _, version = self.run_process([self.gm2calc, "--version"])
        original_input = yaslha.parse_file(slha1)
        original_input["GM2CalcConfig", 0] = 1  # request "DETAILED" output
        yaslha.dump_file(original_input, slha1.with_suffix(".gm2in"))
        command = [self.gm2calc, f"--slha-input-file={slha1.with_suffix('.gm2in')}"]
        _, output = self.run_process(command)
        return GM2CalcOutput(output, version)

    def run_sdecay(
        self, slha1: pathlib.Path
    ) -> Tuple[yaslha.block.InfoBlock, List[yaslha.block.Decay]]:
        """Run SDecay."""
        shutil.copyfile(slha1, SDECAY_SLHA)
        # add dummy block, otherwise SDecay complains.
        with open(SDECAY_SLHA, "a") as f:
            f.write("Block DUMMY #\n     1     0.00000000E+00   #\n")
        self.run_process([self.sdecay])
        result = yaslha.parse_file(SDECAY_OUT)
        os.remove(SDECAY_SLHA)
        shutil.move(SDECAY_OUT, slha1.with_suffix(".sdecay_raw"))
        dcinfo = result["DCINFO"]
        decays = list(result.decays.values())
        dcinfo.head.pre_comment = ["#"]
        for d in decays:
            d.head.pre_comment = ["#"]
        return dcinfo, decays

    def convert_to_sinderin(self, slha2: pathlib.Path) -> None:
        if self.sinderin is None:
            logger.error("Sinderin is not configured.")
            exit(1)
        command = ["python", *self.sinderin, str(slha2)]
        _, output = self.run_process(command, False)
        with open(slha2.with_suffix(".sinderin"), "w") as f:
            f.write(output)
