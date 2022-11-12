from functools import partial
import asyncio

import omni.ext
import omni.ui as ui
import omni.kit.commands
import carb.settings

from .libs.app_utils import call_on_parts_ready, call_after_update, get_setting_or

from .window import Window
from .engine import Engine
from . import const



class Extension(omni.ext.IExt):

    def on_startup(self, ext_id):
        # print("ext.on_startup", ext_id)
        self._window = None
        self._ext_id = ext_id

        def build():

            ui.Workspace.set_show_window_fn(const.WINDOW_NAME, partial(self.show_window, None))

            # carb.settings.get_settings().set("persistent/exts/syntway.model_exploder/windowShowOnStartup", True)
            show = get_setting_or(const.SETTINGS_PATH + "windowShowOnStartup", False)

            ed_menu = omni.kit.ui.get_editor_menu()
            if ed_menu:
                self._menu = ed_menu.add_item(const.MENU_PATH, self.show_window, toggle=True, value=show)

            if show:
                self.show_window(None, True)  # ui.Workspace.show_window(WINDOW_NAME)


        call_on_parts_ready(build, 1)  # stage ready



    def on_shutdown(self):
        # print("ext.on_shutdown")
        ui.Workspace.set_show_window_fn(const.WINDOW_NAME, None)

        ed_menu = omni.kit.ui.get_editor_menu()
        if ed_menu:
            ed_menu.remove_item(const.MENU_PATH)

        self._menu = None

        if self._window:
            self._window.destroy(True)
            self._window = None




    def show_window(self, menu, value):
        # print("ext.show_window", value, self._window)

        if value:  # show
            #assert self._window is None, "self._window should be None"

            if self._window is None:
                self._window = Window(const.WINDOW_NAME, self._ext_id)
                self._window.set_visibility_changed_fn(self._visibility_changed_fn)
            else:
                self._window.show()

        elif self._window:
            self._window.visible = False  # will destroy in _visibility_changed_fn



    def _set_menu(self, value):
        # print("ext._set_menu", value)
        ed_menu = omni.kit.ui.get_editor_menu()
        if ed_menu:
            ed_menu.set_value(const.MENU_PATH, value)



    def _visibility_changed_fn(self, visible):
        # print("ext._visibility_changed_fn", visible)
        self._set_menu(visible)

        if not visible:  # destroy window

            def destroy_window():
                # print("ext.destroy_window", self._window)

                if self._window:
                    self._window.destroy(False)
                    self._window = None

            call_after_update(destroy_window)




class ExplodeEngineApplyCommand(omni.kit.commands.Command):
    """
    Undo/redoable command used by engine to apply final and initial position lists
    Don't use outside this extension.

    states are a tuple of (dist, change_list, time_code)
    """

    def __init__(self, initial_state, final_state, stage):
        super().__init__()

        self._initial_state = initial_state
        self._final_state = final_state
        self._stage = stage

    def do(self):
        Engine.apply_state(self._final_state, self._stage, None)

    def undo(self):
        Engine.apply_state(self._initial_state, self._stage, None)



omni.kit.commands.register_all_commands_in_module(__name__)
