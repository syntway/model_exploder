"""
If you're getting Kit launch time errors related with omni.ui.scene, 
add omni.ui.scene to your extension dependencies in extension.toml:
[dependencies]
"omni.ui.scene" = {}





"""
from typing import Dict

import carb
import omni.kit, omni.usd

from pxr import Gf, Sdf, Tf, Usd, UsdGeom

from omni.kit.manipulator.viewport import ManipulatorFactory

from omni.kit.manipulator.transform import AbstractTransformManipulatorModel, Operation

from omni.kit.manipulator.transform.manipulator import TransformManipulator, Axis

from omni.kit.manipulator.transform.simple_transform_model import SimpleTransformModel

from omni.kit.manipulator.transform.gestures import TranslateChangedGesture, TranslateDragGesturePayload


from .viewport_helper import ViewportHelper



class TranslateManipulator():
    VERSION = 9

    def __init__(self, viewport: ViewportHelper, 
                 point=Gf.Vec3d(0, 0, 0),
                 size=1.,
                 enabled=False,
                 axes: Axis = Axis.ALL,
                 style: Dict = {},
                 changed_fn=None):
        """ style: all colors in 0xAABBGGRR
        {
        "Translate.Axis::x": {"color": 0xAABBGGRR},
        "Translate.Axis::y": {"color": },
        "Translate.Axis::z": {"color": },
        "Translate.Plane::x_y": {"color": },
        "Translate.Plane::y_z": {"color": },
        "Translate.Plane::z_x": {"color": },
        "Translate.Point": {"color": 0xAABBGGRR, "type": "point"/"notpoint"},
        }        
        """

        self._manip = None
        self._gesture = None
        self._changed_fn = None

        #if not viewport.is_attached:
        #    raise AssertionError("Viewport not attached")

        self._is_legacy = viewport.is_legacy

        model = SimpleTransformModel()
        model.set_operation(Operation.TRANSLATE)
        model.set_floats(model.get_item("translate"), point)

        self._changed_fn = changed_fn
        self._gesture = TranslateGesture(viewport=viewport, changed_fn=self._on_changed_fn)



        if self._is_legacy:
            self._manip = ManipulatorFactory.create_manipulator(TransformManipulator,
                                                                model=model,
                                                                size=size,
                                                                enabled=enabled,
                                                                axes=axes,
                                                                style=style,
                                                                gestures=[self._gesture])
        else:
            #self._manip = None
            #raise AssertionError("TranslateManipulator not currently usable on VP2")
            self._manip = TransformManipulator(model=model,
                                               size=size,
                                               enabled=enabled,
                                               axes=axes,
                                               style=style,
                                               gestures=[self._gesture])
                            



    def __del__(self):
        self.destroy()

    def destroy(self):
        if self._gesture:
            self._gesture.destroy()
            self._gesture = None

        if self._manip:
            if self._is_legacy:
                ManipulatorFactory.destroy_manipulator(self._manip)
            else:
                self._manip.destroy()                
            self._manip = None

        if self._changed_fn:
            self._changed_fn = None

        
    @property
    def enabled(self):
        return self._manip.enabled

    @enabled.setter
    def enabled(self, ena):
        self._manip.enabled = ena



    @property
    def point(self):
        return self._manip.model.get_as_floats(self._manip.model.get_item("translate"))

    @point.setter
    def point(self, point):
        self._manip.model.set_floats(self._manip.model.get_item("translate"), 
                                     [point[0], point[1], point[2]])




    def set_changed_fn(self, fn):
        """ fn(action, manip)
            action: began=0,changed=1,ended=2,canceled=3
        """
        self._changed_fn = fn


    def _on_changed_fn(self, action, point):
        if self._changed_fn:
            self._changed_fn(action, self)




















"""
class PointTranslateModel(SimpleTransformModel):
    def __init__(self, point):
        super().__init__()

        self.set_operation(Operation.TRANSLATE)
        self.set_floats(self.get_item("translate"), point)
"""



class TranslateGesture(TranslateChangedGesture):
    def __init__(self, viewport, changed_fn=None, **kwargs):
        TranslateChangedGesture.__init__(self)
        self._vp = viewport
        self.changed_fn = changed_fn

    def destroy(self):
        self._vp = None
        self.changed_fn = None

    def __del__(self):
        self.destroy()


    def on_began(self):
        # print("TranslateGesture.on_began", self._vp.window_name)

        if not self.gesture_payload or not self.sender or not isinstance(self.gesture_payload, TranslateDragGesturePayload):
            return

        model = self.sender.model
        if not model:
            return

        pt = model.get_as_floats(model.get_item("translate"))
        self._begin_point = Gf.Vec3d(*pt)

        if self._vp.is_legacy:
            self._vp.temp_select_enabled(False)

        if self.changed_fn:
            self.changed_fn(0, self._begin_point)


    def on_ended(self):
        # print("TranslateGesture.on_ended")

        if not self.gesture_payload or not self.sender or not isinstance(self.gesture_payload, TranslateDragGesturePayload):
            return

        model = self.sender.model
        if not model:
            return

        if self.changed_fn:
            pt = model.get_as_floats(model.get_item("translate"))
            self.changed_fn(2, Gf.Vec3d(*pt))


    def on_canceled(self):
        # print("TranslateGesture.on_canceled")

        if not self.gesture_payload or not self.sender or not isinstance(self.gesture_payload, TranslateDragGesturePayload):
            return

        model = self.sender.model
        if not model:
            return

        if self.changed_fn:
            pt = model.get_as_floats(model.get_item("translate"))
            self.changed_fn(3, Gf.Vec3d(*pt))



    def on_changed(self):
        # print("TranslateGesture.on_changed")

        if not self.gesture_payload or not self.sender or not isinstance(self.gesture_payload, TranslateDragGesturePayload):
            return

        model = self.sender.model
        if not model:
            return

        translate = Gf.Vec3d(*self.gesture_payload.moved)

        point = self._begin_point + translate

        model.set_floats(model.get_item("translate"), [point[0], point[1], point[2]])

        if self.changed_fn:
            self.changed_fn(1, point)




