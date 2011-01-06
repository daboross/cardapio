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
	from icons import *
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


class CardapioGtkView:

	def __init__(self, cardapio):

		self.cardapio = cardapio
		self.focus_out_blocked             = False
		self.auto_toggled_sidebar_button   = False # used to stop the on_toggle handler at times
		self.auto_toggled_view_mode_button = False # used to stop the on_toggle handler at times
		self.previously_focused_widget     = None


	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		self.rebuild_timer = None

		main_ui_filepath = os.path.join(self.cardapio.cardapio_path, 'ui', 'cardapio.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(self.cardapio.APP)
		builder.add_from_file(main_ui_filepath)
		builder.connect_signals(self.cardapio)

		self.get_widget = builder.get_object
		self.window                    = self.get_widget('CardapioWindow')
		self.message_window            = self.get_widget('MessageWindow')
		self.about_dialog              = self.get_widget('AboutDialog')
		self.executable_file_dialog    = self.get_widget('ExecutableFileDialog')
		self.cardapio.application_pane          = self.get_widget('ApplicationPane')
		self.cardapio.category_pane             = self.get_widget('CategoryPane')
		self.cardapio.system_category_pane      = self.get_widget('SystemCategoryPane')
		self.cardapio.sidepane                  = self.get_widget('SideappPane')
		self.cardapio.scroll_adjustment         = self.get_widget('ScrolledWindow').get_vadjustment()
		self.cardapio.left_session_pane         = self.get_widget('LeftSessionPane')
		self.cardapio.right_session_pane        = self.get_widget('RightSessionPane')
		self.context_menu              = self.get_widget('CardapioContextMenu')
		self.app_context_menu          = self.get_widget('AppContextMenu')
		self.app_menu_separator        = self.get_widget('AppMenuSeparator')
		self.pin_menuitem              = self.get_widget('PinMenuItem')
		self.unpin_menuitem            = self.get_widget('UnpinMenuItem')
		self.add_side_pane_menuitem    = self.get_widget('AddSidePaneMenuItem')
		self.remove_side_pane_menuitem = self.get_widget('RemoveSidePaneMenuItem')
		self.open_folder_menuitem      = self.get_widget('OpenParentFolderMenuItem')
		self.peek_inside_menuitem      = self.get_widget('PeekInsideMenuItem')
		self.eject_menuitem            = self.get_widget('EjectMenuItem')
		self.view_mode_button          = self.get_widget('ViewModeButton')
		self.main_splitter             = self.get_widget('MainSplitter')

		# start with any search entry -- doesn't matter which
		self.cardapio.search_entry = self.get_widget('TopLeftSearchEntry')

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
		self.cardapio.section_label_attributes = self.get_widget('SectionName').get_attributes()
		self.cardapio.fullsize_mode_padding = self.get_widget('CategoryMargin').get_padding()

		# make sure buttons have icons!
		self.cardapio.gtk_settings = gtk.settings_get_default()
		self.cardapio.gtk_settings.set_property('gtk-button-images', True)
		self.cardapio.gtk_settings.connect('notify', self.on_gtk_settings_changed)

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


	def on_mainwindow_destroy(self, *dummy):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self.cardapio.save_and_quit()


	# This method is required by the View API
	def set_sidebar_button_toggled(self, button, state):
		"""
		Toggle a sidebar button
		"""

		if button.get_active() != state:
			self.auto_toggled_sidebar_button = True
			button.set_active(state)


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		is_system_button = (widget == self.cardapio.all_system_sections_sidebar_button)
		self.cardapio.handle_section_all_clicked(is_system_button)

	
	def set_all_sections_sidebar_button_state(self, state, is_system_button):
		"""
		Makes the "All" button unclickable
		"""

		if is_system_button:
			self.cardapio.all_system_sections_sidebar_button.set_sensitive(state)
		else:
			self.cardapio.all_sections_sidebar_button.set_sensitive(state)


	# This method is required by the View API
	def clear_search_entry(self):
		"""
		Removes all text from the search entry.
		"""
		self.cardapio.search_entry.set_text('')


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
	def set_message_window_visible(self, state = True):
		"""
		Show/Hide the "Rebuilding..." message window
		"""

		if state == False:
			self.message_window.hide()
			return

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
	def show_main_window(self):
		"""
		Show's Cardapio's main window
		"""

		self.show_window_on_top(self.window)


	# This method is required by the View API
	def show_about_dialog(self):
		"""
		Shows the "About" dialog
		"""

		self.about_dialog.show()


	# This method is required by the View API
	def show_executable_file_dialog(self, path):
		"""
		Opens a dialog similar to the one in Nautilus, that asks whether an
		executable script should be launched or edited.
		"""

		basename = os.path.basename(path)
		arg_dict = {'file_name': basename}

		primary_text = '<big><b>' + _('Do you want to run "%(file_name)s" or display its contents?' % arg_dict) + '</b></big>'
		secondary_text = _('"%(file_name)s" is an executable text file.' % arg_dict)

		self.get_widget('ExecutableDialogPrimaryText').set_markup(primary_text)
		self.get_widget('ExecutableDialogSecondaryText').set_text(secondary_text)

		if not self.cardapio.can_launch_in_terminal():
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
			self.window.handler_block_by_func(self.cardapio.on_mainwindow_focus_out)
			self.window.handler_block_by_func(self.cardapio.on_mainwindow_cursor_leave)
			self.focus_out_blocked = True


	def unblock_focus_out_event(self, *dummy):
		"""
		If the focus-out event was previously blocked, this unblocks it
		"""

		if self.focus_out_blocked:
			self.window.handler_unblock_by_func(self.cardapio.on_mainwindow_focus_out)
			self.window.handler_unblock_by_func(self.cardapio.on_mainwindow_cursor_leave)
			self.focus_out_blocked = False


	# This method is required by the View API
	def fill_plugin_context_menu(self, clicked_app_context_menu):
		"""
		Add plugin-related actions to the context menu
		"""

		i = 0

		for item_info in clicked_app_context_menu:

			menu_item = gtk.ImageMenuItem(item_info['name'], True)
			menu_item.set_tooltip_text(item_info['tooltip'])
			menu_item.set_name('PluginAction' + str(i))
			i += 1

			if item_info['icon name'] is not None:
				icon_pixbuf = self.cardapio.icon_helper.get_icon_pixbuf(item_info['icon name'], self.cardapio.icon_helper.icon_size_menu)
				icon = gtk.image_new_from_pixbuf(icon_pixbuf)
				menu_item.set_image(icon)

			menu_item.app_info = item_info
			menu_item.connect('activate', self.cardapio.on_app_button_clicked)

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
	def setup_context_menu(self, app_info):
		"""
		Show or hide different context menu options depending on the widget
		"""
		# TODO: move much of this method into the controller

		self.open_folder_menuitem.hide()
		self.peek_inside_menuitem.hide()
		self.eject_menuitem.hide()

		if app_info['type'] == 'callback':
			self.pin_menuitem.hide()
			self.unpin_menuitem.hide()
			self.add_side_pane_menuitem.hide()
			self.remove_side_pane_menuitem.hide()
			self.app_menu_separator.hide()
			self.cardapio.setup_plugin_context_menu(app_info)
			return

		already_pinned = False
		already_on_side_pane = False
		self.app_menu_separator.show()

		for command in [app['command'] for app in self.cardapio.settings['pinned items']]:
			if command == app_info['command']:
				already_pinned = True
				break

		for command in [app['command'] for app in self.cardapio.settings['side pane items']]:
			if command == app_info['command']:
				already_on_side_pane = True
				break

		if already_pinned:
			self.pin_menuitem.hide()
			self.unpin_menuitem.show()
		else:
			self.pin_menuitem.show()
			self.unpin_menuitem.hide()

		if already_on_side_pane:
			self.add_side_pane_menuitem.hide()
			self.remove_side_pane_menuitem.show()
		else:
			self.add_side_pane_menuitem.show()
			self.remove_side_pane_menuitem.hide()

		# TODO: move this into Controller
		# figure out whether to show the 'open parent folder' menuitem
		split_command = urllib2.splittype(app_info['command'])

		if app_info['type'] == 'xdg' or len(split_command) == 2:

			path_type, canonical_path = split_command
			dummy, extension = os.path.splitext(canonical_path)

			# don't show it for network://, trash://, or .desktop files
			if path_type not in ('computer', 'network', 'trash') and extension != '.desktop':

				# only show if path that exists
				if os.path.exists(self.cardapio.unescape_url(canonical_path)):
					self.open_folder_menuitem.show()
					self.peek_inside_menuitem.show()

		# figure out whether to show the 'eject' menuitem
		if app_info['command'] in self.cardapio.volumes:
			self.eject_menuitem.show()

		self.cardapio.setup_plugin_context_menu(app_info)


	# This method is required by the View API
	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""

		time = gtk.get_current_event().time
		self.app_context_menu.popup(None, None, None, 3, time)


	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list
		"""
		ctrl_is_pressed = (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK)
		self.cardapio.handle_app_clicked(widget.app_info, 1, ctrl_is_pressed)


	def on_app_button_button_pressed(self, widget, event):
		"""
		Respond to mouse click events onto app buttons. Either launch an app or
		show context menu depending on the button pressed.
		"""

		if event.type != gtk.gdk.BUTTON_PRESS: return
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
	def set_view_mode_button_visible(self, state):
		"""
		Shows or hides the "view mode" button, which switches between "app view"
		and "control center" view
		"""

		if state: self.view_mode_button.show()
		else: self.view_mode_button.hide()


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

		category_buttons = self.cardapio.category_pane.get_children() + self.cardapio.system_category_pane.get_children()

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

		if w != self.cardapio.search_entry and w == self.previously_focused_widget:
			if event.is_modifier:
				return

			self.window.set_focus(self.cardapio.search_entry)
			self.cardapio.search_entry.set_position(len(self.cardapio.search_entry.get_text()))
			
			self.cardapio.search_entry.emit('key-press-event', event)

		else:
			self.previously_focused_widget = None


	def on_mainwindow_key_pressed(self, widget, event):
		"""
		This is a trick to make sure the user isn't already typing at the
		search entry when we redirect all keypresses to the search entry.
		Because that would enter two of each key.
		"""

		if self.window.get_focus() != self.cardapio.search_entry:
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


	def on_gtk_settings_changed(self, gobj, property_changed):
		"""
		Rebuild the Cardapio UI whenever the color scheme or gtk theme change
		"""

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self.read_gtk_theme_info()
			self.cardapio.schedule_rebuild()


	def read_gtk_theme_info(self):
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


