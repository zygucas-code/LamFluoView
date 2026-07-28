# LamFluoView

Transparent Image Viewer Operation Manual
1. Software Launch and Initial Interface
1.1 Launch Methods
If distributed as a Python script: Open the command line, navigate to the directory containing the script, enter python checkFIBcolorfigure_V12.5.1.py, and press Enter to launch the program. If distributed as a packaged EXE or BAT file, double-click the LamFluoView icon to start the software directly.
After launching, the software window stays on top by default. The initial interface is shown in Figure 1. The top bar contains background loading buttons, background scaling controls and window management buttons; a title bar sits in the middle; various function operation controls are arranged below the title; the bottom section serves as the image display canvas.
Figure 1 Initial Interface
2. Background Image Loading and Configuration
2.1 Load Background Image
Click the Load Background Image button on the upper left of the top bar (marked with a red box in Figure 2).
The software will automatically export the current montage image from the SerialEM module directory as the background layer. Once loaded successfully, the background image will appear in the display area. If loading fails, error logs will be printed in the backend console.
Figure 2 Load Background Image Button
2.2 Adjust Background Scaling
Locate the QDoubleSpinBox widget for background scaling to the right of the Load Background Image button (red box in Figure 3).
Input a numerical value directly (valid range: 1–1000) or adjust the value using the widget’s up/down arrows. The background image will rescale in real time according to the set factor.
Figure 3 Background Scaling Adjustment
3. Fluorescence Image Loading and Parameter Tuning
3.1 Load Fluorescence Image
Click the Load Image button on the left side of the central control panel (red box in Figure 4).
In the pop-up file selection dialog, select the target fluorescence image (supported formats: .png, .jpg, .bmp, etc.) and click Open. The fluorescence image will be imported to the display area with a default transparency value of 50%.
Figure 4 Load Fluorescence Image
3.2 Modify Fluorescence Image Parameters
Rotation Adjustment
Find the QDoubleSpinBox widget labeled Rotation (red box in Figure 5). Input a value (range: -360 to 360) or adjust via the arrow keys; the fluorescence image rotates instantly to the specified angle.
Figure 5 Rotation Control
Transparency Adjustment
To the right of the rotation widget is the QDoubleSpinBox for Transparency (red box in Figure 6). Input a value ranging from 0 to 100, or adjust via arrows. Lower values correspond to higher transparency, allowing underlying desktop windows to be visible.
Users may also click the Toggle Transparency (Ctrl+H) button or press the Ctrl+H shortcut to quickly switch transparency between 0% and the previously set value.
Figure 6 Transparency Adjustment
Scaling Adjustment
The Scaling QDoubleSpinBox is positioned to the right of the transparency widget (red box in Figure 7). Enter a value between 1 and 5000, or adjust via arrows. Users can also scroll the mouse wheel over the image display area to modify the scale (20 units per scroll tick). The fluorescence image updates its scale in real time.
Figure 7 Scaling Adjustment
4. Image Alignment and Locking
4.1 Image Alignment
Tune the rotation, scaling and transparency parameters of the fluorescence image separately. Additionally, click and hold the left mouse button over the display canvas to drag the fluorescence overlay, aligning its key features with the background TEM montage.
4.2 Image Locking
Once alignment is complete, click the Lock button in the lower control panel (red box in Figure 8). The button will activate to indicate locked status.
After locking:
Dragging the canvas pans both the fluorescence overlay and background synchronously.
Modifying the scaling factor of either layer scales both images proportionally to preserve precise alignment.
Click the Lock button a second time to disable locking and restore independent adjustment for each layer.
Figure 8 Lock Button
5. Point Marking and Coordinate Synchronization
5.1 Enable Point Marking Mode
Click the Add Points button to the right of the Lock button (red box in Figure 9). The button activates to enter marking mode, and the software automatically retrieves the UniqueID from SerialEM.
Figure 9 Position of Add Points Button
5.2 Point Marking and Coordinate Sync
Left-click target positions on the image display canvas to place markers. An ellipse will render at each clicked coordinate; ellipse dimensions are defined by the configuration file and current scaling factor, representing electron beam spot properties. The coordinates of each marker are simultaneously transmitted to SerialEM for subsequent imaging and data acquisition workflows.
Each mouse click generates a new marker. All marked points remain stored within the software until the background image is reloaded or the program is closed.
6. Image Export and Saving
When the fluorescence overlay and background layer are locked, the software automatically exports three files to the folder where the original fluorescence image is stored:
Cropped transparent fluorescence layer: [OriginalFluoName]_croped.jpg
Background TEM montage: [OriginalFluoName]_TEM.jpg
Composite overlaid image: [OriginalFluoName]_combined.jpg
The save directory path is printed to the backend console upon completion.
7. Window Controls
Minimize Window: Click the minus “−” button at the top-right corner (red box in Figure 10) to minimize the software window to the system taskbar.
Close Window: Click the cross “×” button to the right of the minimize button (red box in Figure 10) to exit the software entirely.
Figure 10 Window Control Buttons
