from typing import Self

from miningcat.config.runtime import module_command


class CliCommand:
    """The command line of a converter step run in its own process (python -m miningcat <command> ...): heavy
    libraries (Whisper, OCR) stay out of the GUI's process, and the step's output becomes the job's log.

        CliCommand("video").option("--model", "tiny").flag("--ocr", use_ocr).option("--ocr-fps", fps).build()
    """

    def __init__(self, *command: str):
        self._args = list(command)

    def option(self, name: str, value) -> Self:
        """`name value`, left out when the value is None."""
        if value is not None:
            self._args += [name, str(value)]
        return self

    def flag(self, name: str, enabled: bool = True) -> Self:
        if enabled:
            self._args.append(name)
        return self

    def args(self, *args: str) -> Self:
        self._args += list(args)
        return self

    def build(self) -> list[str]:
        return module_command("miningcat", *self._args)
