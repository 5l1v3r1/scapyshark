
from . import MenuBase

def build_menu(scapyshark):
    global menu

    edit = {
        'caption': 'What you say: ',
        'edit_text': 'This is the edit text',
        'multiline': False,
        'align': 'left',
        'allow_tab': False,
    }

    buttons = []
    buttons.append(urwid.Button('Yes'))
    buttons.append(urwid.Button('No'))
    buttons.append(urwid.Button('Cancel', on_press= lambda _: scapyshark._pop_overlay()))

    menu_items = [
        ('DNS', lambda : 1),
        ('Test Menu', lambda: scapyshark._dialogue_general('blerg', title='this is my title', edit=edit, buttons=buttons)),
        ('Close', scapyshark._pop_overlay)
    ]

    menu = MenuBase(scapyshark, title='Research', menu_items=menu_items)
    return menu

import urwid
