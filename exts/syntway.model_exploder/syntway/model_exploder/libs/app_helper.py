""""""

import asyncio, functools, sys
import os.path

import carb

import omni.kit



class AppHelper():
    VERSION = 10

    SETTING_TRANSFORM_OP = "/app/transform/operation"


    def __init__(self, attach=True):
        self._app = None

        self._settings = None
        self._setting_changed = {}  # {"setting_path": [subs, set(fn0,fn1,...)], }

        self._input = None

        self._update_event_sub = None
        self._update_event_fns = set()

        self._key_action_subs = {}  # {"action_name": [sub, [(fn0,fn1), (fn1,fn2), ...]] }

        if attach:
            res = self.attach()
            if not res: 
                raise AssertionError("Could not attach")

    def __del__(self):
        self.detach()




    def attach(self) -> bool:

        self.detach()

        self._app = omni.kit.app.get_app()  # omni.kit.app
        self._app_win = omni.appwindow.get_default_app_window()  # omni.appwindow

        self._settings = carb.settings.get_settings()


        return True



    def detach(self):

        self._update_event_sub = None
        self._update_event_fns.clear()

        for v in self._setting_changed.values():
            self._settings.unsubscribe_to_change_events(v[0])

        self._setting_changed = {}
        self._settings = None

        if self._input is not None:
            for v in self._key_action_subs.values():
                self._input.unsubscribe_to_action_events(v[0])

            self._key_action_subs = {}

            self._input = None

        if self._app is not None:
            self._app = None

            


    def add_update_event_fn(self, fn, order=0, subscription_name=None):
        """ 0=NEW_FRAME """

        if self._update_event_sub is None:

            def on_update(ev):
                for fn in self._update_event_fns:
                    fn(ev)

            self._update_event_sub = self._app.get_update_event_stream().create_subscription_to_pop(on_update,
                                                                                                    order=order,
                                                                                                    name=subscription_name)

            self._update_event_fns.clear()

        self._update_event_fns.add(fn)


    def remove_update_event_fn(self, fn, event_type=-1):
        if self._update_event_sub:
            self._update_event_fns.discard(fn)







    def add_setting_changed_fn(self, setting_path, fn):
        """ fn(value, event_type) """

        if not setting_path in self._setting_changed:

            def on_changed(item, event_type):
                fns = self._setting_changed[setting_path][1]
                for fn in fns:
                    fn(str(item), event_type)

            self._setting_changed[setting_path] = [None, set()]
            self._setting_changed[setting_path][0] = self._settings.subscribe_to_node_change_events(setting_path, on_changed)

        s = self._setting_changed[setting_path][1]
        s.add(fn)



    def get_setting(self, setting_path):
        return str( self._settings.get(setting_path) )

    def set_setting(self, setting_path, value):
        self._settings.set(setting_path, value)



    def add_key_action_fn(self, action_name, key, key_modifiers, on_key_fn, is_key_enabled_fn=None):
        """ key_modifiers: 1=shift, 2=ctrl, alt=4"""

        if action_name in self._key_action_subs:
            sub = self._key_action_subs[action_name]
            if not (on_key_fn, is_key_enabled_fn) in sub[1]: # fn pair already there
                sub[1].append((on_key_fn, is_key_enabled_fn))
            return

        if self._input is None:
            self._input = carb.input.acquire_input_interface()

        set_path = self._app_win.get_action_mapping_set_path()
        set = self._input.get_action_mapping_set_by_path(set_path)

        string = carb.input.get_string_from_action_mapping_desc(key, key_modifiers)
        path = set_path + "/" + action_name + "/0"
        self._settings.set_default_string(path, string)

        def on_action(action_name, event, *_):
            if not event.flags & carb.input.BUTTON_FLAG_PRESSED:
                return

            if not action_name in self._key_action_subs:
                return

            try: # avoid keys pressed during camera manipulation
                import omni.kit.viewport_legacy
                vp = omni.kit.viewport_legacy.get_viewport_interface().get_viewport_window()
                if vp.is_manipulating_camera():
                    return
            except Exception:
                pass

            sub = self._key_action_subs[action_name]
            for on_key_fn,is_key_enabled_fn in sub[1]:

                if is_key_enabled_fn is not None:
                    if not is_key_enabled_fn():
                        continue

                on_key_fn()


        sub = [self._input.subscribe_to_action_events(set, action_name, functools.partial(on_action, action_name)),
                [(on_key_fn, is_key_enabled_fn)]]

        self._key_action_subs[action_name] = sub




