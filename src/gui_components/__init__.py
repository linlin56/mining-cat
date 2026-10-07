# The Tkinter panels are imported lazily so that the non-GUI modules of this package
# (pipeline, constants, utils) can be used without tkinter installed - the web GUI relies on that.
_PANELS = {
    "AudioPanel": "gui_components.audio_panel",
    "EpubPanel": "gui_components.epub_panel",
    "GamePanel": "gui_components.game_panel",
    "LogPanel": "gui_components.log_panel",
    "VideoPanel": "gui_components.video_panel",
}

__all__ = list(_PANELS)


def __getattr__(name: str):
    module_name = _PANELS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'gui_components' has no attribute {name!r}")
    import importlib
    return getattr(importlib.import_module(module_name), name)
