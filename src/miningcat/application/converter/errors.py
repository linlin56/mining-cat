class ConverterError(Exception):
    """A step of the converter that can't run (missing files, invalid options...): shown to the user as is."""

    def __init__(self, message: str, title: str = "Converter"):
        super().__init__(message)
        self.title = title
