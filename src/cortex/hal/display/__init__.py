"""Display HAL service — LCD, button gestures, LED control.

Public API:
  - WhisplayDisplayService: Full LCD + LED display service
  - FrameRenderer: Pure Pillow frame rendering (no hardware)
  - TextRenderer: Word-wrapped text rendering
  - RenderLoop: Async 30 FPS render loop
"""
