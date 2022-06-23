#!python
"""Scripts of this package."""

import logging
import pathlib

import click
import coloredlogs
import yaslha
from config import Config

logger = logging.getLogger(__name__)

__pkgname__ = "MSSM electroweak spectrum generator"
__version__ = "0.0.0"
CONFIG_FILE = "config.toml"


def message(message: str) -> None:
    """Print a message as a separator."""
    click.echo("")
    click.echo("#" * 80)
    click.echo(f"# {message}{' '*max(1, 77 - len(message))}#")
    click.echo("#" * 80)


def run(config: Config, input_path: pathlib.Path) -> None:
    """Calculate everything."""
    message("Generate spectrum by SimSUSY (SLHA1 and SLHA2)")
    slha1_path = pathlib.Path(".") / input_path.with_suffix(".slha1").name
    slha2_path = pathlib.Path(".") / input_path.with_suffix(".slha2").name
    config.run_simsusy(input_path, slha2_path)
    config.run_simsusy("--v1", input_path, slha1_path)
    # micromegas and gm2calc
    micromegas = config.run_micromegas(slha1_path)
    gm2calc = config.run_gm2calc(slha1_path)
    dcinfo, decays = config.run_sdecay(slha1_path)
    # dump
    slha2 = yaslha.parse_file(slha2_path)
    slha2.add_block(micromegas.to_slha_block())
    slha2.add_block(gm2calc.to_slha_block())
    slha2.add_block(dcinfo)
    for d in decays:
        slha2.add_block(d)
    yaslha.dump_file(
        slha2, slha2_path, comments_preserve=yaslha.dumper.CommentsPreserve.ALL
    )
    # convert to sinderin
    config.convert_to_sinderin(slha2_path)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "-c",
    default=CONFIG_FILE,
    type=click.Path(exists=True, dir_okay=False),
    help="Specify configuration file.",
    show_default=True,
)
@click.argument("input", type=click.Path(exists=True, dir_okay=False))
@click.version_option(__version__, "-V", "--version", prog_name=__pkgname__)
def main(**args: str) -> None:
    """Handle SLHA format data."""
    coloredlogs.install(logger=logging.getLogger(), fmt="%(levelname)8s %(message)s")
    message("Configuration")
    config = Config(config_file=args.get("c", CONFIG_FILE))
    input_file = pathlib.Path(args["input"])
    run(config, input_file)


if __name__ == "__main__":
    main()
