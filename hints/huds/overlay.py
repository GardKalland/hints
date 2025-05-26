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
        super().__init__(Gtk.WindowType.POPUP)
        self.x_pos = x_pos
        self.y_pos = y_pos
        self.width = width
        self.height = height
        self.all_hints = hints
        self.hints = self.generate_hint_labels(self.filter_important_hints(hints))
        self.hint_selector_state = ""
        self.mouse_action = mouse_action
        self.is_wayland = is_wayland

        # Vimium-style settings
        self.hint_padding_x = 3
        self.hint_padding_y = 1
        self.hint_border_radius = 3
        self.hint_height = 13
        self.hint_width_padding = 6
        self.hint_font_size = 12
        self.hint_font_face = "Helvetica, Arial, sans-serif"
        self.hint_font_weight = 200
        self.hint_background_start_r = 1.0
        self.hint_background_start_g = 0.97
        self.hint_background_start_b = 0.52
        self.hint_background_end_r = 1.0
        self.hint_background_end_g = 0.77
        self.hint_background_end_b = 0.26
        self.hint_font_r = 0.188
        self.hint_font_g = 0.145
        self.hint_font_b = 0.020
        self.hint_font_a = 1.0
        self.hint_pressed_font_r = 0.1
        self.hint_pressed_font_g = 0.1
        self.hint_pressed_font_b = 0.1
        self.hint_pressed_font_a = 1.0
        self.hint_upercase = True
        self.hint_border_r = 0.765
        self.hint_border_g = 0.541
        self.hint_border_b = 0.133
        self.hint_border_a = 1.0
        self.shadow_offset_x = 0
        self.shadow_offset_y = 2
        self.shadow_blur = 4
        self.shadow_color_r = 0
        self.shadow_color_g = 0
        self.shadow_color_b = 0
        self.shadow_color_a = 0.1

        self.exit_key = config["exit_key"]
        self.hover_modifier = config["hover_modifier"]
        self.grab_modifier = config["grab_modifier"]
        self.hints_drawn_offsets: dict[str, tuple[float, float]] = {}

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_accept_focus(True)
        self.set_sensitive(True)
        self.set_default_size(self.width, self.height)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.move(x_pos, y_pos)

        self.drawing_area = Gtk.DrawingArea()
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key_press)
        self.connect("show", self.on_show)
        self.drawing_area.connect("draw", self.on_draw)

        def frame_wrap(w):
            frame = Gtk.Frame(label=None)
            frame.set_property("shadow_type", Gtk.ShadowType.NONE)
            frame.add(w)
            return frame

        vpaned = Gtk.VPaned()
        self.add(vpaned)
        vpaned.pack1(frame_wrap(self.drawing_area), True, True)

    def filter_important_hints(self, hints: dict[str, Child]) -> dict[str, Child]:
        """Filter hints like Vimium - include sidebar and other UI elements."""
        important_hints: dict[str, Child] = {}
        seen: set[tuple[int, int]] = set()
        for key, child in hints.items():
            # Skip elements that are too small
            if child.width < 8 or child.height < 8:
                continue

            x, y = child.relative_position
            # Bounds check - include elements partially visible
            if x < -child.width or y < -child.height or x > self.width + child.width or y > self.height + child.height:
                continue

            # Retrieve role and name
            role = getattr(child, 'role', '').lower() if hasattr(child, 'role') else ''
            name = getattr(child, 'name', '').strip() if hasattr(child, 'name') else ''

            # Skip explicit non-interactive UI elements
            skip_keywords = ('separator', 'filler', 'scroll bar', 'status bar', 'decoration', 'frame', 'border')
            if any(k in role for k in skip_keywords):
                continue

            # Determine clickability: if role is known, use keywords; if unknown, assume clickable (to catch sidebar items)
            click_keywords = ('button', 'link', 'menu', 'tab', 'entry', 'text', 'combo', 'check', 'radio', 'toggle', 'tool', 'item', 'cell', 'option', 'choice')
            is_clickable = True if not role else any(k in role for k in click_keywords)

            # Deduplicate by rounded position
            pos_key = (round(x / 10), round(y / 10))
            if pos_key in seen:
                continue

            # Include hinge if:
            # - Likely clickable
            # - Has a meaningful name
            # - Or is sufficiently large (to catch sidebars and toolbars)
            if is_clickable or (name and child.width > 20 and child.height > 15) or (child.width > 40 and child.height > 20):
                seen.add(pos_key)
                important_hints[key] = child

        return important_hints

    def generate_hint_labels(self, hints: dict[str, Child]) -> dict[str, Child]:
        chars = 'SADFJKLEWCMPGH'
        count = len(hints)
        length = 1
        while len(chars)**length < count:
            length += 1
        labels = []
        if length == 1:
            labels = list(chars[:count])
        else:
            def rec(p,l):
                if l==0:
                    labels.append(p)
                    return
                for c in chars:
                    if len(labels)<count:
                        rec(p+c,l-1)
            rec('', length)
        return {labels[i]: child for i, child in enumerate(hints.values())}

    def calculate_vimium_position(self, child, w,h) -> tuple[float,float]:
        x,y = child.relative_position
        x -=5; y-=5
        x = max(0,min(x,self.width-w))
        y = max(0,min(y,self.height-h))
        return x,y

    def draw_rounded_rectangle(self, cr: Context, x,y,w,h,radius:float):
        deg=math.pi/180.0
        cr.new_sub_path()
        cr.arc(x+w-radius,y+radius,radius,-90*deg,0*deg)
        cr.arc(x+w-radius,y+h-radius,radius,0*deg,90*deg)
        cr.arc(x+radius,y+h-radius,radius,90*deg,180*deg)
        cr.arc(x+radius,y+radius,radius,180*deg,270*deg)
        cr.close_path()

    def draw_vimium_gradient_background(self,cr,x,y,w,h):
        import cairo
        self.draw_rounded_rectangle(cr,x,y,w,h,self.hint_border_radius)
        pat=cairo.LinearGradient(0,y,0,y+h)
        pat.add_color_stop_rgb(0,self.hint_background_start_r,self.hint_background_start_g,self.hint_background_start_b)
        pat.add_color_stop_rgb(1,self.hint_background_end_r,self.hint_background_end_g,self.hint_background_end_b)
        cr.set_source(pat); cr.fill()

    def draw_vimium_hint_box(self,cr,x,y,w,h):
        cr.save(); cr.set_source_rgba(self.shadow_color_r,self.shadow_color_g,self.shadow_color_b,self.shadow_color_a)
        self.draw_rounded_rectangle(cr,x+self.shadow_offset_x,y+self.shadow_offset_y,w,h,self.hint_border_radius)
        cr.fill(); cr.restore()
        self.draw_vimium_gradient_background(cr,x,y,w,h)
        self.draw_rounded_rectangle(cr,x,y,w,h,self.hint_border_radius)
        cr.set_source_rgba(self.hint_border_r,self.hint_border_g,self.hint_border_b,self.hint_border_a)
        cr.set_line_width(1); cr.stroke()

    def on_draw(self, _, cr: Context):
        cr.set_source_rgba(0,0,0,0); cr.paint()
        cr.select_font_face(self.hint_font_face.split(',')[0], FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD)
        cr.set_font_size(self.hint_font_size)
        drawn=[]; count=0
        for key,child in self.hints.items():
            x0,y0=child.relative_position
            cr.save()
            txt=key.upper() if self.hint_upercase else key
            state=self.hint_selector_state.upper() if self.hint_upercase else self.hint_selector_state
            xb,yb,tw,th,_,_=cr.text_extents(txt)
            w=tw+2*self.hint_padding_x; h=self.hint_height
            x,y=self.calculate_vimium_position(child,w,h)
            if count<5: print(f"Drawing hint '{key}' at ({x}, {y}) for element at ({x0}, {y0})")
            for dx,dy,dw,dh in drawn:
                if x<dx+dw and x+w>dx and y<dy+dh and y+h>dy:
                    y=dy+dh+2
                    if y+h>self.height: y=dy-h-2
            drawn.append((x,y,w,h)); self.hints_drawn_offsets[key]=(x+w/2-x0,y+h/2-y0)
            self.draw_vimium_hint_box(cr,x,y,w,h)
            tx=x+(w/2)-(tw/2+xb); ty=y+(h/2)-(th/2+yb)
            if state and txt.startswith(state):
                mw,_,_,_,_,_=cr.text_extents(state)
                unmatched=txt[len(state):]
                if unmatched:
                    cr.move_to(tx+mw,ty); cr.set_source_rgba(self.hint_font_r,self.hint_font_g,self.hint_font_b,self.hint_font_a); cr.show_text(unmatched)
                cr.move_to(tx,ty); cr.set_source_rgba(self.hint_pressed_font_r,self.hint_pressed_font_g,self.hint_pressed_font_b,self.hint_pressed_font_a); cr.show_text(state)
            else:
                cr.move_to(tx,ty); cr.set_source_rgba(self.hint_font_r,self.hint_font_g,self.hint_font_b,self.hint_font_a); cr.show_text(txt)
            cr.restore(); count+=1

    def update_hints(self,next_char:str):
        c=next_char.upper() if self.hint_upercase else next_char
        new={k:v for k,v in self.hints.items() if (k.upper() if self.hint_upercase else k).startswith((self.hint_selector_state+c))}
        if new: self.hints=new; self.hint_selector_state+=c
        self.drawing_area.queue_draw()

    def on_key_press(self,_,event):
        keymap=Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        _,keyval,_,_,cons=keymap.translate_keyboard_state(event.hardware_keycode,event.state & ~Gdk.ModifierType.LOCK_MASK,1)
        mods=event.state & Gtk.accelerator_get_default_mod_mask() & ~cons
        key_lower=Gdk.keyval_to_lower(keyval)
        if keyval==Gdk.KEY_Escape or key_lower==self.exit_key: Gtk.main_quit(); return
        if keyval==Gdk.KEY_BackSpace and self.hint_selector_state:
            self.hint_selector_state=self.hint_selector_state[:-1]; self.hints=self.generate_hint_labels(self.filter_important_hints(self.all_hints)); self.drawing_area.queue_draw(); return
        if mods==self.hover_modifier: self.mouse_action["action"]="hover"
        if mods==self.grab_modifier: self.mouse_action["action"]="grab"
        if key_lower!=keyval: self.mouse_action.update({"action":"click","button":MouseButton.RIGHT})
        ch=chr(key_lower)
        if ch.isalpha(): self.update_hints(ch)
        if ch.isdigit(): self.mouse_action["repeat"]=int(str(self.mouse_action.get("repeat",""))+ch)
        if len(self.hints)==1:
            hint=list(self.hints.keys())[0]
            if (self.hint_upercase and hint.upper()==self.hint_selector_state) or (not self.hint_upercase and hint==self.hint_selector_state):
                Gdk.keyboard_ungrab(event.time); self.destroy(); x_abs,y_abs=self.hints[hint].absolute_position; x_off,y_off=self.hints_drawn_offsets[hint]
                self.mouse_action.update({"action":self.mouse_action.get("action","click"),"x":x_abs+x_off,"y":y_abs+y_off,"repeat":self.mouse_action.get("repeat",1),"button":self.mouse_action.get("button",MouseButton.LEFT)})

    def on_show(self,window):
        while not self.is_wayland and Gdk.keyboard_grab(window.get_window(),False,Gdk.CURRENT_TIME)!=Gdk.GrabStatus.SUCCESS: pass
        Gdk.Window.set_cursor(self.get_window(),Gdk.Cursor.new_from_name(Gdk.Display.get_default(),"none"))
