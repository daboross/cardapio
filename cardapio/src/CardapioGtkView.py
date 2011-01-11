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


	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		self.rebuild_timer = None

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
		self.application_pane          = self.get_widget('ApplicationPane')
		self.category_pane             = self.get_widget('CategoryPane')
		self.system_category_pane      = self.get_widget('SystemCategoryPane')
		self.sidepane                  = self.get_widget('SideappPane')
		self.scroll_adjustment         = self.get_widget('ScrolledWindow').get_vadjustment()
		self.left_session_pane         = self.get_widget('LeftSessionPane')
		self.right_session_pane        = self.get_widget('RightSessionPane')
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

		self.context_menu_options = {
			CardapioViewInterface.PIN_MENUITEM              : self.pin_menuitem,
			CardapioViewInterface.UNPIN_MENUITEM            : self.unpin_menuitem,
			CardapioViewInterface.ADD_SIDE_PANE_MENUITEM    : self.add_side_pane_menuitem,
			CardapioViewInterface.REMOVE_SIDE_PANE_MENUITEM : self.remove_side_pane_menuitem,
			CardapioViewInterface.OPEN_FOLDER_MENUITEM      : self.open_folder_menuitem,
			CardapioViewInterface.PEEK_INSIDE_MENUITEM      : self.peek_inside_menuitem,
			CardapioViewInterface.EJECT_MENUITEM            : self.eject_menuitem,
			}

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


	# This method is required by the View API
	def set_all_sections_sidebar_button_toggled(self, state, is_system_mode):
		"""
		Toggle the "All" sidebar button for either the main mode or
		the system mode sidebar.
		"""

		if is_system_mode:
			self.set_sidebar_button_toggled(self.cardapio.all_system_sections_sidebar_button, state)
		else:
			self.set_sidebar_button_toggled(self.cardapio.all_sections_sidebar_button, state)


	# This method is required by the View API
	def set_all_sections_sidebar_button_sensitive(self, state, is_system_mode):
		"""
		Makes the "All" button unclickable
		"""

		if is_system_mode:
			self.cardapio.all_system_sections_sidebar_button.set_sensitive(state)
		else:
			self.cardapio.all_sections_sidebar_button.set_sensitive(state)


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
		self.cardapio.search_entry.set_text('')


	# This method is required by the View API
	def set_search_entry_text(self, text):
		"""
		Removes all text from the search entry.
		"""
		self.cardapio.search_entry.set_text(text)


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
	def open_about_dialog(self):
		"""
		Shows the "About" dialog
		"""

		self.about_dialog.show()


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
	def set_context_menu_option_visible(self, menu_item, state):
		"""
		Shows or hides (depending on the "state" parameter) the context menu
		option specified by "menu_item". The "menu_item" parameter is one of 
		the *_MENUITEM constants declared in CardapioViewInterface.
		"""

		widget = self.context_menu_options[menu_item]
		if state: widget.show()
		else: widget.hide()


	# This method is required by the View API
	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""

		time = gtk.get_current_event().time
		self.app_context_menu.popup(None, None, None, 3, time)


	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list. This includes
		the "mouse click" event and the "clicked using keyboard" event, but
		not middle-clicks and right-clicks.
		"""

		ctrl_is_pressed = (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK)
		self.cardapio.handle_app_clicked(widget.app_info, 1, ctrl_is_pressed)


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
	def get_window_size(self):
		"""
		Get the width and height of the Cardapio window
		"""

		return list(self.window.get_size())


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

		category_buttons = self.category_pane.get_children() + self.system_category_pane.get_children()

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
			if event.is_modifier: return

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


	def on_search_entry_icon_pressed(self, widget, iconpos, event):

		self.cardapio.handle_search_entry_icon_pressed()


	def on_search_entry_activate(self, widget):

		self.cardapio.handle_search_entry_activate()


	# This method is required by the View API
	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.cardapio.search_entry.get_text().strip()) == 0)


	# This method is required by the View API
	def get_first_visible_app(self):
		"""
		Returns the first app in the right pane, if any.
		"""

		for slab in self.application_pane.get_children():
			if not slab.get_visible(): continue

			# NOTE: the following line depends on the UI file. If the file is
			# changed, this may raise an exception:

			for child in slab.get_children()[0].get_children()[0].get_children():
				if not child.get_visible(): continue
				if type(child) != gtk.Button: continue

				return child

		return None


	# This method is required by the View API
	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""

		widget = self.previously_focused_widget

		if (type(widget) is gtk.Button and 'app_info' in dir(widget)):
			return widget

		return None


	# This method is required by the View API
	def set_search_entry_text(self, text):
		"""
		Sets the text in the search entry textbox
		"""

		self.cardapio.search_entry.set_text(text)


	# This method is required by the View API
	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the search entry's text
		"""

		self.cardapio.search_entry.set_position(-1)


	# This method is required by the View API
	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""

		self.cardapio.no_results_slab.hide()


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

		self.cardapio.no_results_label.set_text(text)
		self.cardapio.no_results_slab.show()


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

		
	def on_search_entry_changed(self, *dummy):

		# FOR NOW, THIS METHOD SIMPLY FORWARDS ITS PARAMETERS TO CARDAPIO, BUT
		# LATER IT WILL BE SMARTER ABOUT MVC SEPARATION
		self.cardapio.on_search_entry_changed(*dummy)


	def on_search_entry_key_pressed(self, widget, event):

		# FOR NOW, THIS METHOD SIMPLY FORWARDS ITS PARAMETERS TO CARDAPIO, BUT
		# LATER IT WILL BE SMARTER ABOUT MVC SEPARATION
		self.cardapio.on_search_entry_key_pressed(widget, event)


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


	def add_button(self, button_str, icon_name, parent_widget, tooltip, button_type):
		"""
		Adds a button to a parent container
		"""

		if button_type != CardapioViewInterface.CATEGORY_BUTTON:
			# TODO: make app buttons be togglebuttons too, so we can fake select
			# them when the context menu is showing
			button = gtk.Button() 
		else:
			button = gtk.ToggleButton()

		label = gtk.Label(button_str)

		if button_type == CardapioViewInterface.APP_BUTTON:
			icon_size_pixels = self.cardapio.icon_helper.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)

			button.connect('clicked', self.on_app_button_clicked)
			button.connect('button-press-event', self.on_app_button_button_pressed)
			button.connect('focus-in-event', self.on_app_button_focused)

			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#layout = label.get_layout()
			#extents = layout.get_pixel_extents()
			#label.set_ellipsize(ELLIPSIZE_END)
			#label.set_max_width_chars(20)

		else:
			icon_size_pixels = self.cardapio.icon_helper.icon_size_category

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
	def get_section_slab_from_button(self, button):
		"""
		Returns the section slab widget that a given app button belongs to
		"""

		# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
		# HARD-TO-FIND BUGS!!

		return button.parent.parent.parent



