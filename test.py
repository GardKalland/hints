
"""Overlay to display hints over an application window - Vimium Style."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import math

from gi import require_foreign, require_version

from hints.mouse_enums import MouseButton
from hints.utils import HintsConfig

require_version("Gdk", "3.0")
require_version("Gtk", "3.0")
require_foreign("cairo")
from cairo import FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
from gi.repository import Gdk, Gtk

if TYPE_CHECKING:
    from cairo import Context

    from hints.child import Child


class OverlayWindow(Gtk.Window):
    """Composite widget to overlay hints over a window - Vimium Style."""

    def __init__(
        self,
        x_pos: float,
        y_pos: float,
        width: float,
        height: float,
        config: HintsConfig,
        hints: dict[str, Child],
        mouse_action: dict[str, Any],
        is_wayland: bool = False,
    ):
        """Hint overlay constructor.

        :param x_pos: X window position.
        :param y_pos: Y window position.
        :param width: Window width.
        :param height: Window height.
        :param config: Hints config.
        :param hints: Hints to draw.
        :param mouse_action: Mouse action information.
        """
        super().__init__(Gtk.WindowType.POPUP)

        self.width = width
        self.height = height
        
        # Filter hints to reduce clutter - only show important elements
        self.hints = self.filter_important_hints(hints)
        
        self.hint_selector_state = ""
        self.mouse_action = mouse_action
        self.is_wayland = is_wayland

        # Vimium-style hint settings (based on their actual CSS)
        hints_config = config["hints"]
        
        # EXACT Vimium styling properties
        self.hint_padding_x = 3  # Horizontal padding
        self.hint_padding_y = 1  # Vertical padding
        self.hint_border_radius = 3  # Small rounded corners
        
        # Vimium uses very compact sizing
        self.hint_height = 13  # Exact Vimium height
        self.hint_width_padding = 6

        # Vimium font styling (matches their CSS exactly)
        self.hint_font_size = 12  # Vimium uses 12px
        self.hint_font_face = "Helvetica, Arial, sans-serif"
        self.hint_font_weight = 200  # Lighter weight
        
        # Vimium yellow color scheme (their signature look)
        # Background: Yellow gradient (from #FFF785 to #FFC542)
        self.hint_background_start_r = 1.0      # #FFF785 top
        self.hint_background_start_g = 0.97
        self.hint_background_start_b = 0.52
        
        self.hint_background_end_r = 1.0        # #FFC542 bottom
        self.hint_background_end_g = 0.77
        self.hint_background_end_b = 0.26
        
        # Text color: Dark for contrast (#302505)
        self.hint_font_r = 0.188  # #302505
        self.hint_font_g = 0.145
        self.hint_font_b = 0.020
        self.hint_font_a = 1.0

        # Pressed/matched character color (slightly darker)
        self.hint_pressed_font_r = 0.1
        self.hint_pressed_font_g = 0.1
        self.hint_pressed_font_b = 0.1
        self.hint_pressed_font_a = 1.0
        
        # Vimium uses uppercase hints
        self.hint_upercase = True

        # Border styling (Vimium has subtle borders - #C38A22)
        self.hint_border_r = 0.765   # #C38A22
        self.hint_border_g = 0.541
        self.hint_border_b = 0.133
        self.hint_border_a = 1.0

        # Shadow properties (Vimium has subtle shadows)
        self.shadow_offset_x = 0
        self.shadow_offset_y = 2
        self.shadow_blur = 4
        self.shadow_color_r = 0
        self.shadow_color_g = 0
        self.shadow_color_b = 0
        self.shadow_color_a = 0.1

        # key settings
        self.exit_key = config["exit_key"]
        self.hover_modifier = config["hover_modifier"]
        self.grab_modifier = config["grab_modifier"]

        self.hints_drawn_offsets: dict[str, tuple[float, float]] = {}

        # composite setup with improved transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # window setup - Vimium style (always on top, no decorations)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_accept_focus(True)
        self.set_sensitive(True)
        self.set_default_size(self.width, self.height)
        self.set_keep_above(True)  # Always on top like Vimium
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.move(x_pos, y_pos)

        self.drawing_area = Gtk.DrawingArea()

        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key_press)
        self.connect("show", self.on_show)
        self.drawing_area.connect("draw", self.on_draw)

        def put_in_frame(widget):
            frame = Gtk.Frame(label=None)
            frame.set_property("shadow_type", Gtk.ShadowType.NONE)
            frame.add(widget)
            return frame

        self.current_snippet = None

        vpaned = Gtk.VPaned()
        self.add(vpaned)
        vpaned.pack1(put_in_frame(self.drawing_area), True, True)

    def filter_important_hints(self, hints: dict[str, "Child"]) -> dict[str, "Child"]:
        """Filter hints like Vimium - only show clickable, important elements.
        
        :param hints: All available hints
        :return: Filtered hints dictionary
        """
        important_hints = {}
        
        for hint_key, child in hints.items():
            # Skip tiny elements (Vimium filters these)
            if child.width < 5 or child.height < 5:
                continue
            
            # Skip elements outside visible area
            x_loc, y_loc = child.relative_position
            if x_loc < -child.width or y_loc < -child.height:
                continue
            if x_loc > self.width or y_loc > self.height:
                continue
                
            # Get element role/type if available
            element_role = getattr(child, 'role', '').lower()
            
            # Vimium focuses on clickable elements
            clickable_roles = {
                'button', 'link', 'menuitem', 'tab', 'checkbox', 
                'radio button', 'text field', 'entry', 'combo box',
                'list item', 'tree item', 'toolbar button', 'tool bar button',
                'push button', 'toggle button', 'menu item'
            }
            
            # Skip non-interactive decorative elements
            skip_roles = {
                'separator', 'filler', 'scroll bar', 'status bar',
                'tool tip', 'border', 'frame', 'window', 'dialog'
            }
            
            # Include important clickable elements
            if any(role in element_role for role in clickable_roles):
                important_hints[hint_key] = child
                continue
                
            # Skip decorative elements
            if any(role in element_role for role in skip_roles):
                continue
            
            # Include elements with text content (likely clickable)
            if hasattr(child, 'name') and child.name and child.name.strip():
                important_hints[hint_key] = child
                continue
                
            # Include reasonably sized elements that might be clickable
            if child.width > 20 and child.height > 15:
                important_hints[hint_key] = child
        
        return important_hints

    def draw_rounded_rectangle(self, cr: Context, x: float, y: float, width: float, height: float, radius: float):
        """Draw a rounded rectangle path.
        
        :param cr: Cairo context
        :param x: X position
        :param y: Y position
        :param width: Rectangle width
        :param height: Rectangle height
        :param radius: Corner radius
        """
        degrees = math.pi / 180.0
        
        cr.new_sub_path()
        cr.arc(x + width - radius, y + radius, radius, -90 * degrees, 0 * degrees)
        cr.arc(x + width - radius, y + height - radius, radius, 0 * degrees, 90 * degrees)
        cr.arc(x + radius, y + height - radius, radius, 90 * degrees, 180 * degrees)
        cr.arc(x + radius, y + radius, radius, 180 * degrees, 270 * degrees)
        cr.close_path()

    def draw_vimium_gradient_background(self, cr: Context, x: float, y: float, width: float, height: float):
        """Draw Vimium's signature yellow gradient background with rounded corners.
        
        :param cr: Cairo context
        :param x: X position
        :param y: Y position
        :param width: Rectangle width
        :param height: Rectangle height
        """
        # Import cairo for gradient
        import cairo
        
        # Draw rounded rectangle path
        self.draw_rounded_rectangle(cr, x, y, width, height, self.hint_border_radius)
        
        # Create vertical gradient (top to bottom)
        pattern = cairo.LinearGradient(0, y, 0, y + height)
        pattern.add_color_stop_rgb(0, 
            self.hint_background_start_r, 
            self.hint_background_start_g, 
            self.hint_background_start_b)
        pattern.add_color_stop_rgb(1, 
            self.hint_background_end_r, 
            self.hint_background_end_g, 
            self.hint_background_end_b)
        
        cr.set_source(pattern)
        cr.fill()

    def draw_vimium_hint_box(self, cr: Context, x: float, y: float, width: float, height: float):
        """Draw hint box exactly like Vimium with shadow and border.
        
        :param cr: Cairo context
        :param x: X position
        :param y: Y position
        :param width: Rectangle width
        :param height: Rectangle height
        """
        # Draw shadow first (offset down)
        cr.save()
        cr.set_source_rgba(
            self.shadow_color_r,
            self.shadow_color_g,
            self.shadow_color_b,
            self.shadow_color_a
        )
        self.draw_rounded_rectangle(
            cr, 
            x + self.shadow_offset_x, 
            y + self.shadow_offset_y, 
            width, 
            height, 
            self.hint_border_radius
        )
        cr.fill()
        cr.restore()
        
        # Draw gradient background
        self.draw_vimium_gradient_background(cr, x, y, width, height)
        
        # Draw border (Vimium style)
        self.draw_rounded_rectangle(cr, x, y, width, height, self.hint_border_radius)
        cr.set_source_rgba(
            self.hint_border_r,
            self.hint_border_g,
            self.hint_border_b,
            self.hint_border_a
        )
        cr.set_line_width(1)
        cr.stroke()

    def calculate_vimium_position(self, child, hint_width: float, hint_height: float) -> tuple[float, float]:
        """Calculate position like Vimium - prefer top-left of element, avoid overlaps.
        
        :param child: Child element
        :param hint_width: Hint width
        :param hint_height: Hint height  
        :return: Optimal x, y position
        """
        x_loc, y_loc = child.relative_position
        
        # Vimium positioning strategy:
        # 1. Try to position at top-left corner of element
        # 2. If that would go off-screen, adjust to stay visible
        # 3. Add small offset to not cover the element completely
        
        hint_x = x_loc - 5  # Small offset left
        hint_y = y_loc - 5  # Small offset up
        
        # Keep hint on screen
        if hint_x < 0:
            hint_x = 0
        elif hint_x + hint_width > self.width:
            hint_x = self.width - hint_width
            
        if hint_y < 0:
            hint_y = 0
        elif hint_y + hint_height > self.height:
            hint_y = self.height - hint_height
        
        return hint_x, hint_y

    def on_draw(self, _, cr: Context):
        """Draw hints exactly like Vimium.

        :param cr: Cairo Context.
        """
        # Clear background (transparent)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        
        # Set Vimium font
        cr.select_font_face(self.hint_font_face.split(',')[0], FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD)
        cr.set_font_size(self.hint_font_size)

        # Track drawn positions to avoid overlaps
        drawn_positions = []

        for hint_value, child in self.hints.items():
            x_loc, y_loc = child.relative_position
            
            # Only draw hints that are in visible area
            if x_loc >= -child.width and y_loc >= -child.height and x_loc < self.width and y_loc < self.height:
                cr.save()
                
                # Prepare text
                utf8 = hint_value.upper() if self.hint_upercase else hint_value
                hint_state = (
                    self.hint_selector_state.upper()
                    if self.hint_upercase
                    else self.hint_selector_state
                )

                # Calculate text dimensions
                x_bearing, y_bearing, text_width, text_height, _, _ = cr.text_extents(utf8)
                
                # Vimium compact sizing
                hint_width = text_width + (self.hint_padding_x * 2)
                hint_height = self.hint_height

                # Vimium positioning
                hint_x, hint_y = self.calculate_vimium_position(child, hint_width, hint_height)
                
                # Avoid overlaps with already drawn hints
                for dx, dy, dw, dh in drawn_positions:
                    if (hint_x < dx + dw and hint_x + hint_width > dx and
                        hint_y < dy + dh and hint_y + hint_height > dy):
                        # Adjust position to avoid overlap
                        hint_y = dy + dh + 2
                        if hint_y + hint_height > self.height:
                            hint_y = dy - hint_height - 2
                
                drawn_positions.append((hint_x, hint_y, hint_width, hint_height))

                # Store offsets for click handling
                self.hints_drawn_offsets[hint_value] = (
                    hint_x + hint_width / 2 - x_loc,
                    hint_y + hint_height / 2 - y_loc,
                )

                # Draw Vimium-style hint box
                self.draw_vimium_hint_box(cr, hint_x, hint_y, hint_width, hint_height)

                # Calculate centered text position
                hint_text_x = hint_x + (hint_width / 2) - (text_width / 2 + x_bearing)
                hint_text_y = hint_y + (hint_height / 2) - (text_height / 2 + y_bearing)

                # Draw text with proper Vimium styling
                if hint_state and utf8.startswith(hint_state):
                    # Draw matched portion in different color
                    matched_width, _, _, _, _, _ = cr.text_extents(hint_state)
                    
                    # Draw unmatched portion first
                    unmatched = utf8[len(hint_state):]
                    if unmatched:
                        cr.move_to(hint_text_x + matched_width, hint_text_y)
                        cr.set_source_rgba(
                            self.hint_font_r,
                            self.hint_font_g,
                            self.hint_font_b,
                            self.hint_font_a,
                        )
                        cr.show_text(unmatched)
                    
                    # Draw matched portion on top
                    cr.move_to(hint_text_x, hint_text_y)
                    cr.set_source_rgba(
                        self.hint_pressed_font_r,
                        self.hint_pressed_font_g,
                        self.hint_pressed_font_b,
                        self.hint_pressed_font_a,
                    )
                    cr.show_text(hint_state)
                else:
                    # Draw entire text normally
                    cr.move_to(hint_text_x, hint_text_y)
                    cr.set_source_rgba(
                        self.hint_font_r,
                        self.hint_font_g,
                        self.hint_font_b,
                        self.hint_font_a,
                    )
                    cr.show_text(utf8)

                cr.restore()

    def update_hints(self, next_char: str):
        """Update hints on screen to eliminate options.

        :param next_char: Next character for hint_selector_state.
        """
        # Check if character is valid for hints
        next_char_upper = next_char.upper() if self.hint_upercase else next_char
        
        updated_hints = {}
        for hint, child in self.hints.items():
            if self.hint_upercase:
                if hint.upper().startswith(self.hint_selector_state.upper() + next_char_upper):
                    updated_hints[hint] = child
            else:
                if hint.startswith(self.hint_selector_state + next_char):
                    updated_hints[hint] = child

        if updated_hints:
            self.hints = updated_hints
            self.hint_selector_state += next_char_upper if self.hint_upercase else next_char

        self.drawing_area.queue_draw()

    def on_key_press(self, _, event):
        """Handle key presses :param event: Event object."""
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())

        # if keyval is bound, keyval, effective_group, level, consumed_modifiers
        _, keyval, _, _, consumed_modifiers = keymap.translate_keyboard_state(
            event.hardware_keycode,
            Gdk.ModifierType(event.state & ~Gdk.ModifierType.LOCK_MASK),
            1,
        )

        modifiers = (
            # current state, default mod mask, consumed modifiers
            event.state
            & Gtk.accelerator_get_default_mod_mask()
            & ~consumed_modifiers
        )

        keyval_lower = Gdk.keyval_to_lower(keyval)

        # ESC key handling
        if keyval == Gdk.KEY_Escape or keyval_lower == self.exit_key:
            Gtk.main_quit()
            return

        # Backspace handling - remove last character
        if keyval == Gdk.KEY_BackSpace:
            if self.hint_selector_state:
                self.hint_selector_state = self.hint_selector_state[:-1]
                # Rebuild hints from original set
                self.hints = self.filter_important_hints(self.hints)
                self.drawing_area.queue_draw()
            return

        if modifiers == self.hover_modifier:
            self.mouse_action.update({"action": "hover"})

        if modifiers == self.grab_modifier:
            self.mouse_action.update({"action": "grab"})

        if keyval_lower != keyval:
            self.mouse_action.update({"action": "click", "button": MouseButton.RIGHT})

        hint_chr = chr(keyval_lower)

        # Only process alphabetic characters for hints
        if hint_chr.isalpha():
            self.update_hints(hint_chr)

        # Handle numeric repeat counts
        if hint_chr.isdigit():
            self.mouse_action.update(
                {"repeat": int(f"{self.mouse_action.get('repeat', '')}{hint_chr}")}
            )

        # Check if we have a unique match
        if len(self.hints) == 1:
            hint_key = list(self.hints.keys())[0]
            if (self.hint_upercase and hint_key.upper() == self.hint_selector_state.upper()) or \
               (not self.hint_upercase and hint_key == self.hint_selector_state):
                Gdk.keyboard_ungrab(event.time)
                self.destroy()
                x, y = self.hints[hint_key].absolute_position
                x_offset, y_offset = self.hints_drawn_offsets[hint_key]
                self.mouse_action.update(
                    {
                        "action": self.mouse_action.get("action", "click"),
                        "x": x + x_offset,
                        "y": y + y_offset,
                        "repeat": self.mouse_action.get("repeat", 1),
                        "button": self.mouse_action.get("button", MouseButton.LEFT),
                    }
                )

    def on_show(self, window):
        """Setup window on show.

        Force keyboard grab to listen for keyboard events. Hide mouse so
        it does not block hints.

        :param window: Gtk Window object.
        """
        while (
            not self.is_wayland
            and Gdk.keyboard_grab(window.get_window(), False, Gdk.CURRENT_TIME)
            != Gdk.GrabStatus.SUCCESS
        ):
            pass

        Gdk.Window.set_cursor(
            self.get_window(),  # Gdk Window object
            Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "none"),
        )
