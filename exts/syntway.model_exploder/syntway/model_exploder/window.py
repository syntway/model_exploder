import asyncio, copy, webbrowser

import carb

import omni.ui as ui
from omni.ui import scene as sc
from omni.ui import color as cl

import omni.kit.commands
import omni.usd
import omni.timeline

from pxr import Usd, UsdGeom, UsdSkel, Sdf, Tf
import pxr.Gf as Gf

import omni.kit.notification_manager as nm

from .libs.viewport_helper import ViewportHelper

from .libs.app_utils import get_setting_or, set_setting, call_after_update
from .libs.ui_utils import create_reset_button, create_tooltip_fn, UiPal, UiPal_refresh

from .libs.manipulators import TranslateManipulator

from .engine import Engine
from . import const
from . import style






class Window(ui.Window):

    def __init__(self, title: str, ext_id: str, **kwargs):
        # print("win.__init__")

        self._ext_id = ext_id
        self._engine = Engine()

        self._scene_reg = None
        self._center_manip = None
        self._center_label = None
        self._center_label_transform = None
        self._base_aabb_lines = []

        self._options_bounds_alpha = get_setting_or(const.SETTINGS_PATH + const.OPTIONS_BOUNDS_ALPHA_SETTING, 
                                                    const.OPTIONS_BOUNDS_ALPHA_DEFAULT)
        self._options_unselect_on_use = get_setting_or(const.SETTINGS_PATH + const.OPTIONS_UNSELECT_ON_USE_SETTING, 
                                                       const.OPTIONS_UNSELECT_ON_USE_DEFAULT)


        kwargs["auto_resize"] = True

        super().__init__(title, **kwargs)

        self.auto_resize = True

        self._ui_built = False
        self.frame.set_build_fn(self._build_fn)

        self._vp = ViewportHelper()
        # print(self._vp.info())
        
        # create manipulator scene
        self._scene_reg = self._vp.register_scene_proxy(self._scene_create, self._scene_destroy, 
                                                        self._scene_get_visible, self._scene_set_visible,
                                                        self._ext_id)

        self._engine.usd.add_stage_event_fn(self._on_stage_event)





    def destroy(self, is_ext_shutdown):
        # print("win.destroy", is_ext_shutdown)


        self._dist_slider = None
        self._use_button = None
        self._center_mode_combo = None
        self._recenter_button = None

        self._options = None
        self._options_dist_mult_combo = None
        self._options_accel_slider = None
        self._options_bounds_slider = None
        self._options_unselect_on_use_check = None

        self._done_button = None
        self._reset_button = None

        if self._center_manip:
            self._center_manip.destroy()
            self._center_manip = None

        self._center_label = None
        self._center_label_transform = None

        self._base_aabb_lines.clear()

        if self._scene_reg:
            self._vp.unregister_scene(self._scene_reg)
            self._scene_reg = None

        if self._vp:
            self._vp.detach()
            self._vp = None

        if self._engine:
            if self._engine.usd:
                self._engine.usd.remove_stage_event_fn(self._on_stage_event)

            if not is_ext_shutdown and self._engine.has_meshes and self._engine.dist != 0:
                self._engine.reset(True)  # cancel current to intial positions

            self._engine.destroy()
            self._engine = None

        super().destroy()







    def _build_fn(self):
        """Called to build the UI once the window is visible"""
        # print(f"win._build_fn {self.visible}")

        UiPal_refresh()

        self.frame.style = style.WINDOW_FRAME
       
        with ui.VStack(width=386, style={"margin": 7}):  # spacing=9, style={"margin": 7}
            with ui.VStack(height=0, spacing=11, style={"margin": 0}):  # spacing=9, style={"margin": 7}

                with ui.HStack(skip_draw_when_clipped=True, spacing=5):
                    self._use_button = ui.Button(const.SELECT_TO_EXPLODE_TEXT, 
                                                 name="ever_bright",
                                                 height=24, 
                                                 clicked_fn=self._on_use_clicked,
                                                 tooltip_fn=create_tooltip_fn(const.TOOLTIP_USE))

                    ui.Image(name="info", 
                             fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, width=18, height=24,
                             mouse_pressed_fn=lambda *p: self._on_info(),
                             tooltip_fn=create_tooltip_fn(const.TOOLTIP_INFO))

                with ui.HStack(skip_draw_when_clipped=True, spacing=6):
                    ui.Label(const.DISTANCE_LABEL, width=50,
                             mouse_pressed_fn=lambda *p: self._on_dist_set_zero(),
                             tooltip_fn=create_tooltip_fn(const.TOOLTIP_DIST))

                    self._dist_slider = ui.FloatSlider(min=0, max=1,
                                                       # tooltip_fn=create_tooltip_fn(const.TOOLTIP_DIST)
                                                       )
                    self._dist_slider.model.add_value_changed_fn(self._on_dist_slider_changed)

                with ui.HStack(skip_draw_when_clipped=True, spacing=6):
                    ui.Label(const.CENTER_LABEL, width=50,
                             tooltip_fn=create_tooltip_fn(const.TOOLTIP_CENTER_MODE))
                    self._center_mode_combo = ui.ComboBox(self._engine.center_mode,
                                                          *const.CENTER_COMBO_LABELS,
                                                          width=145,
                                                          tooltip_fn=create_tooltip_fn(const.TOOLTIP_CENTER_MODE))
                    self._center_mode_combo.model.add_item_changed_fn(self._on_center_mode_changed)                    
                    self._setup_center_combo_labels()

                    self._recenter_button = ui.Button(const.RECENTER_TEXT, width=60, 
                                                      clicked_fn=self._on_recenter_clicked,
                                                      tooltip_fn=create_tooltip_fn(const.TOOLTIP_RECENTER))


                ui.Spacer(height=1)




                self._options = ui.CollapsableFrame(const.OPTIONS_TITLE,
                                                    collapsed=not bool(const.DEV_MODE))
                with self._options:
                    with ui.VStack(spacing=0, style={"margin": 3}):
                                   
                        with ui.HStack(spacing=6):
                            ui.Label(const.OPTIONS_ACCEL_LABEL,
                                     tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_ACCEL))

                            with ui.HStack():
                                self._options_accel_slider = ui.FloatSlider(min=0, max=const.OPTIONS_ACCEL_MAX)

                                self._options_accel_slider.model.set_value(self._engine._order_accel)
                                self._options_accel_slider.model.add_value_changed_fn(self._on_options_accel_changed)
                                
                                create_reset_button(const.ACCEL_DEFAULT,
                                                    self._options_accel_slider.model,
                                                    self._options_accel_slider.model.set_value,
                                                    self._options_accel_slider.model.add_value_changed_fn)


                        with ui.HStack(spacing=6):
                            ui.Label(const.OPTIONS_DIST_MULT_LABEL,
                                     tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_DIST))

                            with ui.HStack():
                                # locate dist_mult label index from self._engine.dist_mult
                                def get_dist_mult_index(dist_mult):
                                    index = 0
                                    for i in range(len(const.OPTIONS_DIST_MULT_COMBO_VALUES)):
                                        entry = const.OPTIONS_DIST_MULT_COMBO_VALUES[i]
                                        if dist_mult == entry[1]:
                                            index = i
                                            break
                                    return index

                                self._options_dist_mult_combo = ui.ComboBox(
                                    get_dist_mult_index(self._engine.dist_mult),
                                    *[a[0] for a in const.OPTIONS_DIST_MULT_COMBO_VALUES],
                                    tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_DIST)
                                )
                                self._options_dist_mult_combo.model.add_item_changed_fn(self._on_options_dist_mult_changed)                    

                                create_reset_button(get_dist_mult_index(const.DEFAULT_DIST_MULT),
                                                    self._options_dist_mult_combo.model.get_item_value_model(),
                                                    self._options_dist_mult_combo.model.get_item_value_model().set_value,
                                                    self._options_dist_mult_combo.model.add_item_changed_fn)


                        with ui.HStack(spacing=6):
                            ui.Label(const.OPTIONS_BOUNDS_ALPHA_LABEL,
                                     tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_BOUNDS))

                            with ui.HStack():
                                self._options_bounds_slider = ui.FloatSlider(min=0, max=1,
                                                                             #tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_BOUNDS)
                                                                             )

                                self._options_bounds_slider.model.set_value(self._options_bounds_alpha)
                                self._options_bounds_slider.model.add_value_changed_fn(self._on_options_bounds_changed)
                                
                                create_reset_button(const.OPTIONS_BOUNDS_ALPHA_DEFAULT,
                                                    self._options_bounds_slider.model,
                                                    self._options_bounds_slider.model.set_value,
                                                    self._options_bounds_slider.model.add_value_changed_fn)


                        with ui.HStack(spacing=6):
                            ui.Label(const.OPTIONS_UNSELECT_ON_USE_LABEL,
                                     tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_UNSELECT))
                            
                            with ui.HStack():
                                self._options_unselect_on_use_check = ui.CheckBox(width=12,
                                    tooltip_fn=create_tooltip_fn(const.TOOLTIP_OPTIONS_UNSELECT))

                                self._options_unselect_on_use_check.model.set_value(self._options_unselect_on_use)
                                self._options_unselect_on_use_check.model.add_value_changed_fn(self._on_options_unselect_changed)

                                # ui.Spacer(width=1)
                                ui.Line()
                                
                                create_reset_button(const.OPTIONS_UNSELECT_ON_USE_DEFAULT,
                                                    self._options_unselect_on_use_check.model,
                                                    self._options_unselect_on_use_check.model.set_value,
                                                    self._options_unselect_on_use_check.model.add_value_changed_fn)


                ui.Spacer(height=1)

                with ui.HStack(skip_draw_when_clipped=True, spacing=9):
                    self._reset_button = ui.Button(const.RESET_TEXT, clicked_fn=self._on_reset_clicked,
                                                   tooltip_fn=create_tooltip_fn(const.TOOLTIP_CANCEL))

                    ui.Spacer()

                    self._done_button = ui.Button(const.DONE_TEXT, clicked_fn=self._on_done_clicked,
                                                  tooltip_fn=create_tooltip_fn(const.TOOLTIP_APPLY))


                #ui.Button("Test", clicked_fn=self._on_test)
        

        self._ui_built = True

        self._refresh_ui()
        




    def _on_stage_event(self, ev: carb.events.IEvent):
        # print("Window._on_stage_event", ev.type)

        if not self._ui_built:  # a stage event can call us before _build_fn()
            return

        if ev.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            if not self._engine.has_meshes:
                self._refresh_ui()

        elif ev.type == int(omni.usd.StageEventType.CLOSING):
            # print("Window.CLOSING")

            self._reset(False)  # calls engine.reset
            #self._engine.usd.detach()

        elif ev.type == int(omni.usd.StageEventType.OPENED):
            # print("Window.OPENED")
            self._setup_center_combo_labels()



    def _refresh_ui(self):
        if not self._engine.has_meshes:  # nothing selected

            self._dist_slider.enabled = False
            self._center_mode_combo.enabled = False
            self._recenter_button.enabled = False
            self._done_button.enabled = False
            self._reset_button.enabled = False

            sel_mesh_count = self._engine.stage_selection_meshes_count
            if sel_mesh_count >= 2:
                self._use_button.text = const.SELECT_TO_USE_TEXT.format(sel_mesh_count)
                self._use_button.enabled = True
            else:
                self._use_button.text = const.SELECT_TO_EXPLODE_TEXT
                self._use_button.enabled = False

        else:
            mesh_count = self._engine.meshes_count
            self._use_button.text = const.SELECTED_TEXT.format(mesh_count)

            self._use_button.enabled = False
            self._dist_slider.enabled = True
            self._center_mode_combo.enabled = True
            self._recenter_button.enabled = not self._engine.is_centered()
            self._done_button.enabled = True
            self._reset_button.enabled = True


    def _setup_center_combo_labels(self):
        model = self._center_mode_combo.model
        ch = model.get_item_children()

        up = self._engine.usd.stage_up_index

        if up == 1:  # y up
            mark = [const.CENTER_COMBO_AXIS_FIRST + 1, const.CENTER_COMBO_PLANE_FIRST + 2]
        else:  # z up
            mark = [const.CENTER_COMBO_AXIS_FIRST + 2, const.CENTER_COMBO_PLANE_FIRST + 0]


        for l in range(len(const.CENTER_COMBO_LABELS)):
            label = const.CENTER_COMBO_LABELS[l]

            if l in mark:
                if l < const.CENTER_COMBO_PLANE_FIRST:
                    label += const.CENTER_COMBO_AXIS_SUFFIX
                else:
                    label += const.CENTER_COMBO_PLANE_SUFFIX

            m = model.get_item_value_model(ch[l])
            m.set_value(label)



    def _reset(self, set_to_initial):
        self._engine.reset(set_to_initial)

        self._enable_center_controls(False)
        self._enable_base_aabb(False)

        self._dist_slider.model.set_value(0)

        self._refresh_ui()





    def _on_use_clicked(self):
        if not self._engine.sel_capture():
            self._reset(False)
            return

        self._sync_base_aabb()
        self._enable_base_aabb(True)
        self._enable_center_controls(True)

        if self._center_manip:
            self._set_center_manip_point(self._engine.center)

        if self._options_unselect_on_use:
            self._engine.usd.set_selected_prim_paths([])

        self._refresh_ui()
        

    def _on_dist_set_zero(self):
        self._dist_slider.model.set_value(0)

    def _on_dist_slider_changed(self, model):
        self._engine.dist = model.as_float


    def _on_center_mode_changed(self, m, *args):        
        self._engine.center_mode = m.get_item_value_model().get_value_as_int()

    def _on_recenter_clicked(self):
        self._engine.recenter()
        self._set_center_manip_point(self._engine.center)
        self._recenter_button.enabled = not self._engine.is_centered()


    def _on_done_clicked(self):
        self._engine.commit()

        self._reset(False)


    def _on_reset_clicked(self):
        self._reset(True)




    def _scene_create(self, vp_args):

        vp_api = vp_args["viewport_api"]
        if not self._vp.same_api(vp_api):  # ensure scene is created in same viewport we're attached to
            return

        # print("_scene_create", vp_args, self._vp._api)

        self._center_manip = TranslateManipulator(viewport=self._vp,
                                                  enabled=False,
                                                  changed_fn=self._on_center_manip_changed
                                                  )
        self._center_label_transform = sc.Transform()  # before next _sync
        self._sync_scene_label()

        with self._center_label_transform:

            with sc.Transform(look_at=sc.Transform.LookAt.CAMERA, scale_to=sc.Space.SCREEN):
                with sc.Transform(transform=sc.Matrix44.get_scale_matrix(2, 2, 1)):
                    wup = self._engine.usd.stage_up
                    wup *= const.CENTER_MANIP_LABEL_OFFSET
                    with sc.Transform(transform=sc.Matrix44.get_translation_matrix(*wup)):
                        self._center_label = sc.Label(const.CENTER_TEXT, alignment=ui.Alignment.CENTER, 
                                                      size=const.CENTER_MANIP_LABEL_SIZE, visible=False)

        self._create_base_aabb()


    def _scene_destroy(self):
        if self._center_manip:
            self._center_manip.destroy()
            self._center_manip = None

    def _scene_get_visible(self):
        return True


    def _scene_set_visible(self, value):
        if self._center_manip.enabled:  # only set if manip is enabled
            self._center_manip.enabled = value


    def _on_center_manip_changed(self, action, manip):
        # print("_on_center_manip_changed")

        assert self._engine.has_meshes

        self._sync_scene_label()

        self._engine.center = manip.point

        self._recenter_button.enabled = not self._engine.is_centered()            



    def _enable_center_controls(self, ena):
        if self._center_manip:
            self._center_manip.enabled = ena
        if self._center_label:
            self._center_label.visible = ena


    def _set_center_manip_point(self, wpt):
            self._center_manip.point = wpt
            self._sync_scene_label()

    def _sync_scene_label(self):
        wpt = Gf.Vec3d(self._center_manip.point)
        self._center_label_transform.transform = sc.Matrix44.get_translation_matrix(*wpt)




    def prepare_base_aabb_color(self):
        color = const.BOUNDS_BASE_AABB_COLOR
        color = (color & 0x00ffffff) | (int(self._options_bounds_alpha * 255) << 24)
        return color

    def _create_base_aabb(self):
        self._base_aabb_lines.clear()

        color = self.prepare_base_aabb_color()
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False)) 

        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False)) 

        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))
        self._base_aabb_lines.append(sc.Line([0, 0, 0], [0, 0, 0], color=color, visible=False))


    def _sync_base_aabb(self):
        """
        points p#
            4  5            
           6  7             
        
            0  1
           2  3

        lines
            8|   |9
          10|   |11

            _4_    
          5/  /6                           
           -7-

            _0_    
          1/  /2                           
           -3-
        """
        if self._engine.meshes_base_aabb.IsEmpty():
            return

        mi, ma = self._engine.meshes_base_aabb.min, self._engine.meshes_base_aabb.max

        p0=[mi[0],mi[1],mi[2]]
        p1=[ma[0],mi[1],mi[2]]
        p2=[mi[0],mi[1],ma[2]]
        p3=[ma[0],mi[1],ma[2]]

        p4=[mi[0],ma[1],mi[2]]
        p5=[ma[0],ma[1],mi[2]]
        p6=[mi[0],ma[1],ma[2]]
        p7=[ma[0],ma[1],ma[2]]

        self._base_aabb_lines[0].start,self._base_aabb_lines[0].end, = p0,p1
        self._base_aabb_lines[1].start,self._base_aabb_lines[1].end, = p0,p2
        self._base_aabb_lines[2].start,self._base_aabb_lines[2].end, = p1,p3
        self._base_aabb_lines[3].start,self._base_aabb_lines[3].end, = p2,p3

        self._base_aabb_lines[4].start,self._base_aabb_lines[4].end, = p4,p5
        self._base_aabb_lines[5].start,self._base_aabb_lines[5].end, = p4,p6
        self._base_aabb_lines[6].start,self._base_aabb_lines[6].end, = p5,p7
        self._base_aabb_lines[7].start,self._base_aabb_lines[7].end, = p6,p7

        self._base_aabb_lines[8].start,self._base_aabb_lines[8].end, = p0,p4
        self._base_aabb_lines[9].start,self._base_aabb_lines[9].end, = p1,p5
        self._base_aabb_lines[10].start,self._base_aabb_lines[10].end, = p2,p6
        self._base_aabb_lines[11].start,self._base_aabb_lines[11].end, = p3,p7


    def _enable_base_aabb(self, ena):
        if self._engine.meshes_base_aabb.IsEmpty():
            ena = False

        for l in self._base_aabb_lines:
            l.visible = ena




    def _on_options_dist_mult_changed(self, m, *args):
        index = m.get_item_value_model().get_value_as_int()
        mult = const.OPTIONS_DIST_MULT_COMBO_VALUES[index][1]
        self._engine.dist_mult = mult

    def _on_options_accel_changed(self, model):
        self._engine.order_accel = model.as_float


    def _on_options_bounds_changed(self, model):
        self._options_bounds_alpha = model.as_float
        set_setting(const.SETTINGS_PATH + const.OPTIONS_BOUNDS_ALPHA_SETTING, self._options_bounds_alpha)
        
        color = self.prepare_base_aabb_color()
        for l in self._base_aabb_lines:
            l.color = color
        

    def _on_options_unselect_changed(self, m):
        self._options_unselect_on_use = m.as_float
        set_setting(const.SETTINGS_PATH + const.OPTIONS_UNSELECT_ON_USE_SETTING, self._options_unselect_on_use)



    def _on_info(self):
        res = webbrowser.open(const.INFO_URL)
