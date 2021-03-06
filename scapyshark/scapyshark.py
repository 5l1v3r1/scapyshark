#!/usr/bin/env python3

import argparse
import os
import scapy.all
import urwid
from .scrolling import ScrollingListBox
from .sniffer import Sniffer
from .version import version

palette = [
    ('body','black','dark cyan', 'standout'),
    ('header','light gray', 'black'),
    ('key','light cyan', 'black', 'underline'),
    ('title', 'white', 'black',),
    ('frame', 'dark green', 'black'),
    ('selected', 'light green', 'black'),
    ]

class ScapyShark(object):

    def __init__(self):
        
        self._parse_args()
        self._init_window()
        self.sniffer = Sniffer(self)

        # Keep track of what overlays are open
        self._overlays = []
        
        self._main_menu = menu.main_menu.build_menu(self)
    
    def _parse_args(self):
        parser = argparse.ArgumentParser(
            description='Text based network sniffer based on python scapy. Layout loosely similar to Wireshark.'
            )
        parser.add_argument('expression', type=str, nargs='*', default=None,
                help="BPF Capture Filter. Example: not tcp port 22 and host 127.0.0.1")
        parser.add_argument('-c', metavar='count', type=int, default=0,
                help='Stop capturing after receiving this many packets (defaults to infinity).')
        parser.add_argument('-r', metavar='filename', type=str, default=None,
                help='Read from pcap instead of sniffing on an interface.')
        parser.add_argument('-t', metavar='timeout', type=int, default=None,
                help='Stop parsing packets after timeout seconds have passed.')
        parser.add_argument('-w', metavar='filename', type=str, default=False,
                help='Write packets to pcap file while displaying.')
        parser.add_argument('--rolling-packet-buffer', metavar='max', type=int, default=None,
                help='(optional) How many packets to store in buffer at a time (default: unlimited)')
        parser.add_argument('--channel-hop', metavar='interface', type=str, default=None,
                help='(optional) Interface to channel hop on (default: no channel hopping)')
        parser.add_argument('--channel', metavar=('channel','interface'), type=str, default=None, nargs=2,
                help='(optional) Channel to set interface to (default: whatever it is already)')
        parser.add_argument('--lfilter', metavar='python_code', type=str, default=None,
                help='(optional) Python capture filter (i.e.: "scapy.layers.dot11.Dot11Beacon in packet")')
        parser.add_argument('--output', metavar='directory', type=str, default=os.path.abspath('output'),
                help='(optional) Output directory scapyshark will save things in. default: output')
        self._args = parser.parse_args()

        os.makedirs(self._args.output, exist_ok=True)


    def _init_window(self):
        header = 'ScapyShark v{version}'.format(version=version)
        self._header_box = urwid.BoxAdapter(urwid.AttrMap(urwid.Filler(urwid.Text(header, align='center')), 'header'), 1)
        self._footer_box = urwid.BoxAdapter(urwid.AttrMap(urwid.Filler(urwid.Text('No Packets Yet.', align='right')), 'header'), 1)

        # Body
        self._top_box = ScrollingListBox(rolling_packet_buffer=self._args.rolling_packet_buffer)
        self._middle_box = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text('')]))
        self._bottom_box = urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text('')]))
        
        divider = (1, urwid.Filler(urwid.Divider('\u2500')))
        self._body_pile = urwid.Pile([self._top_box, divider, self._middle_box, divider, self._bottom_box], focus_item=self._top_box)

        # Overarching Frame
        self.frame = urwid.Frame(self._body_pile, header=self._header_box, footer=self._footer_box, focus_part='body')

        # The main loop
        self.loop = urwid.MainLoop(urwid.AttrMap(self.frame, 'frame'), unhandled_input=self.unhandled_input, palette=palette)

    def run(self):
        self.sniffer.start()
        self.loop.run()

    def unhandled_input(self, inp):
        focus_widgets = self.loop.widget.base_widget.get_focus_widgets()

        if inp in ('q','Q'):
            # Q with an overlay up should just pop the overlay
            if self._overlays != []:
                self._pop_overlay()

            # No overlay up, we should quit
            else:
                raise urwid.ExitMainLoop()

        elif inp == 'enter':
            # User hit enter on a packet for more information
            if self._top_box in focus_widgets:
                show_packet_info(self, focus_widgets[-1])

            # Did uer hit enter on an overlay menu
            for overlay in self._overlays:
                if overlay['widget'] in focus_widgets:
                    overlay['enter_handler'](focus_widgets)
                    break

        elif inp == 'tab':
            if self._top_box in focus_widgets:
                self._body_pile.set_focus(self._middle_box)
            elif self._middle_box in focus_widgets:
                self._body_pile.set_focus(self._bottom_box)
            elif self._bottom_box in focus_widgets:
                self._body_pile.set_focus(self._top_box)

        elif inp == 'shift tab':
            if self._top_box in focus_widgets:
                self._body_pile.set_focus(self._bottom_box)
            elif self._middle_box in focus_widgets:
                self._body_pile.set_focus(self._top_box)
            elif self._bottom_box in focus_widgets:
                self._body_pile.set_focus(self._middle_box)

        elif inp in ('m', 'M'):
            self._main_menu.open()

        elif inp == 'down':
            # Did our menu mess up?
            for overlay in self._overlays:
                if overlay['widget'] in focus_widgets:
                    try:
                        overlay['widget'].base_widget.focus_position = (overlay['widget'].base_widget.focus_position + 1) % len(overlay['widget'].base_widget.body)
                    except:
                        pass
                
        elif inp == 'up':
            # Did our menu mess up?
            for overlay in self._overlays:
                if overlay['widget'] in focus_widgets:
                    try:
                        overlay['widget'].base_widget.focus_position = (overlay['widget'].base_widget.focus_position - 1) % len(overlay['widget'].base_widget.body)
                    except:
                        pass

        elif inp == 'f11' or inp == 'd':
            import IPython
            IPython.embed()

    def _pop_overlay(self):
        """ Remove top overlay. """
        overlay = self._overlays.pop()
        self.loop.widget = overlay['previous_widget']
        overlay['close_handler'](self)

    def _dialogue_general_get_edit_text(self):
        """str: Helper function to grab the edit text from the currently opened dialogue_general box."""
        return self._overlays[-1]['edit_box'].get_edit_text()

    def _dialogue_general(self, text, title=None, edit=None, buttons=None, edit_enter_handler=None, close_handler=None):
        """Opens a dialogue overlay box with an 'ok' button.

        Args:
            text (str, urwid.ListBox): Text that should be displayed in the box or the dialogue object to use instead
            title (str, optional): Title for the dialogue box
            edit (dict, optional): Contains urwid.Edit options for optional edit box
            buttons (list, optional): List of buttons to use in dialogue. If not specified, generic 'OK' button will be used.
            edit_enter_handler (function, optional): If you want your edit box to have a handler when the user presses enter, put the function here.
            close_handler (function, optional): Any code you want called when the dialogue box is closed.
        """

        def __edit_enter_handler(widget, text, handler):

            # TODO: For now just assume if \n is in the text, then enter has been pressed.
            if '\n' in widget.get_edit_text():
                handler(text.strip())
                self._pop_overlay()


        #
        # Build the dialogue
        #

        # If we don't already have the widget, build it
        if not isinstance(text, urwid.listbox.ListBox):

            lines = []
            for line in text.split('\n'):
                #menu_items.append(urwid.AttrMap(urwid.Text(item),'frame','selected'))
                lines.append(urwid.Text(line))

            dialogue = urwid.ListBox(urwid.SimpleFocusListWalker(lines))

        else:
            dialogue = text
            lines = list(dialogue.base_widget.body)

        #
        # Edit
        #

        if edit is not None:
            edit = urwid.Edit(**edit)

            # If we want an enter handler
            if edit_enter_handler is not None:
                urwid.connect_signal(edit, 'postchange', __edit_enter_handler, edit_enter_handler)

            dialogue.body.append(edit)


        #
        # Title
        #

        if title is not None:
            dialogue = urwid.LineBox(dialogue, title=title)
        else:
            dialogue = urwid.LineBox(dialogue)
        dialogue = urwid.AttrMap(dialogue, 'frame')

        #
        # Buttons
        #

        # General handler
        if buttons is None:
            ok = urwid.AttrMap(urwid.Button(u"Ok", on_press=lambda _: self._pop_overlay()), 'frame')
            buttons = urwid.Filler(urwid.Columns([ok]))

        else:
            # Use user's buttons
            buttons = urwid.Filler(urwid.Columns(buttons))

        my_pile = [dialogue, (1, buttons)]
        dialogue = urwid.Pile(my_pile, focus_item=0)

        max_width = max(len(x.get_text()[0]) for x in lines)
        max_width = max(max_width, len(title)) if title is not None else max_width

        height = len(lines) + 3

        if edit is not None:
            # Edit will be another row
            height += 1

            # Edit might have longer text?
            text_len = 0 if edit.caption is None else len(edit.caption)
            text_len = text_len if edit.edit_text is None else text_len + len(edit.edit_text)
            max_width = max(max_width, text_len + 1)

        overlay = urwid.Overlay(dialogue, self.loop.widget, 'center', max_width+5, 'middle', height)

        # Register that we have it open
        self._overlays.append({
            'name': 'Dialogue_ok',
            'widget': dialogue,
            'previous_widget': self.loop.widget,
            'enter_handler': lambda _: 1,
            'edit_box': edit,
            'close_handler': close_handler if close_handler is not None else lambda _: 1,
            })

        # Actually set it
        self.loop.widget = overlay

        
def main():
    shark = ScapyShark()
    shark.run()


if __name__ == '__main__':
    main()

from .packetinfo import show_packet_info
from . import menu
