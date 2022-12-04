from pathlib import Path

import omni.ui as ui
from omni.ui import color as cl
from .libs.ui_utils import UiPal


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
        "color": UiPal.TEXT_DISABLED,
    },

    "Slider": {
        "draw_mode": ui.SliderDrawMode.HANDLE,
        "color": UiPal.TRANSP_NOT_0,
        "border_radius": 6,
    },
    "Slider:disabled": {
        "secondary_color": UiPal.TEXT_DISABLED,
    },

    "CheckBox:disabled": {
        "background_color": UiPal.TEXT_DISABLED,
    },

    "Button.Label:disabled": {
        "color": UiPal.TEXT_DISABLED,
    },

    "Button.Label::ever_bright": {
        "color": cl.white,
    },
    "Button.Label::ever_bright:disabled": {
        "color": cl.white,
    },

    "Image::info": {
        "image_url": str(ICONS_PATH / "info.svg"),
        "color": UiPal.TEXT,
    },
    "Image::info:hovered": {
        "image_url": str(ICONS_PATH / "info.svg"),
        "color": cl.white,
    },

    "Line": {
        "color": UiPal.TEXT_DISABLED
    },

    "CollapsableFrame": {
        "border_radius": 4, 
    },
    
}



