""""""

import asyncio, functools, sys
import os.path

import carb

import omni.kit
import omni.kit.viewport.utility as vut
import omni.ui as ui
import omni.usd

from pxr import Gf, Tf, Sdf, Usd, UsdGeom, CameraUtil


VERSION = 10


def call_after_update(fn, update_count=1):

    async def wait_for_update(count):
        while count:
            await omni.kit.app.get_app().next_update_async()
            count -= 1
        fn()

    asyncio.ensure_future(wait_for_update(update_count))


def call_on_ready(is_ready_fn, on_ready_fn, max_tries=sys.maxsize):

    async def wait_for():
        nonlocal max_tries

        while max_tries:
            await omni.kit.app.get_app().next_update_async()

            if is_ready_fn():
                on_ready_fn()
                return

            max_tries -= 1

    if is_ready_fn():  # straight away?
        on_ready_fn()
        return
    else:
        asyncio.ensure_future(wait_for())






def call_on_parts_ready(on_ready_fn, part_flags=1 | 2 | 4, 
                        max_tries=sys.maxsize,
                        usd_context=None, usd_context_name='',
                        window_name: str = None, 
                        ):
    """Call back when all parts in part_flags are ready:
    part_flags:
        Stage ready=1
        Stage camera ready=2 -> implies stage ready
        Viewport non-zero frame size=4    
    """

    def are_parts_ready():
        ready_mask = 0


        if part_flags & (1 | 2 | 4):
            api, win = vut.get_active_viewport_and_window(usd_context_name=usd_context_name, 
                                                          window_name=window_name)


        if part_flags & (1 | 2):
            if usd_context is None:
                ctx = omni.usd.get_context()
            else:
                ctx = usd_context
            if not ctx:
                return False
            
            stage = ctx.get_stage()
            if not stage:
                return False

            cam_prim = stage.GetPrimAtPath(api.camera_path)
            ready_mask = 1 | (2 if cam_prim.IsValid() else 0)


        if part_flags & 4:
            if not win:
                return False

            ws_win = ui.Workspace.get_window(win.name)
            if not ws_win:
                return False

            if not hasattr(ws_win, 'frame'):
                return False
                
            ws_win_frame = ws_win.frame

            if ws_win_frame.computed_width > 0 and ws_win_frame.computed_height > 0:
                ready_mask |= 4
        
        return part_flags & ready_mask == part_flags


    call_on_ready(are_parts_ready, on_ready_fn, max_tries)



# convenience calls
def call_on_stage_ready(on_ready_fn, usd_context=None, max_tries=sys.maxsize):
    call_on_parts_ready(on_ready_fn, 1, usd_context=usd_context, max_tries=max_tries)

def call_on_stage_camera_ready(on_ready_fn, 
                               usd_context=None, usd_context_name='',
                               window_name: str = None, 
                               max_tries=sys.maxsize):
    call_on_parts_ready(on_ready_fn, 1 | 2,
                        usd_context=usd_context, usd_context_name=usd_context_name, 
                        window_name=window_name, max_tries=max_tries)






def get_setting_or(path, not_found_value):
    value = carb.settings.get_settings().get(path)
    if value is not None:
        return value
    else:
        return not_found_value


def set_setting(path, value):
    carb.settings.get_settings().set(path, value)



def get_extension_path(ext_id, sub_path=None):
    ext_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
    if sub_path is not None:
        return os.path.join(ext_path, sub_path)
    else:
        return ext_path
    

def matrix44_flatten(mat):
    """Get a omni.ui.scene.Matrix44 (an array[16]) from a pxr.Gf.Matrix4d or array[4][4]."""
    return [mat[0][0], mat[0][1], mat[0][2], mat[0][3],
            mat[1][0], mat[1][1], mat[1][2], mat[1][3],
            mat[2][0], mat[2][1], mat[2][2], mat[2][3],
            mat[3][0], mat[3][1], mat[3][2], mat[3][3]]
