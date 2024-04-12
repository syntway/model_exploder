"""
Notes:
"""

import omni.kit
import omni.usd

from pxr import Gf, Sdf, Usd, UsdGeom


VERSION = 15

XFORM_OP_TRANSLATE_TYPE_TOKEN = UsdGeom.XformOp.GetOpTypeToken(UsdGeom.XformOp.TypeTranslate)
XFORM_OP_TRANSLATE_ATTR_NAME = "xformOp:" + XFORM_OP_TRANSLATE_TYPE_TOKEN


def get_prim_transform(prim,
                       with_pivot,
                       xform_cache=None,
                       time_code=Usd.TimeCode.Default()):

    """Returns a prim's local transformation, converting mesh points into parent-space coords.
    with_pivot=True: returns GetLocalTransformation, where pivot and pivot^-1 are included into the translation.
    with_pivot=False will set translation to the actual translate XformOp.
    If no pivot is set, returns GetLocalTransformation()
    """

    if xform_cache is None:
        xform_cache = UsdGeom.XformCache(time_code)

    mat, _ = xform_cache.GetLocalTransformation(prim)

    if with_pivot:
        return mat

    # remove pivot from local transform
    attr_name = XFORM_OP_TRANSLATE_ATTR_NAME
    op_attr = prim.GetAttribute(attr_name + ":pivot")
    if not op_attr:  # no pivot, return mat
        return mat

    op_attr = prim.GetAttribute(attr_name)
    if op_attr:
        op = UsdGeom.XformOp(op_attr)
        if op:
            trans = op.Get(time_code)
            if trans is not None:
                mat.SetTranslateOnly(make_vec3_for_matrix4(mat, trans))
                return mat

    # translation not found: set to identity translate
    mat.SetTranslateOnly(make_vec3_for_matrix4(mat, 0, 0, 0))
    return mat






def set_prim_transform(prim, mat, 
                       sdf_change_block=1,
                       time_code=Usd.TimeCode.Default()):
    """sdf_change_block: 0: don't use, 1: use locally, 2: assume already began"""

    sdf_change_block = 0

    stage = prim.GetStage()

    if sdf_change_block == 1:
        Sdf.BeginChangeBlock()

    xform = UsdGeom.Xformable(prim)
    ops = xform.GetOrderedXformOps()
    for op in ops:

        if op.GetOpType() == UsdGeom.XformOp.TypeTransform:
            _set_xform_op_time_code(op, mat, time_code, stage)

            if sdf_change_block == 1:
                Sdf.EndChangeBlock()
            return


    def get_or_add(op_type, prec):
        type_token = UsdGeom.XformOp.GetOpTypeToken(op_type)
        attr_name = "xformOp:" + type_token

        op_attr = prim.GetAttribute(attr_name)
        if op_attr:
            op = UsdGeom.XformOp(op_attr)
            if op:
                return op

        if sdf_change_block >= 1:
            Sdf.EndChangeBlock()

        op = xform.AddXformOp(op_type, prec)

        if sdf_change_block >= 1:
            Sdf.BeginChangeBlock()
        return op


    # not a transform: decompose matrix and set various S,R,T as needed
    _, _, scale, rot_mat, trans, _ = mat.Factor()
    rot_mat.Orthonormalize(False)
    rot = rot_mat.ExtractRotation()
    new_ops = []

    # translation
    op = get_or_add(UsdGeom.XformOp.TypeTranslate, UsdGeom.XformOp.PrecisionDouble)
    if op:
        _set_xform_op_time_code(op, trans, time_code, stage)
        new_ops.append(op)
        

    # scale/rotate pivot (a translate)
    pivot_op = None
    attr_name = XFORM_OP_TRANSLATE_ATTR_NAME + ":pivot"
    op_attr = prim.GetAttribute(attr_name)
    if op_attr:
        pivot_op = UsdGeom.XformOp(op_attr)
        if pivot_op:
            new_ops.append(pivot_op)


    # rotation: pick first type
    rot_type, rot_prec = UsdGeom.XformOp.TypeRotateXYZ, UsdGeom.XformOp.PrecisionFloat
    for op in ops:
        op_type = op.GetOpType()
        if op_type >= UsdGeom.XformOp.TypeRotateX and op_type <= UsdGeom.XformOp.TypeOrient:
            rot_type, rot_prec = op_type, op.GetPrecision()
            break


    def rot_get_or_add(rot_type,
                       axis_0, axis_1, axis_2,
                       x, y, z,
                       rot_prec
                       ):
        angles = rot.Decompose(axis_0, axis_1, axis_2)
        rot_vals = Gf.Vec3f(angles[x], angles[y], angles[z])  # unscramble to x,y,z order that op.Set() needs
        op = get_or_add(rot_type, rot_prec)
        if op:
            _set_xform_op_time_code(op, rot_vals, time_code, stage)
            new_ops.append(op)


    # single rotation?
    if rot_type >= UsdGeom.XformOp.TypeRotateX and rot_type <= UsdGeom.XformOp.TypeRotateZ:

        angles = rot.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())

        op = get_or_add(UsdGeom.XformOp.TypeRotateX, rot_prec)
        if op:
            _set_xform_op_time_code(op, angles[2], time_code, stage)
            new_ops.append(op)

        op = get_or_add(UsdGeom.XformOp.TypeRotateY, rot_prec)
        if op:
            _set_xform_op_time_code(op, angles[1], time_code, stage)
            new_ops.append(op)

        op = get_or_add(UsdGeom.XformOp.TypeRotateZ, rot_prec)
        if op:
            _set_xform_op_time_code(op, angles[0], time_code, stage)
            new_ops.append(op)

    # quaternion?
    elif rot_type == UsdGeom.XformOp.TypeOrient:
        type_token = UsdGeom.XformOp.GetOpTypeToken(rot_type)
        attr_name = "xformOp:" + type_token

        op_attr = prim.GetAttribute(attr_name)
        if op_attr:
            op = UsdGeom.XformOp(op_attr)
            if op:
                _set_xform_op_time_code(op, rot.GetQuat(), time_code, stage)
                new_ops.append(op)

    # triple rotation?
    elif rot_type == UsdGeom.XformOp.TypeRotateXZY:
        rot_get_or_add(rot_type,
                       Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis(), Gf.Vec3d.XAxis(),
                       2, 0, 1,
                       rot_prec)

    elif rot_type == UsdGeom.XformOp.TypeRotateYXZ:
        rot_get_or_add(rot_type,
                       Gf.Vec3d.ZAxis(), Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(),
                       1, 2, 0,
                       rot_prec)

    elif rot_type == UsdGeom.XformOp.TypeRotateYZX:
        rot_get_or_add(rot_type,
                       Gf.Vec3d.XAxis(), Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(),
                       0, 2, 1,
                       rot_prec)

    elif rot_type == UsdGeom.XformOp.TypeRotateZXY:
        rot_get_or_add(rot_type,
                       Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis(), Gf.Vec3d.ZAxis(),
                       1, 0, 2,
                       rot_prec)

    elif rot_type == UsdGeom.XformOp.TypeRotateZYX:
        rot_get_or_add(rot_type,
                       Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis(),
                       0, 1, 2,
                       rot_prec)

    else:  # just assume TypeRotateXYZ for any other
        rot_get_or_add(rot_type,
                       Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis(),
                       2, 1, 0,
                       rot_prec)

    # scale
    op = get_or_add(UsdGeom.XformOp.TypeScale, UsdGeom.XformOp.PrecisionFloat)
    if op:
        _set_xform_op_time_code(op, scale, time_code, stage)
        new_ops.append(op)

    # pivot_op^-1
    if pivot_op is not None:
        for op in ops:
            if op.IsInverseOp() and  \
               op.GetOpType() == UsdGeom.XformOp.TypeTranslate and  \
               is_pivot_xform_op_name_suffix(op.GetOpName()):
                new_ops.append(op)
                break


    # and finally set new ops into xform
    xform.SetXformOpOrder(new_ops, xform.GetResetXformStack())

    if sdf_change_block == 1:
        Sdf.EndChangeBlock()





"""
Note: touch_prim_xform() doesn't work, probably because the value is equal and caches are not rebuilt.
But this does:

lmat = get_prim_transform(prim, False, xform_cache, time_code)
cmd = TransformPrimCommand(path=path, new_transform_matrix=lmat, time_code=time_code)
#slower: cmd = TransformPrimSRTCommand(path=path, time_code=time_code)
cmd.do()


--------------------
def touch_prim_xform(prim, 
                     sdf_change_block=1,
                     time_code=Usd.TimeCode.Default()):
    #sdf_change_block: 0: don't use, 1: use locally, 2: assume already began

    if sdf_change_block == 1:
        Sdf.BeginChangeBlock()

    xform = UsdGeom.Xformable(prim)
    ops = xform.GetOrderedXformOps()
    for op in ops:
        if not op.IsInverseOp():
            op.Set(op.Get(time_code), time_code)
            break

    if sdf_change_block == 1:
        Sdf.EndChangeBlock()
"""











def get_prim_translation(prim, 
                         time_code=Usd.TimeCode.Default()):

    # remove pivot from local transform
    op_attr = prim.GetAttribute(XFORM_OP_TRANSLATE_ATTR_NAME)
    if op_attr:
        op = UsdGeom.XformOp(op_attr)
        if op:
            trans = op.Get(time_code)
            if trans is not None:
                return Gf.Vec3d(trans)

    # translation not found: return identity
    return Gf.Vec3d(0.)



def set_prim_translation(prim, trans,
                         sdf_change_block=1,
                         time_code=Usd.TimeCode.Default()):
    """sdf_change_block: 0: don't use, 1: use locally, 2: assume already began"""
    # print(prim.GetPath().pathString)

    sdf_change_block = 0

    mat_op = trans_op = None
    xform = UsdGeom.Xformable(prim)
    for op in xform.GetOrderedXformOps():
        op_type = op.GetOpType()
        if op_type == UsdGeom.XformOp.TypeTransform:
            mat_op = op
            break
        elif op_type == UsdGeom.XformOp.TypeTranslate and not is_pivot_xform_op_name_suffix(op.GetOpName()):  # op.SplitName()
            # simple translation, not pivot/invert
            trans_op = op
            break

    if mat_op:  # has matrix op
        if sdf_change_block == 1:
            Sdf.BeginChangeBlock()

        mat = Gf.Matrix4d()
        mat.SetTranslate(trans)

        stage = prim.GetStage()
        _set_xform_op_time_code(mat_op, mat, time_code, stage)

    else:  # set or add a translation xform op
        stage = prim.GetStage()

        # can't just set attr as order might not have been set
        if not trans_op:
            if sdf_change_block == 2:
                Sdf.EndChangeBlock()

            trans_op = _prepend_xform_op(xform, 
                                         UsdGeom.XformOp.TypeTranslate,
                                         get_xform_op_precision(trans),
                                         time_code, stage)

            if sdf_change_block == 2:
                Sdf.BeginChangeBlock()

        if sdf_change_block == 1:
            Sdf.BeginChangeBlock()

        _set_xform_op_time_code(trans_op, trans, time_code, stage)

    if sdf_change_block == 1:
        Sdf.EndChangeBlock()



def set_prim_translation_fast(prim, trans, 
                              sdf_change_block=1,
                              time_code=Usd.TimeCode.Default()):

    """
    As set_translation() but won't copy time samples from weaker layers.

    sdf_change_block: 0: don't use, 1: use locally, 2: assume already began
    see: https://graphics.pixar.com/usd/release/api/class_sdf_change_block.html
    """

    sdf_change_block = 0

    if prim.HasAttribute("xformOp:mat"):  # has matrix op
        if sdf_change_block == 1:
            Sdf.BeginChangeBlock()

        at = prim.GetAttribute("xformOp:mat")

        if not at.GetNumTimeSamples():
            time_code = Usd.TimeCode.Default()

        mat = at.Get(time_code)
        mat.SetTranslateOnly(trans)
        at.Set(mat, time_code)

    else:  # set or add a translation xform op
        # can't just set attr as order might not have been set
        attr = prim.GetAttribute("xformOp:translate")
        op = UsdGeom.XformOp(attr)
        if not op:
            if sdf_change_block == 2:
                Sdf.EndChangeBlock()

            stage = prim.GetStage()
            xform = UsdGeom.Xformable(prim)
            op = _prepend_xform_op(xform, 
                                   UsdGeom.XformOp.TypeTranslate,
                                   get_xform_op_precision(trans),
                                   time_code, stage)

            if sdf_change_block == 2:
                Sdf.BeginChangeBlock()

        if sdf_change_block == 1:
            Sdf.BeginChangeBlock()

        if not op.GetNumTimeSamples():
            time_code = Usd.TimeCode.Default()

        op.Set(trans, time_code)  # Gf.Vec3d()

    if sdf_change_block == 1:
        Sdf.EndChangeBlock()












def _set_xform_op_time_code(xform_op, value, time_code, stage):

    prev = xform_op.Get(time_code)

    if not xform_op.GetNumTimeSamples():  # no time samples
        time_code = Usd.TimeCode.Default()

    if prev is None:
        if not time_code.IsDefault():
            omni.usd.copy_timesamples_from_weaker_layer(stage, xform_op.GetAttr())

        xform_op.Set(value, time_code)

    else:
        value_type = type(prev)  # to preserve existing value type

        if not time_code.IsDefault():
            omni.usd.copy_timesamples_from_weaker_layer(stage, xform_op.GetAttr())

        xform_op.Set(value_type(value), time_code)



def _prepend_xform_op(xform, op_type, prec, time_code, stage):
    # print("pre", _get_xform_op_order(xform))

    prev_ops = xform.GetOrderedXformOps()

    xform.SetXformOpOrder([])
    # print("mid", _get_xform_op_order(xform))

    new_op = xform.AddXformOp(op_type, prec)

    for op in prev_ops:
        suffix = get_xform_op_name_suffix(op.GetOpName())
        inverse = op.IsInverseOp()
        new = xform.AddXformOp(op.GetOpType(), op.GetPrecision(), 
                               suffix,
                               inverse)
        if not inverse:
            value = op.Get(time_code)
            if value is not None:
                _set_xform_op_time_code(new, value, time_code, stage)

    # print("post", _get_xform_op_order(xform))

    return new_op



def get_xform_op_precision(t):
    if isinstance(t, Gf.Matrix4d) or isinstance(t, Gf.Vec3d):
        return UsdGeom.XformOp.PrecisionDouble
    else:
        return UsdGeom.XformOp.PrecisionFloat




def get_vec3_type_for_matrix4(mat):
    if isinstance(mat, Gf.Matrix4d):
        return Gf.Vec3d
    else:
        return Gf.Vec3f


def make_vec3_for_matrix4(mat, x, y=None, z=None):
    t = get_vec3_type_for_matrix4(mat)
    if y is None:
        return t(x[0], x[1], x[2])
    else:
        return t(x, y, z)







def _get_xform_op_order(xform):
    out = ""
    for op in xform.GetOrderedXformOps():
        out += op.GetOpName() + ","
    return out


XFORM_OP_INVERSE_PREFIX = "!invert!"


def is_xform_op_name_inverse(op_name):
    return op_name.startswith(XFORM_OP_INVERSE_PREFIX)


def get_xform_op_name_suffix(op_name):
    # or 
    if is_xform_op_name_inverse(op_name):
        op_name = op_name.split(XFORM_OP_INVERSE_PREFIX, 1)[1]

    if op_name.startswith("xformOp:"):
        tags = op_name.split(":", 2)
        if len(tags) >= 3:
            return tags[2]

    return ""


def is_pivot_xform_op_name_suffix(op_name):
    """or faster: 
    "xformOp:" in op_name and "pivot" in op_name
    """

    suffix = get_xform_op_name_suffix(op_name)
    if suffix != "":
        return suffix == "pivot"
    else:
        return False



def create_edit_context(path, stage):
    """Unsafe from threading? No issues so far:
    https://graphics.pixar.com/usd/release/api/class_usd_edit_context.html#details
    """
    layer, prim = omni.usd.find_spec_on_session_or_its_sublayers(stage, path)
    if not prim or not layer:
        return Usd.EditContext(stage)

    if prim.specifier == Sdf.SpecifierDef:
        return Usd.EditContext(stage, Usd.EditTarget(layer))
    else:
        return Usd.EditContext(stage)

