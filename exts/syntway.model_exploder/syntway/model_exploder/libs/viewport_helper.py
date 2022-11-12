"""
+ Coordinate spaces:
- 2D screen coordinate spaces
    ui: whole frame area float UI units, only equal to px units when omni.ui.Workspace.get_dpi_scale() is 1. ui = px_units / dpi_scale.
        Origin is left-top corner of the frame, 0..ui_size().
        (app_ui = ui coordinates in Kit's app coordinates, window left-top is the origin.)
        (px: whole frame area integer screen monitor pixels, 0..px_size(). Use ui coords instead for units to scale in high density displays)

    01: float 0..1 coordinates covering whole frame area. Origin is left-top corner.

    ndc: float -1..+1 Normalized Device Coordinates covering whole frame area. Origin is center, 1,1 is top-right corner of frame.

    iscene: coordinates in a SceneView with view and projection transforms both set to identity matrices. 
            Origin is center, +x,+y is right-top corner. Can span -xy..+xy, where xy=iscene_half(). 
            Fixed aspect ratio: a size displays at the same length in x and y.

    render: area where rendering displays with size fitted to frame area, which can occupy whole or only a part. 
            NDC coords always extend -1..+1, origin is the center, 1,1 is top-right corner of frame.

- 3D world space
    world: world space 3D coordinates


+ Coordinate/size conversions:
- 2D screen spaces
conv_iscene_from_render
conv_iscene_from_ndc
conv_iscene_from_01
conv_iscene_from_ui
size_iscene_from_ui

conv_render_from_ndc <-> conv_ndc_from_render

conv_01_from_ui <-> conv_ui_from_01
conv_ndc_from_ui <-> conv_ui_from_ndc
conv_01_from_app_ui, conv_ndc_from_app_ui, conv_ui_from_app_ui

conv_ndc_from_01 <-> conv_01_from_ndc

- 3D <-> 2D spaces
conv_render_from_world
conv_iscene_from_world
pick_ray_from_render

All conv_* methods accept points in Gf.Vec2*/Gf.Vec3* or tuple, but always return Gf.Vec2d/Gf.Vec3d points.

+ SceneView transformations
get_transform_iscene_from_ui
get_transform_iscene_from_render



+ Legacy Viewport:
Extension omni.kit.viewport_legacy (was omni.kit.window.viewport)
_win -> class omni.kit.viewport.utility.legacy_viewport_window.LegacyViewportWindow -> omni.ui.Window
_api -> class omni.kit.viewport.utility.legacy_viewport_api.LegacyViewportAPI

Use _win.legacy_window to get the actual IViewportWindow ->
    class omni.kit.viewport_legacy._viewport_legacy.IViewportWindow

    set_enabled_picking(), get_mouse_event_stream(), etc

+ Viewport Next
Partially supported. Extensions omni.kit.viewport.window, omni.kit.widget.viewport

+ Notes

- Don't store and always access ViewportHelper's frame or render area sizes as they may change due to user interactions,
even when changing Kit between display monitors.
"""


import asyncio, functools

import carb

import omni.kit
import omni.kit.viewport.utility as vut
import omni.ui as ui

""" Since omni.ui.scene may not not available on Kit's early launch,
if you're launch time errors related with omni.ui.scene, add omni.ui.scene
to your extension dependencies in extension.toml:
[dependencies]
"omni.ui.scene" = {} """
from omni.ui import scene as sc

from pxr import Gf, Tf, Sdf, Usd, UsdGeom, CameraUtil

SETTING_RENDER_WIDTH = "/app/renderer/resolution/width"
SETTING_RENDER_HEIGHT = "/app/renderer/resolution/height"
SETTING_CONFORM_POLICY = "/app/hydra/aperture/conform"
SETTING_RENDER_FILL_LEGACY = "/app/runLoops/rendering_0/fillResolution"
SETTING_RENDER_FILL = "/persistent/app/viewport/{api_id}/fillViewport"
SETTING_DEFAULT_WINDOW_NAME = "/exts/omni.kit.viewport.window/startup/windowName"


class ViewportHelper():
    LIB_VERSION = 45

    def __init__(self, window_name=None, attach: bool = True):
        self._win = None
        self._api = None
        self._ws_win_frame = None

        self._sub_render_width = None
        self._sub_render_height = None
        self._sub_render_fill = None

        self._is_legacy = True

        self._frame_mouse_fns = {}  # frame: set(fn,fn,...)

        self._frame_size_changed_fns = {}  # frame: set(fn,fn,...)
        self._render_changed_fns = set()  # set(fn,fn,...)
        self._stage_objects_changed = None  # [listener, set(fn,fn,...)]

        self._changed_fns = {}  # fn: sub_flags

        if attach:
            res = self.attach(window_name=window_name)
            if not res: 
                raise AssertionError("Could not attach")


    def __del__(self):
        self.detach()




    def attach(self, window_name=None, usd_context_name: str = '') -> bool:
        """ window_name:
            str: actual window name/title, like "Viewport"
            None: current/last active viewport
            int: index into ViewportHelper.get_window_names()

        Window selection order: .get_active_viewport_and_window() vut tries to attach "Viewport Next" first,
        then legacy "Viewport" windows."""

        self.detach()

        if window_name is not None:
            if type(window_name) is int:
                wn_list = ViewportHelper.get_window_names()
                if window_name < len(wn_list):
                    window_name = wn_list[window_name]
                else:
                    raise AssertionError("Non-existent window_name")
            else:
                raise AssertionError("Bad window_name index")


        self._api,self._win = vut.get_active_viewport_and_window(usd_context_name=usd_context_name,
                                                                 window_name=window_name)

        if self._win is None or self._api is None:
            self._win = None
            self._api = None
            self._ws_win = None
            self._ws_win_frame = None
            return False

        if self.stage is None:
             raise AssertionError("Stage not available")

        self._is_legacy = hasattr(self._api, "legacy_window")

        self._ws_win = ui.Workspace.get_window(self._win.name)
        if self._ws_win is None:
            raise AssertionError("Workspace window not available")

        """
        if not self._ws_win.visible:
            print("Viewport Window is not visible: can't attach")
            self.detach()
            return False
        """

        if not hasattr(self._ws_win, 'frame'):
            self._ws_win_frame = None
            raise AssertionError("Workspace window frame not available")

        self._ws_win_frame = self._ws_win.frame

        return True



    def detach(self):
        settings = carb.settings.get_settings()
        if self._sub_render_width: 
            settings.unsubscribe_to_change_events(self._sub_render_width)
            self._sub_render_width = None
        if self._sub_render_height: 
            settings.unsubscribe_to_change_events(self._sub_render_height)
            self._sub_render_height = None
        if self._sub_render_fill: 
            settings.unsubscribe_to_change_events(self._sub_render_fill)
            self._sub_render_fill = None

        if self._win is not None:
            if self._is_legacy:
                self._win.destroy()
            self._win = None

        self._api = None
        self._ws_win = None
        self._ws_win_frame = None

        self._frame_mouse_fns.clear()
        self._frame_size_changed_fns.clear()
        self._render_changed_fns.clear()
        self._changed_fns.clear()

        if self._stage_objects_changed is not None:
            if len(self._stage_objects_changed):
                self._stage_objects_changed[0].Revoke()
            self._stage_objects_changed = None

    @property
    def is_attached(self):
        return self._win is not None


    @property
    def window_name(self) -> str:
        return self._win.name

    @staticmethod
    def get_default_window_name():
        return carb.settings.get_settings().get(SETTING_DEFAULT_WINDOW_NAME) or 'Viewport'

    @staticmethod
    def get_window_names():
        try:
            from omni.kit.viewport.window import get_viewport_window_instances
            return [w.title for w in get_viewport_window_instances()]
        except ImportError:
            return [ViewportHelper.get_default_window_name()]

    @property
    def is_legacy(self):
        return self._is_legacy

    @property
    def camera_path(self) -> Sdf.Path:
        return self._api.camera_path

    @camera_path.setter
    def camera_path(self, camera_path):
        self._api.camera_path = camera_path


    def get_camera_view_proj(self):
        frustum = self.get_conformed_frustum()
        if frustum is None:
            return None
        return frustum.ComputeViewMatrix(), frustum.ComputeProjectionMatrix()


    def same_api(self, api) -> bool:
        return id(api) == id(self._api)


    def get_gf_camera(self):
        """Returns None if no valid prim found."""

        cam = self._api.camera_path

        stage = self.stage
        if stage is None:
             raise AssertionError("Stage not available")

        cam_prim = stage.GetPrimAtPath( self.camera_path )
        if cam_prim and cam_prim.IsValid():
            usd_cam = UsdGeom.Camera(cam_prim)
            if usd_cam:
                return usd_cam.GetCamera()

        # fall over
        return None



    @property
    def fps(self) -> float:
        return self._api.fps


    @property
    def usd_context_name(self) -> str:
        return self._api.usd_context_name

    @property
    def usd_context(self):
        return self._api.usd_context


    @property
    def stage(self):
        return self.usd_context.get_stage()


    def get_frame(self, frame_id: str):
        return self._win.get_frame(frame_id)




    @property
    def ui_size(self):
        """ Due to DPI pixel multiplier, can return fractional. 
        In DPI > 1 displays, this is UI units. Actual display pixels = UI units * omni.ui.Workspace.get_dpi_scale() """
        if self._ws_win_frame is not None:
            return self._ws_win_frame.computed_width, self._ws_win_frame.computed_height
        else:
            return 1.,1.

    @property
    def px_size(self):
        """ Returns int size """
        ui_size = self.ui_size
        dpi_mult = ui.Workspace.get_dpi_scale()
        return int(round(ui_size[0] * dpi_mult)), int(round(ui_size[1] * dpi_mult))

    @property
    def ui_size_ratio(self):
        size = self.ui_size
        return size[0] / size[1] if size[1] else 1.


    @property
    def render_size_px(self):
        size = self._api.resolution
        return (int(size[0]), int(size[1]))

    @render_size_px.setter
    def render_size_px(self, size):
        self._api.resolution = (int(size[0]), int(size[1]))

    # render_size width/height ratio
    @property
    def render_size_ratio(self):
        size = self.render_size_px
        return size[0] / size[1] if size[1] else 1.

    """ ?Also render_rect_px, render_left_top_px """




    """
    Kit-103.1.2/3: render_fill_frame get/set does not work coherently
        Legacy Viewport: setting fill_frame makes viewport settings "Fill Viewport" disappear
        Viewport 2: only works setting to True
    Kit 104.0:
        Viewport 2: api is not initialized to setting: so we use setting

    @property
    def render_fill_frame(self):
        return self._api.fill_frame

    @render_fill_frame.setter
    def render_fill_frame(self, value: bool):
        self._api.fill_frame = value
    """

    @property
    def render_fill_frame(self):        
        if self._is_legacy:
            name = SETTING_RENDER_FILL_LEGACY
        else:
            name = SETTING_RENDER_FILL.format(api_id=self._api.id)
        return bool(carb.settings.get_settings().get(name))


    @render_fill_frame.setter
    def render_fill_frame(self, value: bool):
        if self._is_legacy:
            name = SETTING_RENDER_FILL_LEGACY
        else:
            name = SETTING_RENDER_FILL.format(api_id=self._api.id)
        carb.settings.get_settings().set(name, value)



    def get_conformed_frustum(self):

        cam = self.get_gf_camera()
        if cam is None:
             raise AssertionError("Camera not available")

        frustum = cam.frustum

        conform_policy = ViewportHelper.get_conform_policy()

        CameraUtil.ConformWindow(frustum, conform_policy, self.render_size_ratio)

        return frustum
 


    @staticmethod
    def get_conform_policy():
        """conform_policy: how is the render area fit into the frame area"""

        policy = carb.settings.get_settings().get(SETTING_CONFORM_POLICY)
        
        if policy is None or policy < 0 or policy > 5:
            return CameraUtil.MatchHorizontally
        else:
            policies = [
                CameraUtil.MatchVertically,
                CameraUtil.MatchHorizontally,
                CameraUtil.Fit,
                CameraUtil.Crop,
                CameraUtil.DontConform,
                CameraUtil.DontConform,
            ]

        return policies[policy]




    def sync_scene_view(self, scene_view):
        """Must be called after viewport changes or before using a SceneView.
        A SceneView's "screen_aspect_ratio" is the ratio of what we call the render space"""

        frame_ratio = self.ui_size_ratio
        render_ratio = self.render_size_ratio
        if False and abs(frame_ratio - render_ratio) < 1e-6: # render equal to frame area: set to 0
            ratio = 0
        else:
            ratio = render_ratio

        if scene_view.screen_aspect_ratio != ratio:
            scene_view.screen_aspect_ratio = ratio

        # print("setup_scene_view asp_rat", scene_view.screen_aspect_ratio)







    #====================================================================== coord space conversion

    # generic NDC <-> 0..1 conversion
    @staticmethod
    def conv_ndc_from_01(coord):
        return Gf.Vec2d( coord[0]*2. - 1., -(coord[1]*2. - 1.) )
    @staticmethod
    def conv_01_from_ndc(coord):
        return Gf.Vec2d( (coord[0] + 1.) * 0.5, (-coord[1] + 1.) * 0.5)


    def conv_01_from_ui(self, coord):
        width,height = self.ui_size
        return Gf.Vec2d(coord[0] / width, coord[1] / height)
    def conv_ui_from_01(self, coord):
        width,height = self.ui_size
        return Gf.Vec2d(coord[0] * width, coord[1] * height)

    def conv_ui_from_app_ui(self, coord):
        frame = self._win.frame
        return Gf.Vec2d(coord[0] - frame.screen_position_x, coord[1] - frame.screen_position_y)

    def conv_01_from_app_ui(self, coord):
        frame = self._win.frame
        return self.conv_01_from_ui( (coord[0] - frame.screen_position_x, coord[1] - frame.screen_position_y) )


    def conv_ndc_from_ui(self, coord):
        xy = self.conv_01_from_ui(coord)
        return ViewportHelper.conv_ndc_from_01(xy)
    def conv_ui_from_ndc(self, coord):
        xy = ViewportHelper.conv_01_from_ndc(xy)
        return ViewportHelper.conv_ui_from_01(xy)


    def conv_ndc_from_app_ui(self, coord):
        xy = self.conv_01_from_app_ui(coord)
        return ViewportHelper.conv_ndc_from_01(xy)



    @property
    def _render_from_size_ratios(self):
        fr = self.ui_size

        frame_ratio = fr[0] / fr[1] if fr[1] else 1.
        render_ratio = self.render_size_ratio

        if frame_ratio >= render_ratio: # tex vertical -1..+1
            return (frame_ratio / render_ratio, 1.)
        else: # 
            return (1., render_ratio / frame_ratio)

    # coordinate conversion between frame-NDC and render(NDC) spaces
    def conv_render_from_ndc(self, frame_ndc):
        mx = frame_ndc[0]
        my = frame_ndc[1]

        ratios = self._render_from_size_ratios
        mx *= ratios[0]
        my *= ratios[1]

        return Gf.Vec2d(mx, my)
        
    def conv_ndc_from_render(self, render_ndc):
        mx,my = self.conv_render_from_ndc(render_ndc)
        return Gf.Vec2d(1./mx, 1./my)




    def iscene_size(self, scene_view):
        w,h = self.iscene_half(scene_view)
        return w*2.,h*2.


    def iscene_half(self, scene_view):
        frame_ratio = self.ui_size_ratio
        render_ratio = self.render_size_ratio
        fills = abs(frame_ratio - render_ratio) < 1e-6
        lands = frame_ratio >= render_ratio

        asp_rat = scene_view.aspect_ratio_policy

        # print("fills,lands", fills, lands, frame_ratio, render_ratio)
        if asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_FIT:
            if fills and frame_ratio < 1:
                 mul = 1.,1./frame_ratio
            elif lands:
                mul = frame_ratio,1.
            else:
                mul = render_ratio,render_ratio/frame_ratio

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_HORIZONTAL:
            if lands:
                mul = frame_ratio/render_ratio,1./render_ratio
            else:
                mul = 1.,1./frame_ratio

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_VERTICAL:
            if lands:
                mul = frame_ratio,1.
            else:
                mul = render_ratio,render_ratio/frame_ratio

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_CROP:
            if fills and frame_ratio < 1:
                mul=frame_ratio,1.
            elif lands:
                mul = frame_ratio/render_ratio,1./render_ratio
            elif frame_ratio >= 1:
                mul = 1.,1./frame_ratio
            else:
                mul = 1,1./frame_ratio

        elif asp_rat == sc.AspectRatioPolicy.STRETCH:
            if frame_ratio >= 1:
                mul = frame_ratio,1.
            else:
                mul = 1,1./frame_ratio
            
        else:
            mul = 1.,1.

        return mul


    def iscene_render_half(self, scene_view):
        """Render half size expressed in iscene coords"""
        frame_ratio = self.ui_size_ratio
        render_ratio = self.render_size_ratio
        fills = abs(frame_ratio - render_ratio) < 1e-6
        lands = frame_ratio >= render_ratio

        asp_rat = scene_view.aspect_ratio_policy

        if asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_FIT:
            if fills and frame_ratio < 1:
                mul = 1.,1./frame_ratio
            else:
                mul = render_ratio,1.

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_HORIZONTAL:
            mul = 1.,1./render_ratio

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_VERTICAL:
            mul = render_ratio,1.

        elif asp_rat == sc.AspectRatioPolicy.PRESERVE_ASPECT_CROP:
            if fills and frame_ratio < 1:
                mul=frame_ratio,1.
            else:
                mul = 1.,1./render_ratio

        elif asp_rat == sc.AspectRatioPolicy.STRETCH:
            if fills and frame_ratio < 1:
                mul = 1.,1./render_ratio
            elif lands:
                mul = render_ratio,1.
            elif frame_ratio >= 1:
                mul = frame_ratio,frame_ratio/render_ratio
            else:
                mul = 1.,1./render_ratio

        else:
            mul = 1.,1.

        return mul



    def conv_iscene_from_render(self, render_pt, scene_view):
        mul = self.iscene_render_half(scene_view)
        return Gf.Vec2d(render_pt[0] * mul[0], render_pt[1] * mul[1])



    def conv_iscene_from_01(self, ui01, scene_view):
        size = self.ui_size
        pt = ViewportHelper.conv_ndc_from_01(ui01)
        mul = self.iscene_half(scene_view)
        return Gf.Vec2d(pt[0] * mul[0], pt[1] * mul[1])

    def conv_iscene_from_ndc(self, ndc, scene_view):
        mul = self.iscene_half(scene_view)
        return Gf.Vec2d(ndc[0] * mul[0], ndc[1] * mul[1])


    def conv_iscene_from_ui(self, ui_pt, scene_view):
        size = self.ui_size
        pt = ui_pt[0] / size[0] * 2. - 1., ui_pt[1] / size[1] * 2. - 1. # pt now in NDC
        mul = self.iscene_half(scene_view)
        return Gf.Vec2d(pt[0] * mul[0], pt[1] * mul[1])


    def size_iscene_from_ui(self, ui_size, scene_view):
        size = self.ui_size

        ui_sz = 2. * ui_size / size[0]
        mul = self.iscene_half(scene_view)

        return ui_sz * mul[0]







    def get_transform_iscene_from_ui(self, scene_view):
        size_ui = self.ui_size
        iscene_half = self.iscene_half(scene_view)
        return sc.Matrix44.get_scale_matrix(iscene_half[0], iscene_half[1], 1.) * \
               sc.Matrix44.get_translation_matrix(-1., +1., 0) * \
               sc.Matrix44.get_scale_matrix(2./size_ui[0], -2./size_ui[1], 1.)


    def get_transform_iscene_from_render(self, scene_view):
        iscene_render_half = self.iscene_render_half(scene_view)
        return sc.Matrix44.get_scale_matrix(iscene_render_half[0], iscene_render_half[1], 1.)



    #====================================================================== 3D world <-> 2D screen conversion

    def pick_ray_from_render(self, render_ndc, frustum=None):

        if frustum is None:
            frustum = self.get_conformed_frustum()

        pos = Gf.Vec2d(render_ndc[0],render_ndc[1])
        return frustum.ComputePickRay(pos)
        """
        From frame space NDC coords example:
        x,y = self.conv_render_from_ndc(frame_ndc)
        if x is None or x < -1.0 or x > 1.0 or y < -1.0 or y > 1.0:
            return None
        return get_pick_ray((x,y))
        """


    def conv_render_from_world(self, wpt):
        """ wpt can be Gd.Vec3*, (x,y,z), single value or list
        returns Gf.Vec2d, single value or list NDC coords
        """
        view,proj = self.get_camera_view_proj()
        mat = view*proj

        if isinstance(wpt, list):
            wpt_list=wpt
        else:
            wpt_list=[wpt]

        rpt = []
        for pt in wpt_list:
            r = mat.Transform( Gf.Vec3d(pt[0],pt[1],pt[2]) )
            rpt.append(r)

        if isinstance(wpt, list):
            return rpt
        else:
            return rpt[0]



    def conv_iscene_from_world(self, wpt, scene_view):
        """ wpt can be Gd.Vec3*, (x,y,z) or list. Not single value.
        returns Gf.Vec2d, single value or list NDC coords
        """
        view,proj = self.get_camera_view_proj()
        mat = view*proj

        if isinstance(wpt, list):
            wpt_list=wpt
        else:
            wpt_list=[wpt]

        mul = self.iscene_render_half(scene_view)

        spt = []
        for pt in wpt_list:
            r = mat.Transform( Gf.Vec3d(pt[0],pt[1],pt[2]) )
            s = Gf.Vec2d(r[0] * mul[0], r[1] * mul[1])
            spt.append(s)

        if isinstance(wpt, list):
            return spt
        else:
            return spt[0]








    def add_frame_mouse_fn(self, frame, fn, coord_space=0):
        """Called function params:
        op:
            0=press
            1=move
            2=release
            3=double click
            4=mouse wheel
            5=mouse hovered (entered) frame
        
        x,y: coordinates inside frame, depending on coord_space: 
            0=01 space
            1=ui space
            2=ndc space
            3=render space
        
        button:
            0=left
            1=right
            2=middle

        mod flags:
            1=shift
            2=ctrl
            4=alt
            (6=altGr = ctrl + alt)
            0x40000000=unknown during move and release
        
        """

        if not frame in self._frame_mouse_fns:
            self._frame_mouse_fns[frame] = set()

        fnlist = self._frame_mouse_fns[frame]
        if fn in fnlist:
            return

        fnlist.add(fn)

        last_button_pressed = None

        def dispatch(op, x,y, button, mod):
            for fn in fnlist:
                fn(op, x,y, button, mod)

        def to_space(x,y):
            if coord_space <= 1:
                p01 = self.conv_01_from_app_ui((x,y))
                if coord_space == 0:
                    return p01
                else:
                    return self.conv_ui_from_01(p01)
            else:
                pndc = self.conv_ndc_from_app_ui((x,y))
                if coord_space == 2:
                    return pndc
                else:
                    return self.conv_render_from_ndc(pndc)

        def on_mouse_pressed(x,y, button, mod):
            nonlocal last_button_pressed
            x,y = to_space(x,y)
            dispatch(0, x,y, button, mod)
            last_button_pressed = button

        def on_mouse_moved(x,y, mod, unknown_always_true): #on move: x,y can go outside 0,1
            x,y = to_space(x,y)
            dispatch(1, x,y, last_button_pressed, mod)

        def on_mouse_released(x,y, button, mod):
            nonlocal last_button_pressed
            x,y = to_space(x,y)
            dispatch(2, x,y, button, mod)
            last_button_pressed = None

        def on_mouse_double_clicked(x,y, button, mod):
            x,y = to_space(x,y)
            dispatch(3, x,y, button, mod)

        def on_mouse_wheel(x,y, mod):
            dispatch(4, x,y, None, mod)

        def on_mouse_hovered(entered): # x=entered info
            dispatch(5, entered, None, None, None)

        frame.set_mouse_pressed_fn(on_mouse_pressed)
        frame.set_mouse_moved_fn(on_mouse_moved)
        frame.set_mouse_released_fn(on_mouse_released)

        frame.set_mouse_double_clicked_fn(on_mouse_double_clicked)
        frame.set_mouse_wheel_fn(on_mouse_wheel)
        frame.set_mouse_hovered_fn(on_mouse_hovered)





    def add_frame_size_changed_fn(self, frame, fn):

        if not frame in self._frame_size_changed_fns:

            def on_frame_size_changed():
                if not frame in self._frame_size_changed_fns:
                    return

                for fn in self._frame_size_changed_fns[frame]:
                    fn()

            frame.set_computed_content_size_changed_fn( on_frame_size_changed )
            self._frame_size_changed_fns[frame] = set()


        fnlist = self._frame_size_changed_fns[frame]
        fnlist.add( fn )


    def remove_frame_size_changed_fn(self, frame, fn):
        if frame in self._frame_size_changed_fns:
            fnlist = self._frame_size_changed_fns[frame]
            fnlist.discard( fn )






    def add_render_changed_fn(self, fn):
        """Call fn handler on render resolution or fill mode changed"""

        if self._sub_render_width is None:

            def on_render_changed(*args):
                """ will render resolution/frame_fill take a frame to reflect """

                async def async_func():
                    await omni.kit.app.get_app().next_update_async()

                    for fn in self._render_changed_fns:
                        fn()

                asyncio.ensure_future( async_func() )


            settings = carb.settings.get_settings()
            self._sub_render_width = settings.subscribe_to_node_change_events(SETTING_RENDER_WIDTH, on_render_changed)
            self._sub_render_height = settings.subscribe_to_node_change_events(SETTING_RENDER_HEIGHT, on_render_changed)
            self._sub_render_fill = settings.subscribe_to_node_change_events(SETTING_RENDER_FILL, on_render_changed)

        self._render_changed_fns.add(fn)


    def remove_render_changed_fn(self, fn):
        if self._sub_render_width is not None:
            self._render_changed_fns.discard(fn)








    def add_camera_changed_fn(self, fn):
        """Call fn handler when USD camera changes"""

        if self._stage_objects_changed is None:
            # handler needs to be a method as Register won't hold reference to a local function
            listener = Tf.Notice.Register( Usd.Notice.ObjectsChanged, self._on_stage_objects_changed, self.stage)

            self._stage_objects_changed = [listener, set()]

        val = self._stage_objects_changed
        val[1].add(fn)

    def _on_stage_objects_changed(self, notice, stage):
        if stage != self.stage or self._stage_objects_changed is None:
            return

        # did active camera change?
        cam_path = self.camera_path

        for n in notice.GetChangedInfoOnlyPaths():            
            if n.GetPrimPath() == cam_path: # found camera

                for fn in self._stage_objects_changed[1]:
                    fn()

                return

    def remove_camera_changed_fn(self, fn):
        if self._stage_objects_changed is not None:
            val = self._stage_objects_changed
            val[1].discard(fn)




    def add_changed_fn(self, fn, sub_flags = 1|2|4, frame = None):
        """Call handler on frame, render or camera changes, depending on sub_flags mask.
        sub_flags: 1=frame size changed (requires frame param), 2=render changed, 4=camera changed
        fn(changed_flag)        
        """

        self._changed_fns[fn] = sub_flags #overwrite any existing for fn

        # add everytime because functions avoid duplicates: but only if not using lambdas!
        if sub_flags & 1:
            if frame is None:
                raise AssertionError("Frame size changed: frame parameter cannot be None")
            self.add_frame_size_changed_fn(frame, self._on_frame_changed)

        if sub_flags & 2:
            self.add_render_changed_fn(self._on_render_changed)

        if sub_flags & 4:
            self.add_camera_changed_fn(self._on_camera_changed)

    def _on_frame_changed(self):
        self._on_changed(1)
    def _on_render_changed(self):
        self._on_changed(2)
    def _on_camera_changed(self):
        self._on_changed(4)

    def _on_changed(self, changed_flag):
        for fn, mask in self._changed_fns.items():
            if mask & changed_flag:
                fn(changed_flag)


    def remove_changed_fn(self, fn, frame):
        if fn in self._changed_fns:
            if self._changed_fns[fn] & 1 and frame is None:
                raise AssertionError("Frame size changed: frame parameter cannot be None")
            del self._changed_fns[fn]

        if not len(self._changed_fns):
            if frame is not None:
                self.remove_frame_size_changed_fn(frame, self._on_frame_changed)
            self.remove_render_changed_fn(self._on_render_changed)
            self.remove_camera_changed_fn(self._on_camera_changed)
            




















    def add_scene_view_update(self, scene_view):
        self._api.add_scene_view(scene_view)

    def remove_scene_view_update(self, scene_view):
        self._api.remove_scene_view(scene_view)






    def register_scene(self, scene_creator,
                       ext_id_or_name: str):
        """Registers a scene creator into:
            VP1: a viewport window, where scene is immediately created
            VP2: calls RegisterScene with omni.kit.viewport.registry, to create scene in 
                 current (full window) viewports and any new ones.

                 scene_creator object created with: scene_creator_class(dict)
                    VP1 dict = {viewport_api}
                    VP2 dict = {viewport_api: omni.kit.viewport.window.ViewportAPI, 
                                layer_provider: omni.kit.viewport.window.ViewportLayers, 
                                usd_context_name: str}
        """

        if self.is_legacy:
            with self._win.get_frame(ext_id_or_name):
                scene_view = sc.SceneView()
                with scene_view.scene:
                    sce = scene_creator({"viewport_api": self._api})
        
                # have viewport update our SceneView
                self.add_scene_view_update(scene_view)

                return [scene_view, sce]

        else:
            try:
                from omni.kit.viewport.registry import RegisterScene
                scene_reg = RegisterScene(scene_creator, ext_id_or_name)
                return [scene_reg]

            except ImportError:
                return None


    def register_scene_proxy(self, create_fn, destroy_fn, get_visible_fn, set_visible_fn,
                            ext_id_or_name: str):
        lamb = ViewportHelper.SceneCreatorProxy.make_lambda(create_fn, destroy_fn, get_visible_fn, set_visible_fn)
        return self.register_scene(lamb, ext_id_or_name)




    def unregister_scene(self, scene_reg):
        if scene_reg is None or not len(scene_reg):
            return

        if self.is_legacy:
            scene_view = scene_reg[0]
            self.remove_scene_view_update(scene_view)
            scene_view.destroy()

        scene_reg.clear()           





    class SceneCreatorProxy:
        @staticmethod
        def make_lambda(create_fn, destroy_fn, get_visible_fn, set_visible_fn):
            return lambda vp_args: ViewportHelper.SceneCreatorProxy(vp_args, create_fn, destroy_fn, get_visible_fn, set_visible_fn)

        def __init__(self, vp_args: dict, 
                     create_fn, destroy_fn, get_visible_fn, set_visible_fn):
            # print("SceneCreatorProxy.__init__", vp_args)
            # dict_keys(['usd_context_name', 'layer_provider', 'viewport_api'])
            """@ATTN: a scene may be created in multiple viewports. It's up to the _create_fn() callee to make sure it's 
            being called in the intended viewport by checking vp_args['viewport_api']"""

            self._create_fn = create_fn
            self._destroy_fn = destroy_fn
            self._get_visible_fn = get_visible_fn
            self._set_visible_fn = set_visible_fn

            self._create_fn(vp_args)

        def destroy(self):
            # print("SceneCreatorProxy.destroy")
            if self._destroy_fn:
                self._destroy_fn()

            self._create_fn = None
            self._destroy_fn = None
            self._get_visible_fn = None
            self._set_visible_fn = None


        def __del__(self):
            self.destroy()

        # called from viewport registry
        @property
        def visible(self):
            # print("SceneCreatorProxy.get_visible")

            if self._get_visible_fn:
                return self._get_visible_fn()
            else:
                return True

        @visible.setter
        def visible(self, value: bool):
            # print("SceneCreatorProxy.set_visible", value)

            if self._set_visible_fn:
                return self._set_visible_fn(value)
















    @property
    def picking_enabled(self):
        """Object picking and selection rect."""
        if self._is_legacy:
            self._win.legacy_window.is_enabled_picking()
        else:
            # print("picking_enabled only supported for legacy viewport")
            return True

    @picking_enabled.setter
    def picking_enabled(self, enabled):
        """Disables object picking and selection rect."""
        if self._is_legacy:
            self._win.legacy_window.set_enabled_picking(enabled)
        else:
            # print("picking_enabled only supported for legacy viewport")
            pass
            

    def temp_select_enabled(self, enable_picking):
        """Disables object picking and selection rect until next mouse up.
            enable_picking: enable picking for surface snap
        """
        if self._is_legacy:
            self._win.legacy_window.disable_selection_rect(enable_picking)
        else:
            # print("temp_select_enabled only supported for legacy viewport")
            pass


    @property
    def manipulating_camera(self):
        if self._is_legacy:
            return self._win.legacy_window.is_manipulating_camera()
        else:
            # print("is_manipulating_camera only supported for legacy viewport")
            return False





    def save_render(self, file_path: str, render_product_path: str = None):
        """Doesn't save any overlaid SceneView drawing"""
        vut.capture_viewport_to_file(self._api, 
                                     file_path=file_path, 
                                     is_hdr=False, 
                                     render_product_path=render_product_path)





    def info(self, scene_view=None):

        out = f"window_name='{self.window_name}' is_legacy={self.is_legacy} usd_context_name='{self.usd_context_name} api_id='{self._api.id}'\n"

        out += f"ui_size={self.ui_size} dpi={omni.ui.Workspace.get_dpi_scale()} px_size={self.px_size} ui_size_ratio={self.ui_size_ratio}\n"
        out += f"render_size_px={self.render_size_px} render_fill_frame={self.render_fill_frame} render_ratio={self.render_size_ratio}\n"
        if scene_view is not None:
            out += f"iscene_half={self.iscene_half(scene_view)} iscene_size={self.iscene_size(scene_view)} iscene_render_half={self.iscene_render_half(scene_view)}\n"

        out += f"camera_path='{self.camera_path}'\n"
        out += f"camera frustrum={self.get_conformed_frustum()}\n"
        view,proj = self.get_camera_view_proj()
        out += f"camera matrixes: view={view} proj={proj}\n"

        out += f"conform_policy={self.get_conform_policy()}\n"
        if scene_view is not None:
            out += f"scene_view aspect_ratio={scene_view.aspect_ratio_policy}\n"
        
        out += f"fps={self.fps}\n"

        return out



"""Examples:
vp = ViewportHelper()

res = vp.attach() # "Viewport" "Viewport Next"
print(f"attach res={res}")

frame = vp.get_frame("id")

#frame.clear()
#with frame:
#    with ui.VStack():
#        ui.Spacer()
#        ui.Label("LABEL", alignment=ui.Alignment.CENTER, style={"font_size": 72})
#        ui.Button("TO")
#        ui.Spacer()


print (vp.info())

#vp.camera_path = "OmniverseKit_Top" # OmniverseKit_Persp

vp.save_render("c:/tmp/vp.png")


"""