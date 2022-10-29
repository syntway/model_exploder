"""
Notes:
"""

import omni.kit
import omni.usd

from pxr import Gf, Tf, Sdf, Usd, UsdGeom, CameraUtil

from .app_utils import call_after_update


class UsdHelper():
    VERSION = 17
    STAGE_CHANGED_SUB_PREFIX = "UsdHelper-stage-changed-ev"

    def __init__(self, attach=True, stage_opened_refresh=1 | 2):
        """
        stage_opened_refresh: resubscribe events when a new stage finishes opening. A mask of:
        1: resubscribe add_stage_event_fn handlers
        2: resubscribe add_stage_objects_changed_fn handlers
        """

        self._ctx = None

        self._stage_changed = {}  # event_type: [sub, set(fn,fn,...)]
        self._stage_objects_changed = None  # [listener, set(fn,fn,...)]

        self._stage_opened_refresh = stage_opened_refresh
        self._stage_opened_refresh_sub = None

        if attach:
            res = self.attach()
            if not res:
                raise AssertionError("Could not attach")

    def __del__(self):
        self.detach()




    def attach(self, usd_ctx=None) -> bool:
        """usd_ctx can be a string for context name, or an existing UsdContext."""

        self.detach()

        if usd_ctx is None:
            usd_ctx = ''
        if isinstance(usd_ctx, str):
            self._ctx = omni.usd.get_context(usd_ctx)
        else:
            self._ctx = usd_ctx            

        if self._stage_opened_refresh:
            self.add_stage_event_fn(self._on_stage_opened_refresh, 
                                    omni.usd.StageEventType.OPENED)

        return True



    def detach(self):
        if self._ctx is not None:
            self._ctx = None

        if self._stage_objects_changed is not None:
            if len(self._stage_objects_changed):
                self._stage_objects_changed[0].Revoke()
            self._stage_objects_changed = None

        self._stage_changed.clear()
        self._stage_opened_refresh_sub = None




    @property
    def context(self):
        return self._ctx


    @property
    def stage(self):
        return self._ctx.get_stage()


    @property
    def stage_state(self) -> omni.usd.StageState:
        return self._ctx.get_stage_state()


    def is_stage_opened(self) -> bool:
        return self.stage_state == omni.usd.StageState.OPENED


    @property
    def stage_up(self):
        up = UsdGeom.GetStageUpAxis(self.stage)
        if up == UsdGeom.Tokens.y:
            return Gf.Vec3d(0, 1, 0)
        elif up == UsdGeom.Tokens.z:
            return Gf.Vec3d(0, 0, 1)
        else:  # UsdGeom.Tokens.x
            return Gf.Vec3d(1, 0, 0)

    @property
    def stage_up_index(self):
        up = UsdGeom.GetStageUpAxis(self.stage)
        if up == UsdGeom.Tokens.y:
            return 1
        elif up == UsdGeom.Tokens.z:
            return 2
        else:  # UsdGeom.Tokens.x: illegal
            return 0





    @property
    def timecode(self) -> Usd.TimeCode:

        stage = self.stage

        """
        if stage.HasAuthoredTimeCodeRange(): -> wrong: a stage might not have timeCodes authored,
            but its references may have.
        Using Usd.TimeCode.Default() in xform_cache.GetLocalTransformation(prim) won't fetch correct matrices
            for time_coded prims
        """

        time = omni.timeline.get_timeline_interface().get_current_time()
        ret = Usd.TimeCode(omni.usd.get_frame_time_code(time, stage.GetTimeCodesPerSecond())) 
        # or ret = Usd.TimeCode( time * stage.GetTimeCodesPerSecond() )

        return ret








    def add_stage_event_fn(self, fn, event_type=-1):
        """
        Doesn't depend on open stage and remains after closing-opening.

        Arg event_type = -1 to accept all, otherwise a single event of type omni.usd.StageEventType.*: (@Kit103)
        0=SAVED
        1=SAVE_FAILED
        2=OPENING
        3=OPENED
        4=OPEN_FAILED
        5=CLOSING
        6=CLOSED
        7=SELECTION_CHANGED
        8=ASSETS_LOADED
        9=ASSETS_LOAD_ABORTED
        10=GIZMO_TRACKING_CHANGED
        11=MDL_PARAM_LOADED
        12=SETTINGS_LOADED
        13=SETTINGS_SAVING
        14=OMNIGRAPH_START_PLAY
        15=OMNIGRAPH_STOP_PLAY
        16=SIMULATION_START_PLAY
        17=SIMULATION_STOP_PLAY
        18=ANIMATION_START_PLAY
        19=ANIMATION_STOP_PLAY
        20=DIRTY_STATE_CHANGED
        """

        event_type = int(event_type)

        if event_type not in self._stage_changed:
            sub = self._sub_stage_event(event_type)
            self._stage_changed[event_type] = [sub, set()]

        ch = self._stage_changed[event_type]
        ch[1].add(fn)


    def _sub_stage_event(self, event_type):
        sub_name = UsdHelper.STAGE_CHANGED_SUB_PREFIX + str(event_type)
        lamb = lambda ev: self._on_stage_event(ev, event_type)
        if event_type == -1:
            sub = self._ctx.get_stage_event_stream().create_subscription_to_pop(lamb,
                                                                                name=sub_name)
        else:
            sub = self._ctx.get_stage_event_stream().create_subscription_to_pop_by_type(event_type, 
                                                                                        lamb,
                                                                                        name=sub_name)
        return sub


    def _on_stage_event(self, ev, target_event_type):
        # print("_on_stage_event", ev.type, target_event_type)

        if target_event_type in self._stage_changed:
            for fn in self._stage_changed[target_event_type][1]:
                fn(ev)


    def remove_stage_event_fn(self, fn, event_type=-1):
        """
        Don't call from fn or will get:
            RuntimeError: Set changed size during iteration
        """
        if event_type in self._stage_changed:
            ch = self._stage_changed[event_type]
            ch[1].discard(fn)



    def _on_stage_opened_refresh(self, ev):
        # print("_on_stage_opened_refresh", ev.type)

        def resub():
            if self._stage_opened_refresh & 1:
                # print("resub _stage_changed")
                for event_type in self._stage_changed:
                    ch = self._stage_changed[event_type]
                    ch[0] = self._sub_stage_event(event_type)

            if self._stage_opened_refresh & 2 and self._stage_objects_changed is not None:
                # print("resub _stage_objects_changed")
                self._stage_objects_changed[0] = self._sub_stage_objects_changed()

        call_after_update(resub)









    def add_stage_objects_changed_fn(self, fn):
        # print("add_stage_objects_changed_fn")

        """
        Depends on stage: if closed must call remove_stage_objects_changed_fn(), then on stage opened call add_stage_objects_changed_fn again.

        From https://graphics.pixar.com/usd/dev/api/class_usd_notice_1_1_objects_changed.html:
        Usd.Notice.ObjectsChanged: Object changes, either "resync" or "changed-info". 
        "Resyncs" are potentially structural changes that invalidate entire subtrees of UsdObjects (including prims and properties). 
        For example, if the path "/foo" is resynced, then all subpaths like "/foo/bar" and "/foo/bar.baz" may be arbitrarily changed. 
        When a prim is resynced, say "/foo/bar", it might have been created or destroyed. In that case "/foo"'s list of children will have changed, but we do not consider "/foo" to be resynced. If we did, it would mean clients would have to consider all of "/foo/bar"'s siblings (and their descendants) to be resynced which might be egregious overinvalidation.

        In contrast, "changed-info" means that a nonstructural change has occurred, like an attribute value change or a value change to a metadata field not related to composition.
        This notice provides API for two client use-cases. Clients interested in testing whether specific objects are affected by the changes should use the AffectedObject() 
        method (and the ResyncedObject() and ChangedInfoOnly() methods). 
        Clients that wish to reason about all changes as a whole should use the GetResyncedPaths() and GetChangedInfoOnlyPaths() methods. 

        fn(notice: Tf.notice) can call notice.GetChangedInfoOnlyPaths()
        """

        if self._stage_objects_changed is None:
            # handler needs to be a method as Register won't hold reference to a local function
            listener = self._sub_stage_objects_changed()

            self._stage_objects_changed = [listener, set()]


        val = self._stage_objects_changed
        val[1].add(fn)
        # print("add")


    def _sub_stage_objects_changed(self):
        return Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_stage_objects_changed, self.stage)


    def _on_stage_objects_changed(self, notice, stage):
        if stage != self.stage or self._stage_objects_changed is None:
            return

        for fn in self._stage_objects_changed[1]:
            fn(notice)


    def remove_stage_objects_changed_fn(self, fn):
        # print("remove_stage_objects_changed_fn")
        if self._stage_objects_changed is not None:
            val = self._stage_objects_changed
            val[1].discard(fn)
            # print("discard")












    def get_selected_prim_paths(self):
        sel = self.get_selection()
        return sel.get_selected_prim_paths()

    def set_selected_prim_paths(self, paths, expand_in_stage=False):
        sel = self.get_selection()
        sel.set_selected_prim_paths(paths, expand_in_stage)    

    def get_selection(self):
        return self._ctx.get_selection()




    def set_pickable(self, enabled, prim_path="/"):
        """If disabled, Kit will still display selection rects but nothing will be selected."""
        self._ctx.set_pickable(prim_path, enabled)







"""
Timeline events

stream = omni.timeline.get_timeline_interface().get_timeline_event_stream()
self._timeline_sub = stream.create_subscription_to_pop(self._on_timeline_event)

0=PLAY
1=PAUSE
2=STOP
3=CURRENT_TIME_CHANGED
4=CURRENT_TIME_TICKED
5=LOOP_MODE_CHANGED
6=START_TIME_CHANGED
7=END_TIME_CHANGED
8=TIME_CODE_PER_SECOND_CHANGED
9=AUTO_UPDATE_CHANGED
10=PREROLLING_CHANGED
"""