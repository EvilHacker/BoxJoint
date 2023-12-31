# Box Joint

This is a [Fusion 360](https://www.autodesk.com/products/fusion-360/overview) Add-In for creating CNC friendly box/finger joints.

## Editable Feature

The Box Joint appears as a single Feature in the Timeline.

* The Box Joint Feature can be edited after creation just like any other built-in feature.
* The joint will be automatically recomputed if any of the dependent bodies earlier in the Timeline are changed.

## CNC Friendly

The joint has been designed to be cuttable on a CNC machine.

* Can be cut flat from a single side on an 3-axis CNC machine.
* No voids are visible even though inside corners are rounded.

## Screen Shots

TODO

## Installation

This Add-In can be installed from either:

* The Fusion 360 App Store (link TBD).
* Using [GitHubToFusion360](https://apps.autodesk.com/FUSION/en/Detail/Index?id=789800822168335025). Paste the github link `https://github.com/EvilHacker/BoxJoint` into the [GitHubToFusion360](https://apps.autodesk.com/FUSION/en/Detail/Index?id=789800822168335025) Add-In.
* Download the Add-In from [github](https://codeload.github.com/EvilHacker/BoxJoint/zip/refs/heads/main) and extract to
	* `$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/` (Mac OS)
	* `C:\Users\%USER_NAME%\AppData\Roaming\Autodesk\Autodesk Fusion 360\API\AddIns` (Windows)
