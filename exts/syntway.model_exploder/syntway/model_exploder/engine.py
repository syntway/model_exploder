import asyncio, copy

import carb

import omni.ext
import omni.ui as ui
from omni.ui import scene as sc
from omni.ui import color as cl

import omni.kit.commands
import omni.usd
import omni.timeline

from pxr import Usd, UsdGeom, UsdSkel, Sdf, Tf
import pxr.Gf as Gf

import omni.kit.notification_manager as nm

from omni.usd.commands import TransformPrimCommand, TransformPrimSRTCommand

from .libs.usd_helper import UsdHelper
from .libs.usd_utils import (set_prim_translation, set_prim_translation_fast, 
                             set_prim_transform, get_prim_transform, 
                             get_prim_translation, create_edit_context)
from .libs.viewport_helper import ViewportHelper

from .libs.app_helper import AppHelper
from .libs.app_utils import get_setting_or, set_setting, call_after_update

from . import const


APPLY_ASYNC = True


class Engine():

    def __init__(self):

        self.meshes_base_aabb = Gf.Range3d()

        self._meshes = []
        
        self._dist = 0
        self._center_mode = get_setting_or(const.SETTINGS_PATH + const.CENTER_MODE_SETTING, const.DEFAULT_CENTER_MODE)        
        self._dist_mult = get_setting_or(const.SETTINGS_PATH + const.DIST_MULT_SETTING, const.DEFAULT_DIST_MULT)
        self._order_accel = get_setting_or(const.SETTINGS_PATH + const.ACCEL_SETTING, const.ACCEL_DEFAULT)

        self._explo_center = Gf.Vec3d(0)
        self._last_explo_center = Gf.Vec3d(0)
        self._apply_needed = False
        self._apply_task = None
        self._recalc_changed_needed = set()
        self._ignore_next_objects_changed = 0  # 0=no, 1=only next, 2:all until reset

        self._dist_base_size = 100

        self.usd = UsdHelper()

        self._app = AppHelper()
        self._app.add_update_event_fn(self._on_update)

        stream = omni.timeline.get_timeline_interface().get_timeline_event_stream()
        self._timeline_sub = stream.create_subscription_to_pop(self._on_timeline_event)



    def destroy(self):
        self._apply_cancel()

        self._timeline_sub = None

        self._recalc_changed_needed.clear()
        
        if self.usd:
            self.usd.remove_stage_objects_changed_fn(self._on_stage_objects_changed)
            self.usd.detach()
            self.usd = None

        if self._app:
            self._app.detach()
            self._app = None

        Engine._instance = None




    def reset(self, set_to_initial):
        self._apply_cancel()

        if set_to_initial and self.dist > 0:  # if dist is 0, nothing to do
            self._apply(-2, self._explo_center, self._meshes)  # returns prims to initial's

        self._meshes.clear()
        self._dist = 0

        self.usd.remove_stage_objects_changed_fn(self._on_stage_objects_changed)



    def _on_update(self, _):

        if self._recalc_changed_needed:
            self._recalc_changed(self._recalc_changed_needed)
            self._recalc_changed_needed.clear()

        if self._apply_needed:

            if APPLY_ASYNC:
                if not self._apply_task or self._apply_task.done():
                    self._apply_needed = False

                    dist = self._dist

                    explo_center = Gf.Vec3d(self._explo_center)

                    meshes = copy.copy(self._meshes)

                    self._apply_task = asyncio.ensure_future(self._async_apply(dist, explo_center, meshes))
                # else still applying last

            else:
                self._apply_needed = False
                self._apply(-1, self._explo_center, self._meshes)  # returns prims to initial's




    def _on_stage_objects_changed(self, notice):

        if self._ignore_next_objects_changed:
            if self._ignore_next_objects_changed == 1:
                self._ignore_next_objects_changed = 0
            return

        if not self._meshes:  # should never happen?
            return

        # set filters  out duplicate path property changes
        changed_paths = set(Sdf.Path.GetAbsoluteRootOrPrimPath(i) for i in notice.GetChangedInfoOnlyPaths())

        # print("_on_stage_objects_changed", changed_paths)

        for n in changed_paths:
            ch_path = n.GetPrimPath().pathString

            # avoid camera changes
            if ch_path.startswith("/OmniverseKit_") or ch_path.endswith("/animationData"):
                continue

            for p in self._meshes:
                path = p["path"]

                if path.startswith(ch_path):
                    self._recalc_changed_needed.add(path)



    def _on_timeline_event(self, e):
        # print("engine:_on_timeline_event", e.type)

        if self.has_meshes:
            if e.type == int(omni.timeline.TimelineEventType.CURRENT_TIME_CHANGED):
                self._ignore_next_objects_changed = 1




    AVOID_CHILDREN_PRIM_TYPES = ["Camera"]  # avoid recursion on these

    @staticmethod
    def _traverse_add_prim(list, prim):
        """Recursively traverse the hierarchy"""

        if not prim.IsValid():  # might not exist anymore
            return

        prim_t = prim.GetTypeName()

        if prim.HasAuthoredReferences():  # refs: check if any children
            ref_list = []
            children = prim.GetChildren()
            for c in children:
                Engine._traverse_add_prim(ref_list, c)

            if ref_list:  # add children but not itself
                list += ref_list
            else:  # no children, add itself
                list.append(prim)
            return

        if prim.IsA(UsdGeom.PointInstancer) or prim.IsA(UsdSkel.Root):  # instance, SkelRoot: add but don't recurse inside
            list.append(prim)
            return

        if prim.IsA(UsdGeom.Gprim):
            list.append(prim)

        if not prim_t in Engine.AVOID_CHILDREN_PRIM_TYPES:
            children = prim.GetChildren()
            for c in children:
                Engine._traverse_add_prim(list, c)



    def _sel_get_prim_paths_parent_first_order(self, paths):
        
        stage = self.usd.stage

        prims = []
        for path in paths:
            prim = stage.GetPrimAtPath(path)
            prims.append(prim)

        u_prims = []
        for p in prims:
            Engine._traverse_add_prim(u_prims, p)

        return u_prims



    def sel_capture(self, paths=None):
        
        # print("sel_capture")
        if paths is None:
            paths = self.usd.get_selected_prim_paths()
        # print("_sel_capture", paths)
        
        u_prims = self._sel_get_prim_paths_parent_first_order(paths)

        self._meshes = []
        self._dist = 0        

        if len(u_prims) < 2:
            return False


        time_code = self.usd.timecode

        xform_cache = UsdGeom.XformCache(time_code)
        bbox_cache = UsdGeom.BBoxCache(time_code, [UsdGeom.Tokens.default_])

        self._explo_center = Gf.Vec3d(0)  # average of prim centroids
        aa_bounds = Gf.Range3d()

        # world positions
        for prim in u_prims:

            path = prim.GetPath().pathString

            lbb = bbox_cache.ComputeLocalBound(prim)
            lcent = lbb.ComputeCentroid()
            ltrans = get_prim_translation(prim, time_code)
            ldelta = ltrans - lcent  # translation from centroid to the placing pos

            wbb = bbox_cache.ComputeWorldBound(prim)
            wbb_aa = wbb.ComputeAlignedRange()
            aa_bounds.UnionWith(wbb_aa)
            wtrans = wbb.ComputeCentroid()

            lmat = get_prim_transform(prim, False, xform_cache, time_code)

            # print(path, "local", lbb, lcent, ltrans, "world", wbb, wbb_aa, wtrans, lmat)

            # prim, prim_path, untransformed/local mid, world_mid, initial_local_translation
            entry = {"prim": prim, "path": path, "ini_wtrans": wtrans, "ldelta": ldelta, "ini_lmat": lmat}
            self._meshes.append(entry)
            # print(entry)
            
            self._explo_center += wtrans



        # centroid and base AA bounds
        self._explo_center /= len(u_prims)
        self._last_explo_center = self._explo_center

        self.meshes_base_aabb = aa_bounds

        # _dist_base_size size scale
        size = aa_bounds.GetSize()
        self._dist_base_size = max(size[0], size[1], size[2]) * 0.5


        self._calc_dist_order()


        # print(time_code, self._explo_center, self._dist_base_size)

        self._ignore_next_objects_changed = 0
        self.usd.add_stage_objects_changed_fn(self._on_stage_objects_changed)

        # print("sel_capture end")
        return True




    def _recalc_changed(self, ch_paths):

        time_code = self.usd.timecode
        bbox_cache = UsdGeom.BBoxCache(time_code, [UsdGeom.Tokens.default_])

        dist = self._dist
        dist = self._calc_dist(dist)

        for p in self._meshes:

            path = p["path"]
            if path in ch_paths:  # only if changed

                prim = p["prim"]

                lbb = bbox_cache.ComputeLocalBound(prim)
                lcent = lbb.ComputeCentroid()
                ltrans = get_prim_translation(prim, time_code)
                ldelta = ltrans - lcent

                wbb = bbox_cache.ComputeWorldBound(prim)
                new_wtrans = wbb.ComputeCentroid()

                # calc dir
                w_dir = new_wtrans - self._explo_center
                w_dir = self._calc_normalized_dir(w_dir)
                
                new_ini_wtrans = new_wtrans - w_dir * dist

                p["ini_wtrans"] = new_ini_wtrans
                p["ldelta"] = ldelta
                # print("changed", path, new_wtrans, ldelta)

        # not needed and conflicts with translate manipulator's dragging: self.apply_asap()

        self._calc_dist_order()









    def apply_asap(self):
        self._apply_needed = True


    def _apply_cancel(self):
        if APPLY_ASYNC:
            if self._apply_task:
                if self._apply_task.done():
                    return
                self._apply_task.cancel()


    async def _async_apply(self, dist_value, explo_center, meshes):
        self._apply(dist_value, explo_center, meshes)
        self._apply_task = None




    def _apply(self, dist, explo_center, meshes):
        """dist: -2: reset to stored initial pos, -1: use current self._dist, >=0: 0..1"""

        if not meshes:
            return

        # print("_apply", dist)

        time_code = self.usd.timecode

        changes = self._prepare_apply_state(dist, explo_center, meshes, time_code, True)

        is_reset = dist == -2
        state = (is_reset, changes, time_code)
        
        Engine.apply_state(state, self.usd.stage, self)

        # print("_apply end")





    def _prepare_apply_state(self, dist, explo_center, meshes, time_code, with_prims):
        """dist: -2: reset to stored initial pos, -1: use current self._dist, >=0: 0..1"""

        if dist == -1:
            dist = self._dist
        # dist can now be [0..1] or -2 for reset to initial
        if dist >= 0:
            dist_factor = self._calc_dist(dist)
        else:
            dist_factor = dist

        time_code = self.usd.timecode

        xform_cache = UsdGeom.XformCache(time_code)

        changes = []

        for mp in meshes:

            prim = mp["prim"]            
            if not prim.IsValid():  # avoid any invalidated prims, deleted for example
                # print("skipping", prim)
                continue

            path = mp["path"]
            ini_wtrans = mp["ini_wtrans"]
            ldelta = mp["ldelta"]
            prim = mp["prim"]
            dist_order = mp["dist_order"]
            
            if dist_factor >= 0:
                # calc world pos
                # calc dir
                w_ini_vec = ini_wtrans - explo_center
                w_ini_len = w_ini_vec.GetLength()
                w_ini_len = max(w_ini_len, 1e-5)

                w_dir = self._calc_normalized_dir(w_ini_vec)

                order_factor = 1.0 + dist_order * self._order_accel
                w_vec = w_dir * dist_factor * order_factor

                dest_w_trans = ini_wtrans + w_vec

                # get local->parent->world transforms
                p2w = xform_cache.GetParentToWorldTransform(prim)

                # transform back from world to local coords
                w2p = p2w.GetInverse()
                dest_ptrans = w2p.Transform(dest_w_trans)

                # calc delta in mesh local/untransformed space
                dest_ltrans = dest_ptrans + ldelta

                # local trans, in parent space coords
                ltrans = (dest_ltrans[0], dest_ltrans[1], dest_ltrans[2])

                #print(prim, dest_w_trans, ltrans)


            else:
                ltrans = mp["ini_lmat"]

            if with_prims:
                changes.append((prim, path, ltrans))
            else:
                changes.append((None, path, ltrans))

        return changes




    @staticmethod
    def apply_state(state, stage, instance):
        # print("apply_state", state, instance)

        is_reset, changes, time_code = state

        if instance:
            instance._ignore_next_objects_changed = 2

        if not is_reset:

            """ Slower alternative:
            for ch in changes:
                prim, path, ltrans = ch
                # print(path,ltrans, type(ltrans))

                cmd = TransformPrimSRTCommand(path=path,
                                                new_translation=ltrans,
                                                time_code=time_code)
                cmd.do()
            """
            
            stage = stage
            sdf_change_block = 2
            Sdf.BeginChangeBlock()

            for ch in changes:
                prim, path, lmat = ch
                if prim is None:
                    prim = stage.GetPrimAtPath(path)
                # print(prim, ltrans)

                with create_edit_context(path, stage):
                    set_prim_translation(prim, lmat, sdf_change_block=sdf_change_block, time_code=time_code)
                    #set_prim_translation_fast(prim, lmat, sdf_change_block=sdf_change_block, time_code=time_code)

            Sdf.EndChangeBlock()

        else:

            for ch in changes:
                prim, path, ltrans = ch
                # print(path,ltrans, type(ltrans))

                cmd = TransformPrimCommand(path=path,
                                           new_transform_matrix=ltrans,
                                           time_code=time_code)
                cmd.do()

        if instance:
            instance._ignore_next_objects_changed = 0

        # print("apply_state end")





    def commit(self):

        time_code = self.usd.timecode

        dist = -2
        changes = self._prepare_apply_state(dist, self._explo_center, self._meshes, time_code, False)
        is_reset = dist == -2
        initial_state = (is_reset, changes, time_code)

        dist = -1
        changes = self._prepare_apply_state(dist, self._explo_center, self._meshes, time_code, False)
        is_reset = dist == -2
        final_state = (is_reset, changes, time_code)


        self._ignore_next_objects_changed = 2

        stage = self.usd.stage
        omni.kit.commands.execute("ExplodeEngineApplyCommand", 
                                  initial_state=initial_state, 
                                  final_state=final_state, 
                                  stage=stage)

        self._ignore_next_objects_changed = 0

        self.reset(False)

        """
        # compile transform list for undo
        time_code = self.usd.timecode
        xform_cache = UsdGeom.XformCache(time_code)

        self._ignore_next_objects_changed = 2
        
        xforms=[]
        for mp in self._meshes:
            p = mp["prim"]
            path = mp["path"]

            ini_mat = mp["ini_lmat"]
            new_mat = get_prim_transform(p, False, xform_cache, time_code)

            xforms.append((path, new_mat, ini_mat, time_code, False))

        self.reset(False)

        if xforms:
            if True:
                omni.kit.undo.begin_group()
                for x in xforms:
                    omni.kit.commands.execute("TransformPrim", 
                                              path=x[0], 
                                              new_transform_matrix=x[1],
                                              old_transform_matrix=x[2]
                                             )
                omni.kit.undo.end_group()

            else:
                omni.kit.commands.execute(
                "TransformPrims", prims_to_transform=xforms
                )

        self._ignore_next_objects_changed = 0
        """








    def _calc_dist(self, dist):
        dist = dist ** const.DIST_EXP
        dist = dist * self._dist_base_size * self._dist_mult
        return dist


    def _calc_dir(self, dir):
        if self._center_mode >= 1 and self._center_mode <= 3:  # around axis: zero axis displacement
            dir[self._center_mode - 1] = 0.
        elif self._center_mode >= 4:  # from a plane
            i = self._center_mode - 4
            dir[i] = 0.
            dir[(i + 1) % 3] = 0.


    def _calc_normalized_dir(self, dir):
        self._calc_dir(dir)

        if dir.GetLength() > 1e-6:
            dir.Normalize()

        return dir


    def _calc_dist_order(self):
        """dist_order is the 0..1 position of the mesh with regard to _explo_center"""

        min_len = float("inf")
        max_len = -1

        len_list = []
        for mp in self._meshes:
            vec = mp["ini_wtrans"] - self._explo_center
            self._calc_dir(vec)

            len = vec.GetLength()
            len = max(len, 1e-5)
            len_list.append(len)

            min_len = min(len, min_len)
            max_len = max(len, max_len)

        max_min_range = max_len - min_len
        max_min_range = max(max_min_range, 1e-5)
        index = 0
        for mp in self._meshes:
            order = (len_list[index] - min_len) / max_min_range
            mp["dist_order"] = order
            index+=1







    @property
    def has_meshes(self):
        return self.meshes_count >= 2

    @property
    def meshes_count(self):
        return len(self._meshes)

    @property
    def stage_selection_meshes_count(self):
        paths = self.usd.get_selected_prim_paths()
        u_prims = self._sel_get_prim_paths_parent_first_order(paths)
        return len(u_prims)


    @property
    def center(self):
        return self._explo_center

    @center.setter
    def center(self, center):
        self._explo_center = center
        self._calc_dist_order()
        self.apply_asap()

    @property    
    def dist(self):
        return self._dist

    @dist.setter
    def dist(self, d):
        self._dist = d
        self.apply_asap()



    @property
    def center_mode(self):
        return self._center_mode

    @center_mode.setter
    def center_mode(self, c):
        self._center_mode = c
        set_setting(const.SETTINGS_PATH + const.CENTER_MODE_SETTING, self._center_mode)
        self.apply_asap()

    @property
    def order_accel(self):
        return self._order_accel

    @order_accel.setter
    def order_accel(self, v):
        self._order_accel = v
        set_setting(const.SETTINGS_PATH + const.ACCEL_SETTING, self._order_accel)
        self.apply_asap()

    @property
    def dist_mult(self):
        return self._dist_mult

    @dist_mult.setter
    def dist_mult(self, m):
        self._dist_mult = m
        set_setting(const.SETTINGS_PATH + const.DIST_MULT_SETTING, self._dist_mult)
        self.apply_asap()



    def recenter(self):
        self._explo_center = self._last_explo_center
        self.apply_asap()

    def is_centered(self):
        return Gf.IsClose(self._explo_center, self._last_explo_center, 1e-6)






