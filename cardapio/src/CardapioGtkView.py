# 
#  Copyright (C) 2010 Cardapio Team (tvst@hotmail.com)
# 
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# these imports are outside of the "try" block because it defines
# the function fatal_error(), which is used in the "except"
from misc import *
import sys

try:
	from CardapioViewInterface import *
	from IconHelper import *
	import os
	import gtk
	import urllib2

	from time import time


except Exception, exception:
	fatal_error("Fatal error loading Cardapio's GTK interface", exception)
	sys.exit(1)

if gtk.ver < (2, 14, 0):
	fatal_error("Fatal error loading Cardapio's GTK interface", 'Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


# TODO: Figure out locale/gettext configuration, now that CardapioGTKView is in
# its own file...

class CardapioGtkView(CardapioViewInterface):

	def __init__(self, cardapio):

		self.cardapio = cardapio

		self.focus_out_blocked             = False
		self.auto_toggled_sidebar_button   = False # used to stop the on_toggle handler at times
		self.auto_toggled_view_mode_button = False # used to stop the on_toggle handler at times
		self.previously_focused_widget     = None
		self.clicked_app_info              = None


	# This method is required by the View API
	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		main_ui_filepath = os.path.join(self.cardapio.cardapio_path, 'ui', 'cardapio.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(self.cardapio.APP)
		builder.add_from_file(main_ui_filepath)
		builder.connect_signals(self)

		self.get_widget = builder.get_object
		self.window                    = self.get_widget('CardapioWindow')
		self.message_window            = self.get_widget('MessageWindow')
		self.about_dialog              = self.get_widget('AboutDialog')
		self.executable_file_dialog    = self.get_widget('ExecutableFileDialog')
		self.scroll_adjustment         = self.get_widget('ScrolledWindow').get_vadjustment()
		self.context_menu              = self.get_widget('CardapioContextMenu')
		self.app_context_menu          = self.get_widget('AppContextMenu')
		self.app_menu_separator        = self.get_widget('AppMenuSeparator')
		self.pin_menuitem              = self.get_widget('PinMenuItem')
		self.unpin_menuitem            = self.get_widget('UnpinMenuItem')
		self.add_side_pane_menuitem    = self.get_widget('AddSidePaneMenuItem')
		self.remove_side_pane_menuitem = self.get_widget('RemoveSidePaneMenuItem')
		self.open_app_menuitem         = self.get_widget('OpenAppMenuItem')
		self.open_parent_menuitem      = self.get_widget('OpenParentFolderMenuItem')
		self.peek_inside_menuitem      = self.get_widget('PeekInsideMenuItem')
		self.eject_menuitem            = self.get_widget('EjectMenuItem')
		self.view_mode_button          = self.get_widget('ViewModeButton')
		self.main_splitter             = self.get_widget('MainSplitter')
		self.navigation_buttons_pane   = self.get_widget('NavigationButtonsBackground')
		self.mainpane_separator        = self.get_widget('MainPaneSeparator')

		# override the pane constants from CardapioViewInterface
		self.APPLICATION_PANE          = self.get_widget('ApplicationPane')
		self.CATEGORY_PANE             = self.get_widget('CategoryPane')
		self.SYSTEM_CATEGORY_PANE      = self.get_widget('SystemCategoryPane')
		self.SIDE_PANE                 = self.get_widget('SideappPane')
		self.LEFT_SESSION_PANE         = self.get_widget('LeftSessionPane')
		self.RIGHT_SESSION_PANE        = self.get_widget('RightSessionPane')

		self.context_menu_options = {
			self.PIN_MENUITEM              : self.pin_menuitem,
			self.UNPIN_MENUITEM            : self.unpin_menuitem,
			self.ADD_SIDE_PANE_MENUITEM    : self.add_side_pane_menuitem,
			self.REMOVE_SIDE_PANE_MENUITEM : self.remove_side_pane_menuitem,
			self.OPEN_MENUITEM             : self.open_app_menuitem,
			self.OPEN_PARENT_MENUITEM      : self.open_parent_menuitem,
			self.PEEK_INSIDE_MENUITEM      : self.peek_inside_menuitem,
			self.EJECT_MENUITEM            : self.eject_menuitem,
			}

		# start with any search entry -- doesn't matter which
		self.search_entry = self.get_widget('TopLeftSearchEntry')

		# HACK: fix names of widgets to allow theming
		# (glade doesn't seem to properly add names to widgets anymore...)
		for widget in builder.get_objects():

			# skip the about dialog or the app name will be overwritten!
			if widget == self.about_dialog: continue

			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		# dynamic translation of MenuItem defined in .ui file
		about_distro_label = _('_About %(distro_name)s') % {'distro_name' : self.cardapio.distro_name}
		self.get_widget('AboutDistroMenuItem').set_label(about_distro_label)

		# grab some widget properties from the ui file
		self.section_label_attributes = self.get_widget('SectionName').get_attributes()
		self.fullsize_mode_padding = self.get_widget('CategoryMargin').get_padding()

		# make sure buttons have icons!
		self.gtk_settings = gtk.settings_get_default()
		self.gtk_settings.set_property('gtk-button-images', True)
		self.gtk_settings.connect('notify', self.on_gtk_settings_changed)

		self.window.set_keep_above(True)

		# make edges draggable
		self.get_widget('MarginLeft').realize()
		self.get_widget('MarginRight').realize()
		self.get_widget('MarginTop').realize()
		self.get_widget('MarginTopLeft').realize()
		self.get_widget('MarginTopRight').realize()
		self.get_widget('MarginBottom').realize()
		self.get_widget('MarginBottomLeft').realize()
		self.get_widget('MarginBottomRight').realize()
		self.get_widget('MarginLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.LEFT_SIDE))
		self.get_widget('MarginRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.RIGHT_SIDE))
		self.get_widget('MarginTop').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_SIDE))
		self.get_widget('MarginTopLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_LEFT_CORNER))
		self.get_widget('MarginTopRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_RIGHT_CORNER))
		self.get_widget('MarginBottom').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_SIDE))
		self.get_widget('MarginBottomLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_LEFT_CORNER))
		self.get_widget('MarginBottomRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_RIGHT_CORNER))


	def on_gtk_settings_changed(self, gobj, property_changed):
		"""
		Rebuild the Cardapio UI whenever the color scheme or gtk theme change
		"""

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self.read_gui_theme_info()
			self.cardapio.schedule_rebuild()


	def read_gui_theme_info(self):
		"""
		Reads some info from the GTK theme to better adapt to it 
		"""

		dummy_window = gtk.Window()
		dummy_window.set_name('ApplicationPane')
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_app_button_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_app_button_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_widget('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)
		self.get_widget('NavigationButtonsBackground').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)


	def on_mainwindow_destroy(self, *dummy):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self.cardapio.save_and_quit()

	
	# This method is required by the View API
	def quit(self):
		"""
		Do the last cleaning up you need to do --- this is the last thing that
		happens before Cardapio closes.
		"""
		gtk.main_quit()


	# This method is required by the View API
	def set_sidebar_button_toggled(self, button, state):
		"""
		Toggle a sidebar button
		"""

		if button.get_active() != state:
			self.auto_toggled_sidebar_button = True
			button.set_active(state)


	# This method is required by the View API
	def set_all_sections_sidebar_button_toggled(self, state, is_system_mode):
		"""
		Toggle the "All" sidebar button for either the main mode or
		the system mode sidebar.
		"""

		if is_system_mode:
			self.set_sidebar_button_toggled(self.all_system_sections_sidebar_button, state)
		else:
			self.set_sidebar_button_toggled(self.all_sections_sidebar_button, state)


	# This method is required by the View API
	def set_all_sections_sidebar_button_sensitive(self, state, is_system_mode):
		"""
		Makes the "All" button unclickable
		"""

		if is_system_mode:
			self.all_system_sections_sidebar_button.set_sensitive(state)
		else:
			self.all_sections_sidebar_button.set_sensitive(state)


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		self.cardapio.handle_section_all_clicked()

	
	# This method is required by the View API
	def show_section(self, section):
		"""
		Shows a given application section
		"""
		section.show()


	# This method is required by the View API
	def hide_section(self, section):
		"""
		Hides a given application section
		"""
		section.hide()


	# This method is required by the View API
	def hide_sections(self, sections):
		"""
		Hides the application sections listed in the array "sections"
		"""
		for section in sections: section.hide()


	# This method is required by the View API
	def clear_search_entry(self):
		"""
		Removes all text from the search entry.
		"""
		self.search_entry.set_text('')


	# This method is required by the View API
	def set_search_entry_text(self, text):
		"""
		Removes all text from the search entry.
		"""
		self.search_entry.set_text(text)


	# This method is required by the View API
	def get_search_entry_text(self):
		"""
		Gets the text that is currently displayed in the search entry, formatted
		in UTF8.
		"""

		text = self.search_entry.get_text()
		return unicode(text, 'utf-8')


	# TODO MVC this out of Cardapio
	def on_sidebar_button_clicked(self, widget, section_slab):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		return not self.cardapio.handle_section_clicked(section_slab)


	def on_sidebar_button_hovered(self, widget):
		"""
		Handler for when the user hovers over a category in the sidebar
		"""

		widget.set_active(True)


	def on_mainwindow_button_pressed(self, widget, event):
		"""
		Show context menu when the right mouse button is clicked on the main
		window
		"""

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self.block_focus_out_event()
			self.context_menu.popup(None, None, None, event.button, event.time)


	def on_search_entry_button_pressed(self, widget, event):
		"""
		Handler for when the users clicks on the search entry. We use this to
		stop window from hiding when context menu is shown.
		"""

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self.block_focus_out_event()
			glib.timeout_add(Cardapio.FOCUS_BLOCK_INTERVAL, self.unblock_focus_out_event)


	# This method is required by the View API
	def show_message_window(self):
		"""
		Show the "Rebuilding..." message window
		"""

		main_window_width, main_window_height = self.window.get_size()
		message_width, message_height = self.message_window.get_size()

		offset_x = (main_window_width  - message_width) / 2
		offset_y = (main_window_height - message_height) / 2

		x, y = self.window.get_position()
		self.message_window.move(x + offset_x, y + offset_y)

		self.message_window.set_keep_above(True)
		self.show_window_on_top(self.message_window)

		# ensure window is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()


	# This method is required by the View API
	def hide_message_window(self):
		"""
		Hide the "Rebuilding..." message window
		"""

		self.message_window.hide()


	# This method is required by the View API
	def show_main_window(self):
		"""
		Shows Cardapio's main window
		"""

		self.show_window_on_top(self.window)


	# This method is required by the View API
	def hide_main_window(self):
		"""
		Hides Cardapio's main window
		"""

		#if self.focus_out_blocked: return
		self.window.hide()


	# This method is required by the View API
	def open_about_dialog(self):
		"""
		Shows the "About" dialog
		"""

		self.about_dialog.show()


	def on_about_cardapio_clicked(self, dummy):
		self.open_about_dialog()


	# This method is required by the View API
	def show_executable_file_dialog(self, primary_text, secondary_text, hide_terminal_option):
		"""
		Opens a dialog similar to the one in Nautilus, that asks whether an
		executable script should be launched or edited.
		"""

		primary_text = '<big><b>' + primary_text + '</b></big>'

		self.get_widget('ExecutableDialogPrimaryText').set_markup(primary_text)
		self.get_widget('ExecutableDialogSecondaryText').set_text(secondary_text)

		if hide_terminal_option:
			self.get_widget('ExecutableDialogRunInTerminal').hide()

		self.executable_file_dialog.set_focus(self.get_widget('ExecutableDialogCancel'))

		response = self.executable_file_dialog.run()
		self.executable_file_dialog.hide()

		return response


	def show_window_on_top(self, window):
		"""
		Place the Cardapio window on top of all others
		"""

		window.stick()
		window.show_now()

		# for compiz, this must take place twice!!
		window.present_with_time(int(time()))
		window.present_with_time(int(time()))

		# for metacity, this is required!!
		window.window.focus()


	# This method is required by the View API
	def block_focus_out_event(self):
		"""
		Blocks the focus-out event
		"""

		if not self.focus_out_blocked:
			self.window.handler_block_by_func(self.on_mainwindow_focus_out)
			self.window.handler_block_by_func(self.on_mainwindow_cursor_leave)
			self.focus_out_blocked = True


	def unblock_focus_out_event(self, *dummy):
		"""
		If the focus-out event was previously blocked, this unblocks it
		"""

		if self.focus_out_blocked:
			self.window.handler_unblock_by_func(self.on_mainwindow_focus_out)
			self.window.handler_unblock_by_func(self.on_mainwindow_cursor_leave)
			self.focus_out_blocked = False


	# This method is required by the View API
	def fill_plugin_context_menu(self, clicked_app_info_context_menu):
		"""
		Add plugin-related actions to the context menu
		"""

		i = 0

		for item_info in clicked_app_info_context_menu:

			menu_item = gtk.ImageMenuItem(item_info['name'], True)
			menu_item.set_tooltip_text(item_info['tooltip'])
			menu_item.set_name('PluginAction' + str(i))
			i += 1

			if item_info['icon name'] is not None:
				icon_pixbuf = self.cardapio.icon_helper.get_icon_pixbuf(item_info['icon name'], self.cardapio.icon_helper.icon_size_menu)
				icon = gtk.image_new_from_pixbuf(icon_pixbuf)
				menu_item.set_image(icon)

			menu_item.app_info = item_info
			menu_item.connect('activate', self.on_app_button_clicked)

			menu_item.show_all()
			self.app_context_menu.append(menu_item)


	# This method is required by the View API
	def clear_plugin_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""

		for menu_item in self.app_context_menu:
			if menu_item.name is not None and menu_item.name.startswith('PluginAction'):
				self.app_context_menu.remove(menu_item)


	# This method is required by the View API
	def show_context_menu_option(self, menu_item):
		"""
		Shows the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""

		widget = self.context_menu_options[menu_item]
		widget.show()


	# This method is required by the View API
	def hide_context_menu_option(self, menu_item):
		"""
		Hides the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""

		widget = self.context_menu_options[menu_item]
		widget.hide()


	# This method is required by the View API
	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""

		time = gtk.get_current_event().time
		self.app_context_menu.popup(None, None, None, 3, time)


	# TODO MVC this out of Cardapio
	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list. This includes
		the "mouse click" event and the "clicked using keyboard" event, but
		not middle-clicks and right-clicks.
		"""

		ctrl_is_pressed = (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK)
		self.cardapio.handle_app_clicked(widget.app_info, 1, ctrl_is_pressed)


	# TODO MVC this out of Cardapio
	def on_app_button_button_pressed(self, widget, event):
		"""
		Respond to mouse click events onto app buttons. Either launch an app or
		show context menu depending on the button pressed.
		"""

		if event.type != gtk.gdk.BUTTON_PRESS: return
		if event.button == 1: return # avoid left-click activating the button twice
		self.clicked_app_info = widget.app_info
		self.cardapio.handle_app_clicked(widget.app_info, event.button, False)


	def on_view_mode_toggled(self, widget):
		"""
		Handler for when the "system menu" button is toggled
		"""

		if self.auto_toggled_view_mode_button:
			self.auto_toggled_view_mode_button = False
			return True

		self.cardapio.switch_modes(show_system_menus = widget.get_active())


	# This method is required by the View API
	def set_view_mode_button_toggled(self, state):
		"""
		Toggle the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		if self.view_mode_button.get_active() != state:
			self.auto_toggled_view_mode_button = True
			self.view_mode_button.set_active(state)


	# This method is required by the View API
	def show_view_mode_button(self):
		"""
		Shows the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		self.view_mode_button.show()


	# This method is required by the View API
	def hide_view_mode_button(self):
		"""
		Hides the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		self.view_mode_button.hide()


	# This method is required by the View API
	def set_main_splitter_position(self, position):
		"""
		Set the position of the "splitter" which separates the sidepane from the
		app pane
		"""

		self.main_splitter.set_position(position)


	# This method is required by the View API
	def get_main_splitter_position(self):
		"""
		Get the position of the "splitter" which separates the sidepane from the
		app pane
		"""

		return self.main_splitter.get_position()


	# This method is required by the View API
	def get_window_size(self):
		"""
		Get the width and height of the Cardapio window
		"""

		return list(self.window.get_size())


	# This method is required by the View API
	def get_window_position(self):
		"""
		Get the x,y coordinates of the top-left corner of the Cardapio window
		"""
		return self.window.get_position()


	# This method is required by the View API
	def apply_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""

		if not self.cardapio.settings['applet icon']: 
			self.cardapio.settings['applet icon'] = 'start-here'

		if self.cardapio.settings['show session buttons']:
			self.get_widget('SessionPane').show()
		else:
			self.get_widget('SessionPane').hide()

		# set up open-on-hover for categories

		category_buttons = self.CATEGORY_PANE.get_children() + self.SYSTEM_CATEGORY_PANE.get_children()

		if self.cardapio.settings['open categories on hover']:
			for category_button in category_buttons:

				if 'has_hover_handler' in dir(category_button) and not category_button.has_hover_handler: # is there a better way to check this?
					category_button.handler_unblock_by_func(self.on_sidebar_button_hovered)
				else: 
					category_button.connect('enter', self.on_sidebar_button_hovered)
					category_button.has_hover_handler = True 

		else:
			for category_button in category_buttons:
				if 'has_hover_handler' in dir(category_button) and category_button.has_hover_handler:
					category_button.handler_block_by_func(self.on_sidebar_button_hovered)
					category_button.has_hover_handler = False

		self.toggle_mini_mode_ui(update_window_size = False)


	def on_dialog_close(self, dialog, response = None):
		"""
		Handler for when a dialog's X button is clicked. This is used for the
		"About" and "Open in terminal?" dialogs for example.
		"""

		dialog.hide()
		return True


	def on_mainwindow_after_key_pressed(self, widget, event):
		"""
		Send all keypresses to the search entry, so the user can search
		from anywhere without the need to focus the search entry first
		"""

		w = self.window.get_focus()

		if w != self.search_entry and w == self.previously_focused_widget:
			if event.is_modifier: return

			self.window.set_focus(self.search_entry)
			self.search_entry.set_position(len(self.search_entry.get_text()))
			
			self.search_entry.emit('key-press-event', event)

		else:
			self.previously_focused_widget = None


	def on_mainwindow_key_pressed(self, widget, event):
		"""
		This is a trick to make sure the user isn't already typing at the
		search entry when we redirect all keypresses to the search entry.
		Because that would enter two of each key.
		"""

		if self.window.get_focus() != self.search_entry:
			self.previously_focused_widget = self.window.get_focus()


	# This method is required by the View API
	def get_cursor_coordinates(self):
		"""
		Returns the x,y coordinates of the mouse cursor with respect
		to the current screen.
		"""
		mouse_x, mouse_y, dummy = gtk.gdk.get_default_root_window().get_pointer()
		return mouse_x, mouse_y


	# This method is required by the View API
	def get_screen_dimensions(self):
		"""
		Returns usable dimensions of the current desktop in a form of
		a tuple: (x, y, width, height). If the real numbers can't be
		determined, returns the size of the whole screen instead.
		"""

		root_window = gtk.gdk.get_default_root_window()
		screen_property = gtk.gdk.atom_intern('_NET_WORKAREA')
		screen_dimensions = root_window.property_get(screen_property)[2]

		if screen_dimensions:
			return (screen_dimensions[0], screen_dimensions[1],
				screen_dimensions[2], screen_dimensions[3])

		else:
			logging.warn('Could not get dimensions of usable screen area. Using max screen area instead.')
			return (0, 0, gtk.gdk.screen_width(), gtk.gdk.screen_height())


	def on_mainwindow_focus_out(self, widget, event):

		self.cardapio.handle_mainwindow_focus_out()


	def on_mainwindow_cursor_leave(self, widget, event):

		self.cardapio.handle_mainwindow_cursor_leave()


	def on_mainwindow_delete_event(self, widget, event):

		self.cardapio.handle_user_closing_mainwindow()


	def on_search_entry_icon_pressed(self, widget, iconpos, event):

		self.cardapio.handle_search_entry_icon_pressed()


	def on_search_entry_activate(self, widget):

		self.cardapio.handle_search_entry_activate()
		# TODO: make this run also when the search entry is activated WHILE the
		# ctrl key is pressed


	# This method is required by the View API
	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.search_entry.get_text().strip()) == 0)


	def get_first_visible_app_widget(self):
		"""
		Returns the first app in the right pane, if any.
		"""

		for slab in self.APPLICATION_PANE.get_children():
			if not slab.get_visible(): continue

			# NOTE: the following line depends on the UI file. If the file is
			# changed, this may raise an exception:

			for child in slab.get_children()[0].get_children()[0].get_children():
				if not child.get_visible(): continue
				if type(child) != gtk.Button: continue

				return child

		return None


	# This method is required by the View API
	def focus_first_visible_app(self):
		"""
		Focuses the first visible button in the app pane.
		"""

		first_app_widget = self.get_first_visible_app_widget()
		if first_app_widget is not None:
			self.window.set_focus(first_app_widget)


	# This method is required by the View API
	def get_first_visible_app(self):
		"""
		Returns the app_info for the first app in the right pane, if any.
		"""
		widget = self.get_first_visible_app_widget()
		if widget is None: return None
		return widget.app_info


	# This method is required by the View API
	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""

		widget = self.previously_focused_widget

		if (type(widget) is gtk.Button and 'app_info' in dir(widget)):
			return widget.app_info

		return None


	# This method is required by the View API
	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the search entry's text
		"""

		self.search_entry.set_position(-1)


	# This method is required by the View API
	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""

		self.no_results_slab.hide()


	# This method is required by the View API
	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""

		self.scroll_adjustment.set_value(0)


	# This method is required by the View API
	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""

		if text is None: text = self.cardapio.no_results_text

		self.no_results_label.set_text(text)
		self.no_results_slab.show()


	def open_about_gnome_dialog(self, widget):
		"""
		Opens the "About Gnome" dialog.
		"""

		self.cardapio.open_about_dialog('AboutGnome')


	def open_about_distro_dialog(self, widget):
		"""
		Opens the "About %distro%" dialog
		"""

		self.cardapio.open_about_dialog('AboutDistro')


	def open_options_dialog(self, *dummy):
		"""
		Opens Cardapio's options dialog	
		"""

		self.cardapio.open_options_dialog()


	def launch_edit_app(self, *dummy):
		"""
		Open the menu editor app
		"""

		self.cardapio.launch_edit_app()

		
	# TODO MVC this out of Cardapio
	def on_search_entry_changed(self, *dummy):

		# FOR NOW, THIS METHOD SIMPLY FORWARDS ITS PARAMETERS TO CARDAPIO, BUT
		# LATER IT WILL BE SMARTER ABOUT MVC SEPARATION
		self.cardapio.on_search_entry_changed()


	def on_search_entry_key_pressed(self, widget, event):
		"""
		Handler for when the user presses a key when the search entry is
		focused.
		"""

		if event.keyval == gtk.gdk.keyval_from_name('Tab'):
			self.cardapio.handle_search_entry_tab_pressed()

		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):
			self.cardapio.handle_search_entry_escape_pressed()

		else: return False
		return True


	def on_main_splitter_clicked(self, widget, event):
		"""
		Make sure user can't move the splitter when in mini mode
		"""

		# TODO: collapse to mini mode when main_splitter is clicked (but not dragged)
		#if event.type == gtk.gdk.BUTTON_PRESS:

		if event.button == 1:
			if self.cardapio.settings['mini mode']:
				# block any other type of clicking when in mini mode
				return True


	def on_pin_this_app_clicked(self, widget):

		self.cardapio.handle_pin_this_app_clicked(self.clicked_app_info)


	def on_unpin_this_app_clicked(self, widget):

		self.cardapio.handle_unpin_this_app_clicked(self.clicked_app_info)


	def on_add_to_side_pane_clicked(self, widget):

		self.cardapio.handle_add_to_side_pane_clicked(self.clicked_app_info)


	def on_remove_from_side_pane_clicked(self, widget):

		self.cardapio.handle_remove_from_side_pane_clicked(self.clicked_app_info)


	def on_open_parent_folder_pressed(self, widget):

		self.cardapio.handle_open_parent_folder_pressed(self.clicked_app_info)


	def on_launch_in_background_pressed(self, widget):

		self.cardapio.handle_launch_in_background_pressed(self.clicked_app_info)


	def on_peek_inside_pressed(self, widget):

		self.cardapio.handle_peek_inside_pressed(self.clicked_app_info)


	def on_eject_pressed(self, widget):

		self.cardapio.handle_eject_pressed(self.clicked_app_info)


	def on_open_app_pressed(self, widget):

		self.cardapio.handle_launch_app_pressed(self.clicked_app_info)


	def on_app_button_focused(self, widget, event):
		"""
		Scroll to app buttons when they gain focus
		"""

		alloc = widget.get_allocation()
		scroller_position = self.scroll_adjustment.value
		page_size = self.scroll_adjustment.page_size

		if alloc.y < scroller_position:
			self.scroll_adjustment.set_value(alloc.y)

		elif alloc.y + alloc.height > scroller_position + page_size:
			self.scroll_adjustment.set_value(alloc.y + alloc.height - page_size)


	def on_app_button_drag_begin(self, button, drag_context):
		"""
		In a drag-and-drop operation, setup the icon that will be displayed near the
		mouse cursor.
		"""
		
		icon_pixbuf = self.cardapio.get_icon_pixbuf_from_app_info(button.app_info)
		button.drag_source_set_icon_pixbuf(icon_pixbuf)


	def on_app_button_data_get(self, button, drag_context, selection_data, info, time):
		"""
		In a drag-and-drop operation, send the drop target some information 
		about the dragged app.
		"""

		app_uri = self.cardapio.get_app_uri_for_drag_and_drop(button.app_info)
		selection_data.set_uris([app_uri])


	def on_back_button_clicked(self, widget):
		"""
		Handler for when the "back" button is clicked.
		"""
		self.cardapio.handle_back_button_clicked()


	# This method is required by the View API
	def show_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		self.navigation_buttons_pane.show()
		self.mainpane_separator.show()

		# This is a hackish way to solve a bug, where adding a '/' to a folder
		# from a Tracker result would not jump into it. We need to run this line
		# somewhere before processing a subfolder, so we're doing it here.
		self.previously_focused_widget = None


	# This method is required by the View API
	def hide_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		self.navigation_buttons_pane.hide()
		self.mainpane_separator.hide()


	def start_resize(self, widget, event):
		"""
		This function is used to emulate the window manager's resize function
		from Cardapio's borderless window.
		"""

		window_x, window_y = self.window.get_position()
		x = event.x_root - window_x
		y = event.y_root - window_y
		window_width, window_height = self.window.get_size()
		resize_margin = 10

		if x < resize_margin:

			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH_WEST

			elif y > window_height - resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH_WEST

			else:
				edge = gtk.gdk.WINDOW_EDGE_WEST

		elif x > window_width - resize_margin:

			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH_EAST

			elif y > window_height - resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH_EAST

			else:
				edge = gtk.gdk.WINDOW_EDGE_EAST

		else:
			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH

			else:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH

		x = int(event.x_root)
		y = int(event.y_root)

		self.block_focus_out_event()
		self.window.window.begin_resize_drag(edge, event.button, x, y, event.time)


	def end_resize(self, *dummy):
		"""
		This function is called when the user releases the mouse after resizing the
		Cardapio window.
		"""

		self.cardapio.end_resize()
		self.unblock_focus_out_event()


	def get_clicked_app_info(self):
		"""
		Returns
		"""
		return self.clicked_app_info


	# This method is required by the View API
	def add_button(self, button_str, icon_name, pane_or_section, tooltip, button_type):
		# TODO MVC: break this into add_app_button, add_sidebar_button, etc., so
		# it's easier to implement app buttons that are different from sidebar
		# ones.
		"""
		Adds a button to a parent container and returns a handler to it, which
		will be treated by the Controller as a constant (i.e. will never be
		modified).
		"""

		if button_type != self.CATEGORY_BUTTON:
			# TODO: make app buttons be togglebuttons too, so we can fake select
			# them when the context menu is showing
			button = gtk.Button() 
		else:
			button = gtk.ToggleButton()

		label = gtk.Label(button_str)

		if button_type == self.APP_BUTTON:
			icon_size_pixels = self.cardapio.icon_helper.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
			button.connect('clicked', self.on_app_button_clicked)
			button.connect('button-press-event', self.on_app_button_button_pressed)
			button.connect('focus-in-event', self.on_app_button_focused)
			parent_widget = self.get_button_container_from_section(pane_or_section)

			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#layout = label.get_layout()
			#extents = layout.get_pixel_extents()
			#label.set_ellipsize(ELLIPSIZE_END)
			#label.set_max_width_chars(20)

		else:
			parent_widget = pane_or_section
			icon_size_pixels = self.cardapio.icon_helper.icon_size_category

			if button_type == self.SIDEPANE_BUTTON:
				icon_size_pixels = self.cardapio.icon_helper.icon_size_category
				button.connect('clicked', self.on_app_button_clicked)
				button.connect('button-press-event', self.on_app_button_button_pressed)
				button.connect('focus-in-event', self.on_app_button_focused)

			elif button_type == self.SESSION_BUTTON:
				icon_size_pixels = self.cardapio.icon_helper.icon_size_category
				button.connect('clicked', self.on_app_button_clicked)

		icon_pixbuf = self.cardapio.icon_helper.get_icon_pixbuf(icon_name, icon_size_pixels)
		icon = gtk.image_new_from_pixbuf(icon_pixbuf)

		hbox = gtk.HBox()
		hbox.add(icon)
		hbox.add(label)
		hbox.set_spacing(5)
		hbox.set_homogeneous(False)

		align = gtk.Alignment(0, 0.5)
		align.add(hbox)

		if tooltip: button.set_tooltip_text(tooltip)

		button.add(align)
		button.set_relief(gtk.RELIEF_NONE)
		button.set_use_underline(False)

		button.show_all()
		parent_widget.pack_start(button, expand = False, fill = False)

		return button


	# This method is required by the View API
	def setup_button_drag_and_drop(self, button, is_desktop_file):
		"""
		Sets up the event handlers for drag-and-drop
		"""

		if is_desktop_file:
			button.drag_source_set(
					gtk.gdk.BUTTON1_MASK,
					[('text/uri-list', 0, 0)],
					gtk.gdk.ACTION_COPY)
		else:
			button.drag_source_set(
					gtk.gdk.BUTTON1_MASK,
					[('text/uri-list', 0, 0)],
					gtk.gdk.ACTION_LINK)

		button.connect('drag-begin', self.on_app_button_drag_begin)
		button.connect('drag-data-get', self.on_app_button_data_get)
		# TODO: drag and drop to reorganize pinned items


	# This method is required by the View API
	def get_section_from_button(self, button):
		"""
		Returns a unique handler describing the section that a given app button
		belongs to
		"""

		# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
		# HARD-TO-FIND BUGS!!

		return button.parent.parent.parent


	# This method is required by the View API
	def pre_build_ui(self):
		"""
		Prepares the UI before building any of the actual content-related widgets
		"""

		self.read_gui_theme_info()

		# the ui is already built by ui file, so we just clear it here
		self.remove_all_children(self.APPLICATION_PANE)
		self.remove_all_children(self.RIGHT_SESSION_PANE)
		self.remove_all_children(self.LEFT_SESSION_PANE)


	# This method is required by the View API
	def post_build_ui(self):
		"""
		Performs operations after building the actual content-related widgets
		"""

		# TODO: this is nitpicky, but we should do something here to preload the
		# window, so that it doesn't flash a grey rectangle on the first time
		# cardapio is shown
		pass


	# This method is required by the View API
	def build_all_sections_sidebar_buttons(self, title, tooltip):
		"""
		Creates the "All sections" buttons for both the regular and system modes
		"""

		# "All" button for the regular menu
		button = self.add_button(title, None, self.CATEGORY_PANE, tooltip, self.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button
		self.set_sidebar_button_toggled(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		# "All" button for the system menu
		button = self.add_button(title, None, self.SYSTEM_CATEGORY_PANE, tooltip, self.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_system_sections_sidebar_button = button
		self.set_sidebar_button_toggled(button, True)
		self.all_system_sections_sidebar_button.set_sensitive(False)


	# This method is required by the View API
	def build_no_results_slab(self):
		"""
		Creates the slab that will be used to display the "No results to show" text
		"""

		section_slab, label = self.add_application_section('Dummy text')
		self.no_results_slab = section_slab
		self.no_results_label = label
		self.hide_no_results_text()


	# This method is required by the View API
	def build_subfolders_slab(self, title, tooltip):
		"""
		Creates the Folder Contents slab to the app pane
		"""

		section_slab, label = self.cardapio.add_slab(title, 'system-file-manager', tooltip = tooltip, hide = True)
		self.subfolders_section = section_slab
		self.subfolders_label = label


	# This method is required by the View API
	def build_uncategorized_slab(self, title, tooltip):
		"""
		Creates the Uncategorized slab to the app pane
		"""

		section_slab, dummy = self.cardapio.add_slab(title, 'applications-other', tooltip = tooltip, hide = True)
		self.uncategorized_section = section_slab


	# This method is required by the View API
	def build_session_slab(self, title, tooltip):
		"""
		Creates the Session slab to the app pane
		"""

		section_slab, dummy = self.cardapio.add_slab(title, 'session-properties', hide = True)
		self.session_section = section_slab


	# This method is required by the View API
	def build_system_slab(self, title, tooltip):
		"""
		Creates the System slab to the app pane
		"""

		section_slab, dummy = self.cardapio.add_slab(title, 'applications-system', hide = True)
		self.system_section = section_slab


	# This method is required by the View API
	def build_places_slab(self, title, tooltip):
		"""
		Creates the Places slab to the app pane
		"""
		
		section_slab, dummy = self.cardapio.add_slab(title, 'folder', tooltip = tooltip, hide = False)
		self.places_section = section_slab


	# This method is required by the View API
	def build_pinneditems_slab(self, title, tooltip):
		"""
		Creates the Pinned Items slab to the app pane
		"""

		section_slab, dummy = self.cardapio.add_slab(title, 'emblem-favorite', tooltip = tooltip, hide = False)
		self.favorites_section = section_slab


	# This method is required by the View API
	def build_sidepane_slab(self, title, tooltip):
		"""
		Creates the Side Pane slab to the app pane
		"""

		section_slab, dummy = self.cardapio.add_slab(title, 'emblem-favorite', tooltip = tooltip, hide = True)
		self.sidepane_section = section_slab


	# This method is required by the View API
	def remove_about_context_menu_items(self):
		"""
		Removes "About Gnome" and "About %distro" from Cardapio's context menu
		"""

		self.get_widget('AboutGnomeMenuItem').set_visible(False)
		self.get_widget('AboutDistroMenuItem').set_visible(False)


	# This method is required by the View API
	def show_window_frame(self):
		"""
		Shows the window frame around Cardapio
		"""
		self.window.set_decorated(True)
		self.window.set_deletable(False) # remove "close" button from window frame (doesn't work with Compiz!)
		self.get_widget('MainWindowBorder').set_shadow_type(gtk.SHADOW_NONE)


	# This method is required by the View API
	def hide_window_frame(self):
		"""
		Hides the window frame around Cardapio
		"""
		self.window.set_decorated(False)
		self.window.set_deletable(True) 
		self.get_widget('MainWindowBorder').set_shadow_type(gtk.SHADOW_IN)


	# This method is required by the View API
	def remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section slab
		"""

		container = self.get_button_container_from_section(section)
		if container is None: return
		for	child in container.get_children():
			container.remove(child)
		# TODO: for speed, remove/readd container from its parent instead of
		# removing each child!


	def get_button_container_from_section(self, section):
		"""
		Returns a SectionContents widget given a SectionSlab. (SectionContents
		is the child of SectionMargin which is the child of SectionSlab. All app
		buttons are contained inside a SectionContents widget. The only exception
		is the SideappPane widget, which is its own button container)
		"""

		if section == self.SIDE_PANE: return section
		try:
			return section.get_children()[0].get_children()[0]
		except:
			return None


	# This method is required by the View API
	def remove_all_buttons_from_category_panes(self):
		"""
		Removes all buttons from both the regular and system category panes
		(i.e. the category filter lists)
		"""
		
		for	child in self.CATEGORY_PANE.get_children(): self.CATEGORY_PANE.remove(child)
		for	child in self.SYSTEM_CATEGORY_PANE.get_children(): self.SYSTEM_CATEGORY_PANE.remove(child)


	# This method is required by the View API
	def toggle_mini_mode_ui(self, update_window_size = True):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""

		category_buttons = self.CATEGORY_PANE.get_children() +\
				self.SYSTEM_CATEGORY_PANE.get_children() + self.SIDE_PANE.get_children()

		if self.cardapio.settings['mini mode']:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].hide()

			self.session_button_locksys.child.child.get_children()[1].hide()
			self.session_button_logout.child.child.get_children()[1].hide()
			self.RIGHT_SESSION_PANE.set_homogeneous(False)

			self.get_widget('ViewLabel').set_size_request(0, 0) # required! otherwise a weird margin appears
			self.get_widget('ViewLabel').hide()
			self.get_widget('ControlCenterLabel').hide()
			self.get_widget('ControlCenterArrow').hide()
			self.get_widget('CategoryScrolledWindow').set_policy(gtk.POLICY_NEVER, gtk.POLICY_NEVER)

			padding = self.fullsize_mode_padding
			self.get_widget('CategoryMargin').set_padding(0, padding[1], padding[2], padding[3])

			self.get_widget('TopLeftSearchSlabMargin').hide()    # these are required, to make sure the splitter
			self.get_widget('BottomLeftSearchSlabMargin').hide() # ...moves all the way to the left
			sidepane_margin = self.get_widget('SidePaneMargin')
			#self.set_main_splitter_position(0)

			# hack to make sure the viewport resizes to the minisize correctly
			self.get_widget('SideappViewport').hide()
			self.get_widget('SideappViewport').show()
			#self.LEFT_SESSION_PANE.hide()
			#self.LEFT_SESSION_PANE.show()
			#self.RIGHT_SESSION_PANE.hide()
			#self.RIGHT_SESSION_PANE.show()

			if update_window_size:
				self.cardapio.settings['window size'][0] -= self.get_main_splitter_position()

		else:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].show()

			self.session_button_locksys.child.child.get_children()[1].show()
			self.session_button_logout.child.child.get_children()[1].show()
			self.RIGHT_SESSION_PANE.set_homogeneous(True)

			self.get_widget('ViewLabel').set_size_request(-1, -1)
			self.get_widget('ViewLabel').show()
			self.get_widget('ControlCenterLabel').show()
			self.get_widget('ControlCenterArrow').show()
			self.get_widget('CategoryScrolledWindow').set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

			self.get_widget('CategoryMargin').set_padding(*self.fullsize_mode_padding)
			
			self.set_main_splitter_position(self.cardapio.settings['splitter position'])

			if update_window_size:
				self.cardapio.settings['window size'][0] += self.get_main_splitter_position()


	# This method is required by the View API
	def setup_search_entry(self, place_at_top, place_at_left):
		"""
		Hides 3 of the 4 search entries and returns the visible entry.
		"""

		text = self.search_entry.get_text()

		self.get_widget('TopLeftSearchSlabMargin').hide()
		self.get_widget('BottomLeftSearchSlabMargin').hide()
		self.get_widget('TopRightSearchSlabMargin').hide()
		self.get_widget('BottomRightSearchSlabMargin').hide()

		if place_at_top:
			if place_at_left:
				self.search_entry = self.get_widget('TopLeftSearchEntry')
				self.get_widget('TopLeftSearchSlabMargin').show()
			else:
				self.search_entry = self.get_widget('TopRightSearchEntry')
				self.get_widget('TopRightSearchSlabMargin').show()
		else:
			if place_at_left:
				self.search_entry = self.get_widget('BottomLeftSearchEntry')
				self.get_widget('BottomLeftSearchSlabMargin').show()
			else:
				self.search_entry = self.get_widget('BottomRightSearchEntry')
				self.get_widget('BottomRightSearchSlabMargin').show()

		self.search_entry.handler_block_by_func(self.on_search_entry_changed)
		self.search_entry.set_text(text)
		self.search_entry.handler_unblock_by_func(self.on_search_entry_changed)


	def remove_all_children(self, container):
		"""
		Removes all children from a GTK container
		"""
		
		for child in container: container.remove(child)


	# This method is required by the View API
	def focus_search_entry(self):
		"""
		Focuses the search entry
		"""

		self.window.set_focus(self.search_entry)


	# This method is required by the View API
	def show_section_status_text(self, section, text):
		"""
		Shows some status text inside a section (for instance, this is called to
		write the "loading..." text for slow plugins).
		"""

		self.remove_all_buttons_from_section(section)

		label = gtk.Label(text)
		label.set_alignment(0, 0.5)
		label.set_sensitive(False)
		label.show()

		section_contents = section.get_children()[0].get_children()[0]
		section_contents.pack_start(label, expand = False, fill = False)
		section_contents.show()


	def get_ctrl_key_state(self):
		"""
		Returns True if the CTRL key is pressed, and False otherwise.
		"""
		return (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK)


	# This method is required by the View API
	def run_in_ui_thread(self, function, *args, **kwargs):
		"""
		Runs a function making sure that no other thread can write to the UI.
		"""
		gtk.gdk.threads_enter()
		function(*args, **kwargs)
		gtk.gdk.threads_leave()


	# This method is required by the View API
	def add_application_section(self, section_title):
		"""
		Adds a new slab to the applications pane
		"""

		section_contents = gtk.VBox(homogeneous = True)

		section_margin = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
		section_margin.add(section_contents)
		section_margin.set_padding(0, 0, 0, 0)

		label = gtk.Label()
		label.set_use_markup(True)
		label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
		label.set_padding(0, 4)
		label.set_attributes(self.section_label_attributes)

		if section_title is not None:
			label.set_text(section_title)

		section_slab = gtk.Frame()
		section_slab.set_label_widget(label)
		section_slab.set_shadow_type(gtk.SHADOW_NONE)
		section_slab.add(section_margin)

		section_slab.show_all()

		self.APPLICATION_PANE.pack_start(section_slab, expand = False, fill = False)

		return section_slab, label


