from __future__ import annotations

from mcm_agent.cli_commands.api import ApiCommand
from mcm_agent.cli_commands.git import GitCommand
from mcm_agent.cli_commands.imports import build_import_commands
from mcm_agent.cli_commands.init import InitCommand
from mcm_agent.cli_commands.start import StartCommand
from mcm_agent.cli_commands.status import OutputsCommand, ResetCommand, StatusCommand


def build_command_registry() -> dict[str, object]:
    commands = [
        ApiCommand(),
        GitCommand(),
        InitCommand(),
        StartCommand(),
        OutputsCommand(),
        ResetCommand(),
        StatusCommand(),
        *build_import_commands(),
    ]
    return {command.name: command for command in commands}
