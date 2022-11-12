from omni.ui import color as cl

DEV_MODE = 0

# extension/window
WINDOW_NAME = "Model Exploder"
MENU_PATH = f"Tools/{WINDOW_NAME}"
SETTINGS_PATH = "persistent/exts/syntway.model_exploder/"
INFO_URL = "https://www.syntway.com/model_exploder/#how-to-use"

# ui
DISTANCE_LABEL = "Distance"
CENTER_LABEL = "Center"
SELECT_TO_EXPLODE_TEXT = "Start by selecting what to explode..."
SELECT_TO_USE_TEXT = "Click to use the {0} selected parts"
SELECTED_TEXT = "Exploding {0} parts"
DONE_TEXT = "Apply"
RESET_TEXT = "Cancel"
CENTER_TEXT = "Center"
RECENTER_TEXT = "Recenter"

OPTIONS_TITLE = "Options"
OPTIONS_DIST_MULT_LABEL = "Distance Multiplier"
OPTIONS_DIST_MULT_COMBO_VALUES = [
    ("1x", 1.),
    ("5x ", 5.),
    ("10x", 10.),
    ("100x", 100.)
]

OPTIONS_ACCEL_LABEL = "Acceleration from Center"
OPTIONS_ACCEL_MAX = 5.

OPTIONS_BOUNDS_ALPHA_LABEL = "Initial Bounds Visibility"
OPTIONS_BOUNDS_ALPHA_SETTING = "boundsAlpha"
OPTIONS_BOUNDS_ALPHA_DEFAULT = 0.5

OPTIONS_UNSELECT_ON_USE_LABEL = "Unselect Parts on Use"
OPTIONS_UNSELECT_ON_USE_SETTING = "unselectOnUse"
OPTIONS_UNSELECT_ON_USE_DEFAULT = True



TIMELINE_RESET_TEXT = "Timeline has changed: resetting exploded meshes..."


CENTER_COMBO_LABELS = [
    "Point",
    "X Axis",
    "Y Axis",  # up
    "Z Axis",  # up
    "XY Plane",  # ground
    "YZ Plane",
    "ZX Plane"  # ground
]
CENTER_COMBO_AXIS_FIRST = 1
CENTER_COMBO_AXIS_SUFFIX = " (Vertical)"

CENTER_COMBO_PLANE_FIRST = 4
CENTER_COMBO_PLANE_SUFFIX = " (Ground)"



# engine
CENTER_MANIP_LABEL_OFFSET = -11
CENTER_MANIP_LABEL_SIZE = 15

DEFAULT_CENTER_MODE = 0
CENTER_MODE_SETTING = "centerMode"

DEFAULT_DIST_MULT = 5.
DIST_MULT_SETTING = "distMult"

ACCEL_DEFAULT = 1.68
ACCEL_SETTING = "orderAccel"

DIST_EXP = 1.3
BOUNDS_BASE_AABB_COLOR = cl("#808080ff")  # rgba order


# tooltips
TOOLTIP_USE = "First select the models to explode, then click this button to use."
TOOLTIP_INFO = "Help and more info on this tool."

TOOLTIP_DIST = "Select the explosion distance. For larger distances, see Options - Distance Multiplier."

TOOLTIP_CENTER_MODE = """Select the explosion center type, which can be a point, an axis or a plane.
You can drag the Center manipulator directly in the viewport to change its position."""

TOOLTIP_RECENTER = "Toggle the Center manipulator in the viewport back to the centroid of the used shapes."

TOOLTIP_OPTIONS_ACCEL = """Exploded parts accelerate based on their initial distance from Center.
This setting controls how farthest parts accelerate more than nearest ones."""

TOOLTIP_OPTIONS_DIST = """Multiply the explosion distance selected in the above slider.
For smaller or larger explosion scales."""

TOOLTIP_OPTIONS_BOUNDS = """Visibility of the initial bounding box for the used shapes,
from transparent to fully visible."""

TOOLTIP_OPTIONS_UNSELECT = """When starting to use a group of selected parts,
should they be unselected for simpler visuals?"""

TOOLTIP_CANCEL = "Cancel the tool and leave parts in their initial positions."
TOOLTIP_APPLY = "Applies the current parts positions and adds an Undo-Redo state."