"""Configuration module."""
import logging
import pathlib
import shutil
import subprocess
import sys
from typing import Any, List, Optional, Tuple, Union

import click
import colorama
import toml
import yaslha.slha

from data import GM2CalcOutput, MicromegasOutput

logger = logging.getLogger(__name__)
BLUE = colorama.Fore.BLUE
RESET = colorama.Style.RESET_ALL
PathLike = Union[str, pathlib.Path]


class Config:
    @staticmethod
    def run_process(command: List[str], **kwargs: Any) -> Tuple[int, str]:
        logger.info(BLUE + " ".join(command) + RESET)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            **kwargs,
        )
        assert process and process.stdout
        click.echo(colorama.Style.DIM)
        lines: List[str] = []
        for line in process.stdout:
            click.echo(line, nl=False)
            lines.append(line)
        return_code = process.wait()
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
        self.micromegas = {
            "make": self.__get_config(config["micromegas"], "make"),
            "dir": self.__get_config(config["micromegas"], "micromegas_dir"),
            "source": self.__get_config(config["micromegas"], "source_file"),
            "executable_name": self.__get_config(
                config["micromegas"], "executable_name"
            ),
        }
        self.micromegas_executable: Optional[Tuple[pathlib.Path, pathlib.Path]] = None
        self._setup_simsusy()
        self._setup_gm2calc()
        self._setup_micromegas()

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
        logger.info(BLUE + " ".join(command) + RESET)
        click.echo(colorama.Style.DIM)
        subprocess.run(command)
        click.echo(RESET)

        # check compile
        if shutil.which(executable_path) is None:
            logger.error(f"Compilation of {executable_path} failed.")
            exit(1)
        logger.info("Compilation of micrOMEGAs code is done successfully.")
        self.micromegas_executable = (dir, executable_path)

    def run_simsusy(self, *args: PathLike) -> None:
        """Run simsusy."""
        command = [self.simsusy, "run", self.calculator] + [str(a) for a in args]
        logger.info(BLUE + " ".join(command) + RESET)
        click.echo(colorama.Style.DIM)
        subprocess.run(command)
        click.echo(RESET)

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
