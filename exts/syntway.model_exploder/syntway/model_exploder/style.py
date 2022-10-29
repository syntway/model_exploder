from pathlib import Path

import omni.ui as ui
from omni.ui import color as cl
from .libs.ui_utils import COLOR_TRANSP_NOT_0, COLOR_DISABLED

COLOR_TEXT = 0xffcccccc

THIS_FOLDER_PATH = Path(__file__).parent.absolute()
EXT_ROOT_FOLDER_PATH = THIS_FOLDER_PATH.parent.parent
ICONS_PATH = EXT_ROOT_FOLDER_PATH.joinpath("data").joinpath("icons")


# window frame cascade
WINDOW_FRAME = {
    "ComboBox": {
        "border_radius": 6, 
        "margin": 0,
    },
    "ComboBox:disabled": {
        "color": COLOR_DISABLED,
    },

    "Slider": {
        "draw_mode": ui.SliderDrawMode.HANDLE,
        "color": COLOR_TRANSP_NOT_0,
        "border_radius": 6,
    },
    "Slider:disabled": {
        "secondary_color": COLOR_DISABLED,
    },

    "CheckBox:disabled": {
        "background_color": COLOR_DISABLED,
    },

    "Button.Label:disabled": {
        "color": COLOR_DISABLED,
    },

    "Button.Label::ever_bright": {
        "color": cl.white,
    },
    "Button.Label::ever_bright:disabled": {
        "color": cl.white,
    },

    "Image::info": {
        "image_url": str(ICONS_PATH / "info.svg"),
        "color": COLOR_TEXT,
    },
    "Image::info:hovered": {
        "image_url": str(ICONS_PATH / "info.svg"),
        "color": cl.white,
    },

    "Line": {
        "color": COLOR_DISABLED
    },

    "CollapsableFrame": {
        "border_radius": 4, 
    },
    
}



