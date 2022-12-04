# Model Exploder Tool
Model Exploder separates a 3D model into its parts for a better view of their relationship and how they fit together.

Model separation is done as if by a small controlled explosion emanating from its center. This is often known as an exploded-view of the model.

Exploded-views can be used to understand a model from its components and can also be used to create drawings for parts catalogs or assembly/maintenance/instruction information.


## Features
- Easy to use: select a model, click the Use button and move the Distance slider.
- Includes several ways to explode the model around a central point, axis or plane.
- Interactive editing of the explosion center: just drag the "Center" manipulator in the viewport.
- Works with meshes, USD Shapes, references/payloads. Point instances and skeletons are moved as a whole.
- Adds Undo-Redo state when applying changes.
- Works with NVIDIA's Omniverse Create, Code 2022+ or any other Kit-based apps. Compatible with multiple viewports and with the legacy viewport of older Omniverse versions.


### Tips
- Model Exploder is available in the Tools menu.
- Click the ( i ) button for help and more information.
- On complex models, the first interaction with the Distance slider might take a few seconds - next ones are much faster.
- If model parts do not separate and remain joined to each other:
  - Make sure model is divided in parts (meshes, USD shapes, etc), as this tools works by moving those parts.
  - With the Distance slider away from its leftmost position, move the Center manipulator in the viewport into the middle of the parts group.
  - Separate the group of "stuck" parts before separating the rest of the model.
- The initial bounds preview and center manipulator work in the active (last used) viewport. To change viewports, close the Model Exploder window and open again after using the new viewport.


## Credits
This tool is developed by Syntway, the VR/Metaverse tools division of FaronStudio: www.syntway.com

Uses icons from SVG Repo: www.svgrepo.com
3D model used in the preview snapshot is from mdesigns100: 3dexport.com/free-3dmodel-residential-building-model-296192.htm

