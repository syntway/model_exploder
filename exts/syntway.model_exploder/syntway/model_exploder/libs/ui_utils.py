"""
Utility UI functions.
"""

from enum import IntEnum

import omni.ui as ui

VERSION = 4



class UiPaletteDark(IntEnum):
    """Colors in 0xAABBGGRR format. All colors with ff alpha if possible"""
    BACK = 0xff23211f  # darker than WINDOW_BACK: general widget background, window title bar
    BACK_SELECTED = 0xff6e6e6e
    BACK_HOVERED = BACK_SELECTED

    TEXT = 0xffcccccc
    TEXT_SELECTED = 0xff8b8a8a
    TEXT_DISABLED = 0xff505050

    WINDOW_BACK = 0xff454545  # lighter than BACK: window base color where darker controls are placed

    TOOLTIP_TEXT = 0xff303030
    TOOLTIP_BACK = 0xffaadddd

    RESET = 0xffa07d4f  # field reset button

    TRANSP = 0x00000000
    TRANSP_NOT_0 = 0x00ffffff  # some widgets collapse width if 0 is passed as a color


UiPal = UiPaletteDark


def UiPal_refresh():
    global UiPal
    UiPal = UiPaletteDark






def create_tooltip(text: str,
                   tooltip_style=None,
                   tooltip_text_style=None):

    if tooltip_style is None:
        tooltip_style = {
            "color": UiPal.TOOLTIP_TEXT,
            "background_color": UiPal.TOOLTIP_BACK,
            "margin": -1,
            "border_width": 0,
        }

    if tooltip_text_style is None:
        tooltip_text_style = {"margin": 3}

    with ui.ZStack(style=tooltip_style):
        ui.Rectangle()
        ui.Label(text, style=tooltip_text_style)


def create_tooltip_fn(text: str,
                      tooltip_style=None,
                      tooltip_text_style=None):
    return lambda: create_tooltip(text, tooltip_style, tooltip_text_style)




def create_reset_button(reset_value,
                        widget_model,
                        widget_set_value_fn,
                        widget_add_value_changed_fn,
                        style_on=None,
                        style_off=None,
                        on_tooltip_text=True,  # True: use default, None: no tooltip
                        ) -> ui.Rectangle:

    if style_on is None:
        style_on = {
            "background_color": UiPal.RESET, 
            "border_radius": 2, 
            "color": 0xffffffff
        }

    if style_off is None:
        style_off = {"background_color": UiPal.TEXT_DISABLED}

    if on_tooltip_text is True:
        on_tooltip_text = "Click to reset to default value"


    def update_rect(new_value, *_):
        if type(new_value) is ui.AbstractItemModel:
            new_value = new_value.get_item_value_model()

        if type(reset_value) is bool:
            new_value = new_value.as_bool
        elif type(reset_value) is int:
            new_value = new_value.as_int
        elif type(reset_value) is float:
            new_value = new_value.as_float

        # value changed? display reset button
        rect.visible = new_value != reset_value

    SIZE = 12
    OFF_LEFT_PAD = 3
    OFF_SIZE = 5
    
    with ui.VStack(width=0, style={"margin": 0}):
        ui.Spacer()

        with ui.ZStack(width=SIZE, height=SIZE):

            # disabled reset button
            with ui.HStack(width=SIZE, height=SIZE):

                ui.Spacer(width=OFF_LEFT_PAD)
                with ui.VStack(width=SIZE, height=SIZE):
                    ui.Spacer()
                    ui.Rectangle(width=OFF_SIZE, height=OFF_SIZE, name="reset_off", 
                                 style=style_off)
                    ui.Spacer()

            # actionable reset button
            rect = ui.Rectangle(
                width=SIZE,
                height=SIZE,
                name="reset",
                alignment=ui.Alignment.V_CENTER,
                style=style_on,
                margin=0)

            if on_tooltip_text is not None:
                rect.set_tooltip_fn(create_tooltip_fn(on_tooltip_text))

            rect.set_mouse_pressed_fn(lambda x, y, b, m: widget_set_value_fn(reset_value))

            # initial rect visibility
            update_rect(widget_model)

        ui.Spacer()


    widget_add_value_changed_fn(update_rect)

    return rect

