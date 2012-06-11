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
	import Constants
	from CardapioViewInterface import *
	from IconHelper import *

	import os
	import gtk
	import glib
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

	APP_BUTTON      = 0
	CATEGORY_BUTTON = 1
	SESSION_BUTTON  = 2
	SIDEPANE_BUTTON = 3

	FOCUS_BLOCK_INTERVAL = 50    # milliseconds

	def __init__(self, cardapio):

		self._cardapio = cardapio

		self._focus_out_blocked             = False
		self._auto_toggled_sidebar_button   = False # used to stop the on_toggle handler at times
		self._auto_toggled_view_mode_button = False # used to stop the on_toggle handler at times
		self._previously_focused_widget     = None
		self._clicked_app_button            = None
		self._display                       = gtk.gdk.display_get_default()
		self._screen                        = self._display.get_default_screen()
		self._root_window                   = gtk.gdk.get_default_root_window()
		self._wm                            = self._get_current_window_manager()


	# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
	# Methods required by the View API

	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		main_ui_filepath = os.path.join(self._cardapio.cardapio_path, 'ui', 'cardapio.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(Constants.APP)
		builder.add_from_file(main_ui_filepath)
		builder.connect_signals(self)

		self.get_widget = builder.get_object
		self.main_window               = self.get_widget('CardapioWindow')
		self.message_window            = self.get_widget('MessageWindow')
		self.about_dialog              = self.get_widget('AboutDialog')
		self.executable_file_dialog    = self.get_widget('ExecutableFileDialog')
		self.scroll_adjustment         = self.get_widget('ScrolledWindow').get_vadjustment()
		self.context_menu              = self.get_widget('CardapioContextMenu')
		self.app_context_menu          = self.get_widget('AppContextMenu')
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
		self.PIN_MENUITEM              = self.get_widget('PinMenuItem')
		self.UNPIN_MENUITEM            = self.get_widget('UnpinMenuItem')
		self.ADD_SIDE_PANE_MENUITEM    = self.get_widget('AddSidePaneMenuItem')
		self.REMOVE_SIDE_PANE_MENUITEM = self.get_widget('RemoveSidePaneMenuItem')
		self.OPEN_MENUITEM             = self.get_widget('OpenAppMenuItem')
		self.OPEN_PARENT_MENUITEM      = self.get_widget('OpenParentFolderMenuItem')
		self.PEEK_INSIDE_MENUITEM      = self.get_widget('PeekInsideMenuItem')
		self.EJECT_MENUITEM            = self.get_widget('EjectMenuItem')
		self.SEPARATOR_MENUITEM        = self.get_widget('AppMenuSeparator')

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
		about_distro_label = _('_About %(distro_name)s') % {'distro_name' : self._cardapio.distro_name}
		self.get_widget('AboutDistroMenuItem').set_label(about_distro_label)

		# grab some widget properties from the ui file
		self.section_label_attributes = self.get_widget('SectionName').get_attributes()
		self.fullsize_mode_padding = self.get_widget('CategoryMargin').get_padding()

		# make sure buttons have icons!
		self.gtk_settings = gtk.settings_get_default()
		self.gtk_settings.set_property('gtk-button-images', True)
		self.gtk_settings.connect('notify', self.on_gtk_settings_changed)

		self.main_window.set_keep_above(True)

		# turn on RGBA
		main_window_screen = self.main_window.get_screen()
		colormap = main_window_screen.get_rgba_colormap()
		if colormap is not None and self._cardapio.settings['allow transparency']: 
			gtk.widget_set_default_colormap(colormap)

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
		self.main_window.window.set_cursor(None)

		try:
			self.main_window.set_property('has-resize-grip', False)
		except:
			pass


	def quit(self):
		"""
		Do the last cleaning up you need to do --- this is the last thing that
		happens before Cardapio closes.
		"""
		gtk.main_quit()


	def set_sidebar_button_toggled(self, button, state):
		"""
		Toggle a sidebar button
		"""

		if button.get_active() != state:
			self._auto_toggled_sidebar_button = True
			button.set_active(state)


	def set_all_sections_sidebar_button_toggled(self, state, is_system_mode):
		"""
		Toggle the "All" sidebar button for either the main mode or
		the system mode sidebar.
		"""

		if is_system_mode:
			self.set_sidebar_button_toggled(self.all_system_sections_sidebar_button, state)
		else:
			self.set_sidebar_button_toggled(self.all_sections_sidebar_button, state)


	def set_all_sections_sidebar_button_sensitive(self, state, is_system_mode):
		"""
		Makes the "All" button unclickable
		"""

		if is_system_mode:
			self.all_system_sections_sidebar_button.set_sensitive(state)
		else:
			self.all_sections_sidebar_button.set_sensitive(state)


	def show_section(self, section):
		"""
		Shows a given application section
		"""
		section.show()
		# TODO: is this necessary? (below)
		section.get_children()[0].get_children()[0].show() # show also section_contents


	def unblock_focus_out_event(self, *dummy):
		"""
		If the focus-out event was previously blocked, this unblocks it
		"""

		if self._focus_out_blocked:
			self.main_window.handler_unblock_by_func(self.on_mainwindow_focus_out)
			self.main_window.handler_unblock_by_func(self.on_mainwindow_cursor_leave)
			self._focus_out_blocked = False


	def fill_plugin_context_menu(self, _clicked_app_button_info_context_menu):
		"""
		Add plugin-related actions to the context menu
		"""

		i = 0

		for item_info in _clicked_app_button_info_context_menu:

			menu_item = gtk.ImageMenuItem(item_info['name'], True)
			menu_item.set_tooltip_text(item_info['tooltip'])
			menu_item.set_name('PluginAction' + str(i))
			i += 1

			if item_info['icon name'] is not None:
				icon_pixbuf = self._cardapio.icon_helper.get_icon_pixbuf(item_info['icon name'], self._cardapio.icon_helper.icon_size_menu)
				icon = gtk.image_new_from_pixbuf(icon_pixbuf)
				menu_item.set_image(icon)

			menu_item.app_info = item_info
			menu_item.connect('activate', self.on_app_button_clicked)

			menu_item.show_all()
			self.app_context_menu.append(menu_item)


	def clear_plugin_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""

		for menu_item in self.app_context_menu:
			if menu_item.name is not None and menu_item.name.startswith('PluginAction'):
				self.app_context_menu.remove(menu_item)


	def show_context_menu_option(self, menu_item):
		"""
		Shows the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""

		menu_item.show()


	def hide_context_menu_option(self, menu_item):
		"""
		Hides the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""

		menu_item.hide()


	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""

		time = gtk.get_current_event().time
		self.app_context_menu.popup(None, None, None, 3, time)


	def set_view_mode_button_toggled(self, state):
		"""
		Toggle the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		if self.view_mode_button.get_active() != state:
			self._auto_toggled_view_mode_button = True
			self.view_mode_button.set_active(state)


	def show_view_mode_button(self):
		"""
		Shows the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		self.view_mode_button.show()

		# Sometimes Gtk seems to not show the button unless I hide/show its
		# parent viewport 
		self.get_widget('SideappViewport').hide()
		self.get_widget('SideappViewport').show()


	def hide_view_mode_button(self):
		"""
		Hides the "view mode" button, which switches between "app view" and
		"control center" view
		"""

		self.view_mode_button.hide()


	def set_main_splitter_position(self, position):
		"""
		Set the position of the "splitter" which separates the sidepane from the
		app pane
		"""

		self.main_splitter.set_position(position)


	def get_main_splitter_position(self):
		"""
		Get the position of the "splitter" which separates the sidepane from the
		app pane
		"""

		return self.main_splitter.get_position()


	def get_window_size(self):
		"""
		Get the width and height of the Cardapio window
		"""

		return list(self.main_window.get_size())


	def get_window_position(self):
		"""
		Get the x,y coordinates of the top-left corner of the Cardapio window
		"""
		return self.main_window.get_position()


	def apply_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""

		#if not self._cardapio.settings['applet icon']: 
		#	self._cardapio.settings['applet icon'] = 'start-here'

		if self._cardapio.settings['show session buttons']:
			self.get_widget('SessionPane').show()
		else:
			self.get_widget('SessionPane').hide()

		# set up open-on-hover for categories

		category_buttons = self.CATEGORY_PANE.get_children() + self.SYSTEM_CATEGORY_PANE.get_children()

		if self._cardapio.settings['open categories on hover']:
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


	def get_cursor_coordinates(self):
		"""
		Returns the x,y coordinates of the mouse cursor with respect
		to the current screen.
		"""
		mouse_x, mouse_y, dummy = gtk.gdk.get_default_root_window().get_pointer()
		return mouse_x, mouse_y


	def get_monitor_dimensions(self, x, y):
		"""
		Returns the dimensions of the monitor that contains the point x,y.  It
		would be *great* if these dimensions could be the *usable* dimensions,
		but it seems that the xdesktop spec does not define a way to get this...
		"""

		monitor = self._screen.get_monitor_at_point(x, y)
		monitor_dimensions = self._screen.get_monitor_geometry(monitor)
		return monitor_dimensions


	def get_screen_dimensions(self):
		"""
		Returns usable dimensions of the current desktop in a form of
		a tuple: (x, y, width, height). If the real numbers can't be
		determined, returns the size of the whole screen instead.
		"""

		screen_property = gtk.gdk.atom_intern('_NET_WORKAREA')
		screen_dimensions = self._root_window.property_get(screen_property)[2]

		if screen_dimensions:
			screen_x = screen_dimensions[0]
			screen_y = screen_dimensions[1]
			screen_width = screen_dimensions[2]
			screen_height = screen_dimensions[3]

		else:
			logging.warn('Could not get dimensions of usable screen area. Using max screen area instead.')
			screen_x = screen_y = 0
			screen_width  = self._screen.get_width()
			screen_height = self._screen.get_height()

		return (screen_x, screen_y, screen_width, screen_height)


	def is_window_visible(self):
		"""
		Returns True if the main window is visible
		"""
		return self.main_window.get_visible()


	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.search_entry.get_text().strip()) == 0)


	def focus_first_visible_app(self):
		"""
		Focuses the first visible button in the app pane.
		"""

		first_app_widget = self._get_nth_visible_app_widget(1)
		if first_app_widget is not None:
			self.main_window.set_focus(first_app_widget)


	def get_nth_visible_app(self, n):
		"""
		Returns the app_info for the nth app in the right pane, if any.
		"""
		widget = self._get_nth_visible_app_widget(n)
		if widget is None: return None
		return widget.app_info


	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""

		widget = self._previously_focused_widget

		if (type(widget) is gtk.ToggleButton and 'app_info' in dir(widget)):
			return widget.app_info

		return None


	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the search entry's text
		"""

		self.search_entry.set_position(-1)


	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""

		self.no_results_section.hide()


	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""

		self.scroll_adjustment.set_value(0)


	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""

		if text is None: text = self._cardapio.no_results_text

		self.no_results_label.set_text(text)
		self.no_results_section.show()


	def show_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		self.navigation_buttons_pane.show()
		self.mainpane_separator.show()

		# This is a hackish way to solve a bug, where adding a '/' to a folder
		# from a Tracker result would not jump into it. We need to run this line
		# somewhere before processing a subfolder, so we're doing it here.
		self._previously_focused_widget = None


	def hide_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		self.navigation_buttons_pane.hide()
		self.mainpane_separator.hide()


	def add_app_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the app pane, and returns a handler to it
		"""
		return self._add_button(button_str, icon_name, pane_or_section, tooltip, self.APP_BUTTON)


	def add_category_button(self, button_str, icon_name, pane_or_section, section, tooltip):
		"""
		Adds a toggle-button to the category pane, and returns a handler to it
		"""

		sidebar_button = self._add_button(button_str, icon_name, pane_or_section, tooltip, self.CATEGORY_BUTTON)
		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section)
		return sidebar_button


	def add_session_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the session pane, and returns a handler to it
		"""
		session_button = self._add_button(button_str, icon_name, pane_or_section, tooltip, self.SESSION_BUTTON)
		self.session_buttons.append(session_button)
		return session_button


	def add_sidepane_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the sidepane, and returns a handler to it
		"""
		return self._add_button(button_str, icon_name, pane_or_section, tooltip, self.SIDEPANE_BUTTON)


	def hide_button(self, button):
		"""
		Hides a button
		"""
		button.hide()


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


	def get_section_from_button(self, button):
		"""
		Returns a unique handler describing the section that a given app button
		belongs to
		"""

		# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
		# HARD-TO-FIND BUGS!!

		return button.parent.parent.parent


	def pre_build_ui(self):
		"""
		Prepares the UI before building any of the actual content-related widgets
		"""

		self.session_buttons = []
		self._read_gui_theme_info()

		# the ui is already built by ui file, so we just clear it here
		self._remove_all_children(self.APPLICATION_PANE)
		self._remove_all_children(self.RIGHT_SESSION_PANE)
		self._remove_all_children(self.LEFT_SESSION_PANE)


	def post_build_ui(self):
		"""
		Performs operations after building the actual content-related widgets
		"""

		# TODO: this is nitpicky, but we should do something here to preload the
		# window, so that it doesn't flash a grey rectangle on the first time
		# cardapio is shown
		pass


	def build_all_sections_sidebar_buttons(self, title, tooltip):
		"""
		Creates the "All sections" buttons for both the regular and system modes
		"""

		# "All" button for the regular menu
		button = self._add_button(title, None, self.CATEGORY_PANE, tooltip, self.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button
		self.set_sidebar_button_toggled(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		# "All" button for the system menu
		button = self._add_button(title, None, self.SYSTEM_CATEGORY_PANE, tooltip, self.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_system_sections_sidebar_button = button
		self.set_sidebar_button_toggled(button, True)
		self.all_system_sections_sidebar_button.set_sensitive(False)


	def build_no_results_section(self):
		"""
		Creates the section that will be used to display the "No results to show" text
		"""

		section, label = self.add_application_section('Dummy text')
		self.no_results_section = section
		self.no_results_label = label
		self.hide_no_results_text()


	def build_subfolders_section(self, title, tooltip):
		"""
		Creates the Folder Contents section to the app pane
		"""

		section, label = self._cardapio.add_section(title, 'system-file-manager', tooltip = tooltip, hidden_when_no_query = True)
		self.SUBFOLDERS_SECTION = section
		self.subfolders_label = label


	def build_uncategorized_section(self, title, tooltip):
		"""
		Creates the Uncategorized section to the app pane
		"""

		section, dummy = self._cardapio.add_section(title, 'applications-other', tooltip = tooltip, hidden_when_no_query = True)
		self.UNCATEGORIZED_SECTION = section


	def build_session_section(self, title, tooltip):
		"""
		Creates the Session section to the app pane
		"""

		section, dummy = self._cardapio.add_section(title, 'session-properties', hidden_when_no_query = True)
		self.SESSION_SECTION = section


	def build_system_section(self, title, tooltip):
		"""
		Creates the System section to the app pane
		"""

		section, dummy = self._cardapio.add_section(title, 'applications-system', hidden_when_no_query = True)
		self.SYSTEM_SECTION = section


	def build_places_section(self, title, tooltip):
		"""
		Creates the Places section to the app pane
		"""
		
		section, dummy = self._cardapio.add_section(title, 'folder', tooltip = tooltip, hidden_when_no_query = False)
		self.PLACES_SECTION = section


	def build_pinneditems_section(self, title, tooltip):
		"""
		Creates the Pinned Items section to the app pane
		"""

		section, dummy = self._cardapio.add_section(title, 'emblem-favorite', tooltip = tooltip, hidden_when_no_query = False)
		self.FAVORITES_SECTION = section


	def build_sidepane_section(self, title, tooltip):
		"""
		Creates the Side Pane section to the app pane
		"""

		section, dummy = self._cardapio.add_section(title, 'emblem-favorite', tooltip = tooltip, hidden_when_no_query = True)
		self.SIDEPANE_SECTION = section


	def remove_about_context_menu_items(self):
		"""
		Removes "About Gnome" and "About %distro" from Cardapio's context menu
		"""

		self.get_widget('AboutGnomeMenuItem').set_visible(False)
		self.get_widget('AboutDistroMenuItem').set_visible(False)


	def show_window_frame(self):
		"""
		Shows the window frame around Cardapio
		"""
		self.main_window.set_decorated(True)
		self.main_window.set_deletable(False) # remove "close" button from window frame (doesn't work with Compiz!)
		self.get_widget('MainWindowBorder').set_shadow_type(gtk.SHADOW_NONE)


	def hide_window_frame(self):
		"""
		Hides the window frame around Cardapio
		"""
		self.main_window.set_decorated(False)
		self.main_window.set_deletable(True) 
		self.get_widget('MainWindowBorder').set_shadow_type(gtk.SHADOW_IN)


	def remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section 
		"""

		container = self._get_button_container_from_section(section)
		if container is None: return
		for	child in container.get_children():
			container.remove(child)
		# TODO: for speed, remove/readd container from its parent instead of
		# removing each child!


	def remove_all_buttons_from_category_panes(self):
		"""
		Removes all buttons from both the regular and system category panes
		(i.e. the category filter lists)
		"""
		
		for	child in self.CATEGORY_PANE.get_children(): self.CATEGORY_PANE.remove(child)
		for	child in self.SYSTEM_CATEGORY_PANE.get_children(): self.SYSTEM_CATEGORY_PANE.remove(child)


	def toggle_mini_mode_ui(self, update_window_size = True):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""

		category_buttons = self.CATEGORY_PANE.get_children() +\
				self.SYSTEM_CATEGORY_PANE.get_children() + self.SIDE_PANE.get_children()

		if self._cardapio.settings['mini mode']:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].hide()

			try:
				for session_button in self.session_buttons:
					session_button.child.child.get_children()[1].hide()
			except:
				pass

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
				self._cardapio.settings['window size'][0] -= self.get_main_splitter_position()

		else:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].show()

			try:
				for session_button in self.session_buttons:
					session_button.child.child.get_children()[1].show()
			except:
				pass

			self.RIGHT_SESSION_PANE.set_homogeneous(True)

			self.get_widget('ViewLabel').set_size_request(-1, -1)
			self.get_widget('ViewLabel').show()
			self.get_widget('ControlCenterLabel').show()
			self.get_widget('ControlCenterArrow').show()
			self.get_widget('CategoryScrolledWindow').set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

			self.get_widget('CategoryMargin').set_padding(*self.fullsize_mode_padding)
			
			self.set_main_splitter_position(self._cardapio.settings['splitter position'])

			if update_window_size:
				self._cardapio.settings['window size'][0] += self.get_main_splitter_position()


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


	def focus_search_entry(self):
		"""
		Focuses the search entry
		"""

		self.main_window.set_focus(self.search_entry)


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


	def run_in_ui_thread(self, function, *args, **kwargs):
		"""
		Runs a function making sure that no other thread can write to the UI.
		"""
		gtk.gdk.threads_enter()
		function(*args, **kwargs)
		gtk.gdk.threads_leave()


	def add_application_section(self, section_title):
		"""
		Adds a new section to the applications pane
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

		section = gtk.Frame()
		section.set_label_widget(label)
		section.set_shadow_type(gtk.SHADOW_NONE)
		section.add(section_margin)

		section.show_all()

		self.APPLICATION_PANE.pack_start(section, expand = False, fill = False)

		return section, label


	def show_pane(self, pane):
		"""
		Show the pane given by one of the *_PANE constants
		"""
		pane.show()


	def hide_pane(self, pane):
		"""
		Hide the pane given by one of the *_PANE constants
		"""
		pane.hide()


	def show_button(self, button):
		"""
		Show the given button 
		"""
		button.show()


	def hide_button(self, button):
		"""
		Hide the given button
		"""
		button.hide()


	def resize_main_window(self, width, height):
		"""
		Resizes the main Cardapio window
		"""
		self.main_window.resize(width, height)


	def move_main_window(self, x, y, anchor_right, anchor_bottom):
		"""
		Moves the main Cardapio window, obeying the anchor_* booleans
		"""

		if anchor_right:
			if anchor_bottom: self.main_window.set_gravity(gtk.gdk.GRAVITY_SOUTH_EAST)
			else: self.main_window.set_gravity(gtk.gdk.GRAVITY_NORTH_EAST)

		else:
			if anchor_bottom: self.main_window.set_gravity(gtk.gdk.GRAVITY_SOUTH_WEST)
			else: self.main_window.set_gravity(gtk.gdk.GRAVITY_NORTH_WEST)

		# There has been a regression in Ubuntu 11.04, so I'm making the hack permanent. Ugh.
		#if gtk.ver[0] == 2 and gtk.ver[1] <= 21 and gtk.ver[2] < 5:
		if True:
			self._move_main_window_with_gravity_hack(x, y)
		else:
			self.main_window.move(x, y)


	def set_subfolder_section_title(self, title):
		"""
		Sets the title of the subfolder section
		"""
		self.subfolders_label.set_text(title)


	def show_rebuild_required_bar(self):
		"""
		Shows the "rebuild required" bar, which allows the user to click the
		"reload" button, which rebuilds all of Cardapio's menus
		"""
		self.get_widget('ReloadMessageBar').show()


	def hide_rebuild_required_bar(self):
		"""
		Hide the "rebuild required" bar.
		"""
		self.get_widget('ReloadMessageBar').hide()


	def set_screen(self, screen_number):
		"""
		Sets the screen where the view will be shown (given as an integer)
		"""
		self._screen = self._display.get_screen(screen_number)
		self._root_window = self._screen.get_root_window()


	def get_screen_with_pointer(self):
		"""
		Returns the number of the screen that currently contains the mouse
		pointer
		"""
		screen, dummy, dummy, dummy = self._display.get_pointer()
		return screen.get_number()


	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the text entry
		"""
		self.search_entry.set_position(-1)


	def hide_section(self, section):
		"""
		Hides a given application section
		"""
		section.hide()


	def hide_sections(self, sections):
		"""
		Hides the application sections listed in the array "sections"
		"""
		for section in sections: section.hide()


	def clear_search_entry(self):
		"""
		Removes all text from the search entry.
		"""
		self.search_entry.set_text('')


	def set_search_entry_text(self, text):
		"""
		Removes all text from the search entry.
		"""
		self.search_entry.set_text(text)


	def get_search_entry_text(self):
		"""
		Gets the text that is currently displayed in the search entry, formatted
		in UTF8.
		"""

		text = self.search_entry.get_text()
		return unicode(text, 'utf-8')


	def show_message_window(self):
		"""
		Show the "Rebuilding..." message window
		"""

		main_window_width, main_window_height = self.main_window.get_size()
		message_width, message_height = self.message_window.get_size()

		offset_x = (main_window_width  - message_width) / 2
		offset_y = (main_window_height - message_height) / 2

		x, y = self.main_window.get_position()
		self.message_window.move(x + offset_x, y + offset_y)

		self.message_window.set_keep_above(True)
		self._show_window_on_top(self.message_window)

		# ensure window is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()


	def hide_message_window(self):
		"""
		Hide the "Rebuilding..." message window
		"""

		self.message_window.hide()

		# ensure window is hidden immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()


	def show_main_window(self):
		"""
		Shows Cardapio's main window
		"""

		self._show_window_on_top(self.main_window)

		# NOTE: I would love to use keyboard_grab rather than have to keep track
		# of opened_last_app_in_background in Cardapio.py, especially because
		# that approach breaks with some apps like Firefox. However, using
		# keyboard_grab introduces tons of issues itself. For instance, it
		# blocks mouse clicks outside of Cardapio from closing the Cardapio
		# window. It also blocks the shortcut key from being used to close
		# Cardapio. In sum, this whole situation is a mess. And it would be
		# great if someone could help...

		#gtk.gdk.keyboard_grab(self.main_window.window)
		#gtk.gdk.pointer_grab(self.main_window.window, True, gtk.gdk.BUTTON_PRESS_MASK)


	def hide_main_window(self):
		"""
		Hides Cardapio's main window
		"""

		# see the note in show_main_window()
		#gtk.gdk.pointer_ungrab(0)
		#gtk.gdk.keyboard_ungrab(0)

		self.main_window.hide()


	def open_about_dialog(self):
		"""
		Shows the "About" dialog
		"""

		self.about_dialog.show()


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


	def block_focus_out_event(self):
		"""
		Blocks the focus-out event
		"""

		if not self._focus_out_blocked:
			self.main_window.handler_block_by_func(self.on_mainwindow_focus_out)
			self.main_window.handler_block_by_func(self.on_mainwindow_cursor_leave)
			self._focus_out_blocked = True


	# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
	# Private methods

	def _get_current_window_manager(self):
		"""
		Returns the name of the current window manager as a string. If
		unrecognized, returns None.
		"""

		# We don't need to know all WMs, just a few problematic ones.
		wms = ['gnome-shell', 'compiz', 'metacity', 'cinnamon']

		for wm in wms:

			process = subprocess.Popen(
					['pgrep', wm],
					stdout=subprocess.PIPE, stderr=subprocess.PIPE)

			stdout, dummy = process.communicate()
			if stdout: return wm

		return None


	def _read_gui_theme_info(self):
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

		# TODO: I would love to assign some existing theme color on ReloadMessageBar,
		# but I don't know which color I can use for this. Is there a named
		# "message bar" color, that is used by Evince, for instance?
		#
		# self.get_widget('ReloadMessageBar').modify_bg(gtk.STATE_NORMAL, ??)
		# self.get_widget('ReloadMessageBar').modify_fg(gtk.STATE_NORMAL, ??)


	def _show_window_on_top(self, window):
		"""
		Place the Cardapio window on top of all others
		"""

		window.stick()
		window.set_screen(self._screen)
		window.show_now()

		window.present_with_time(int(time()))

		if self._wm == 'compiz':
			window.present_with_time(int(time()))

		else:
			window.window.focus()

		# TODO: must handle Cinnamon here, since we are getting focus
		# problems in the WM :(


	def _toggle_app_button(self, widget, state):
		"""
		Toggles/untoggles a given app button
		"""
		widget.handler_block_by_func(self.on_app_button_clicked)
		widget.set_active(state)
		widget.handler_unblock_by_func(self.on_app_button_clicked)


	def _handle_if_key_combo(self, event):
		"""
		If the event describes a key combo (a regular key plus Alt or Ctrl),
		this method tells the model to process the combo, and returns True.
		Otherwise, returns False.
		"""

		if event.state & gtk.gdk.MOD1_MASK: 
			if 48 <= event.keyval <= 57: 
				self._cardapio.handle_special_key_pressed(key = event.keyval - 48, alt = True)
				return True

		return False


	def is_cursor_inside_window(self, window):
		"""
		Returns True if the mouse cursor is inside the given window. False
		otherwise.
		"""

		mouse_x, mouse_y = self.get_cursor_coordinates()

		x0, y0 = window.get_position()
		w, h = list(window.get_size())

		return (x0 <= mouse_x <= x0+w and y0 <= mouse_y <= y0+h)


	def _get_nth_visible_app_widget(self, n = 1):
		"""
		Returns the nth app in the right pane, if any.
		"""

		for section in self.APPLICATION_PANE.get_children():
			if not section.get_visible(): continue

			# NOTE: the following line depends on the UI file. If the file is
			# changed, this may raise an exception:

			for child in section.get_children()[0].get_children()[0].get_children():
				if not child.get_visible(): continue
				if type(child) != gtk.ToggleButton: continue

				n = n - 1
				if n == 0: return child

		return None


	def _add_button(self, button_str, icon_name, pane_or_section, tooltip, button_type):
		# TODO MVC: break this into add_app_button, add_sidebar_button, etc., so
		# it's easier to implement app buttons that are different from sidebar
		# ones.
		"""
		Adds a button to a parent container and returns a handler to it, which
		will be treated by the Controller as a constant (i.e. will never be
		modified).
		"""

		button = gtk.ToggleButton()
		label = gtk.Label(button_str)

		if button_type == self.APP_BUTTON:
			icon_size_pixels = self._cardapio.icon_helper.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
			button.connect('clicked', self.on_app_button_clicked)
			button.connect('button-press-event', self.on_app_button_button_pressed)
			button.connect('focus-in-event', self.on_app_button_focused)
			parent_widget = self._get_button_container_from_section(pane_or_section)

			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#layout = label.get_layout()
			#extents = layout.get_pixel_extents()
			#label.set_ellipsize(ELLIPSIZE_END)
			#label.set_max_width_chars(20)

		else:
			parent_widget = pane_or_section
			icon_size_pixels = self._cardapio.icon_helper.icon_size_category

			if button_type == self.SIDEPANE_BUTTON:
				icon_size_pixels = self._cardapio.icon_helper.icon_size_category
				button.connect('clicked', self.on_app_button_clicked)
				button.connect('button-press-event', self.on_app_button_button_pressed)
				button.connect('focus-in-event', self.on_app_button_focused)

			elif button_type == self.SESSION_BUTTON:
				icon_size_pixels = self._cardapio.icon_helper.icon_size_category
				button.connect('clicked', self.on_app_button_clicked)

		icon_pixbuf = self._cardapio.icon_helper.get_icon_pixbuf(icon_name, icon_size_pixels)
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


	def _get_button_container_from_section(self, section):
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


	def _remove_all_children(self, container):
		"""
		Removes all children from a GTK container
		"""
		
		for child in container: container.remove(child)


	def _get_ctrl_key_state(self):
		"""
		Returns True if the CTRL key is pressed, and False otherwise.
		"""
		return (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK)


	def _get_shift_key_state(self):
		"""
		Returns True if the SHIFT key is pressed, and False otherwise.
		"""
		return (gtk.get_current_event().state & gtk.gdk.SHIFT_MASK == gtk.gdk.SHIFT_MASK)


	def _move_main_window_with_gravity_hack(self, x, y):
		"""
		For some reason, GTK 2.20.x in Ubuntu 10.04 (Lucid) does not 
		respect the set_gravity command, so here we fix that.
		"""

		gravity = self.main_window.get_gravity()
		width, height = self.main_window.get_size()

		if gravity == gtk.gdk.GRAVITY_NORTH_WEST:
			pass

		elif gravity == gtk.gdk.GRAVITY_NORTH_EAST:
			x -= width

		elif gravity == gtk.gdk.GRAVITY_SOUTH_WEST:
			y -= height

		elif gravity == gtk.gdk.GRAVITY_SOUTH_EAST:
			x -= width
			y -= height

		# NOTE: There are other gravity constants in GDK, but we do not implement
		# them here because they're not used in Cardapio.

		self.main_window.set_gravity(gtk.gdk.GRAVITY_NORTH_WEST)
		self.main_window.move(x, y)


	def _get_icon_pixbuf_from_app_info(self, app_info):
		"""
		Get the icon pixbuf for an app given its app_info dict
		"""

		return self._cardapio.icon_helper.get_icon_pixbuf(app_info['icon name'], self._cardapio.icon_helper.icon_size_app)


	# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
	# Callbacks

	def on_gtk_settings_changed(self, gobj, property_changed):
		"""
		Rebuild the Cardapio UI whenever the color scheme or gtk theme change
		"""

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self._read_gui_theme_info()
			self._cardapio.handle_view_settings_changed()


	def on_mainwindow_destroy(self, *dummy):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self._cardapio.handle_window_destroyed()

	
	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self._auto_toggled_sidebar_button:
			self._auto_toggled_sidebar_button = False
			return True

		self._cardapio.handle_section_all_clicked()

	
	def on_sidebar_button_clicked(self, widget, section):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self._auto_toggled_sidebar_button:
			self._auto_toggled_sidebar_button = False
			return True

		return not self._cardapio.handle_section_clicked(section)


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

		# TODO: consider case where cursor is inside the APPLET too!

		if not self.is_cursor_inside_window(self.main_window):
			# since we grab keyboard/pointer focus, we want to make sure Cardapio hides
			# when the user clicks outside its window
			self.hide_main_window()
			return False

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
			glib.timeout_add(self.FOCUS_BLOCK_INTERVAL, self.unblock_focus_out_event)


	def on_about_cardapio_clicked(self, dummy):
		self.open_about_dialog()


	def on_context_menu_selection_done(self, widget):
		"""
		Listener for when an app's context menu is closed
		"""

		widget = self._clicked_app_button
		self._toggle_app_button(widget, False)


	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list. This includes
		the "mouse click" event and the "clicked using keyboard" event (for example,
		when you press Enter), but not middle-clicks and right-clicks.
		"""

		ctrl_is_pressed = self._get_ctrl_key_state()
		shift_is_pressed = self._get_shift_key_state()
		self._cardapio.handle_app_clicked(widget.app_info, 1, ctrl_is_pressed, shift_is_pressed)

		self._toggle_app_button(widget, False)


	def on_app_button_button_pressed(self, widget, event):
		"""
		Respond to mouse click events onto app buttons. Either launch an app or
		show context menu depending on the button pressed.
		"""

		# avoid left-click activating the button twice, since single-left-click
		# is already handled in the on_app_button_clicked() method
		if event.button == 1: return 

		# toggle app buttons that are right-clicked
		if event.button == 3:
			self._toggle_app_button(widget, True)

		else:
			self._toggle_app_button(widget, False)

		self._clicked_app_button = widget
		self._cardapio.handle_app_clicked(widget.app_info, event.button, False, False)


	def on_view_mode_toggled(self, widget):
		"""
		Handler for when the "system menu" button is toggled
		"""

		if self._auto_toggled_view_mode_button:
			self._auto_toggled_view_mode_button = False
			return True

		self._cardapio.handle_view_mode_toggled(widget.get_active())


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

		w = self.main_window.get_focus()

		if w != self.search_entry and w == self._previously_focused_widget:

			if event.is_modifier: return
			if self._handle_if_key_combo(event): return

			# Catch it when the user pressed Shift-Enter and Ctrl-Enter when
			# focused on a button
			if event.keyval == gtk.gdk.keyval_from_name('Return'):
				self.on_app_button_clicked(w)
				return

			self.main_window.set_focus(self.search_entry)
			self.search_entry.set_position(len(self.search_entry.get_text()))
			
			self.search_entry.emit('key-press-event', event)

		else:
			self._previously_focused_widget = None


	def on_mainwindow_key_pressed(self, widget, event):
		"""
		This is a trick to make sure the user isn't already typing at the
		search entry when we redirect all keypresses to the search entry.
		Because that would enter two of each key.
		"""

		if self.main_window.get_focus() != self.search_entry:
			self._previously_focused_widget = self.main_window.get_focus()


	def on_mainwindow_focus_out(self, widget, event):

		self._cardapio.handle_mainwindow_focus_out()


	def on_mainwindow_cursor_leave(self, widget, event):

		self._cardapio.handle_mainwindow_cursor_leave()


	def on_mainwindow_delete_event(self, widget, event):

		self._cardapio.handle_user_closing_mainwindow()


	def on_search_entry_icon_pressed(self, widget, iconpos, event):

		self._cardapio.handle_search_entry_icon_pressed()


	def on_search_entry_activate(self, widget):

		pass
		#ctrl_is_pressed = self._get_ctrl_key_state()
		#shift_is_pressed = self._get_shift_key_state()
		#self._cardapio.handle_search_entry_activate(ctrl_is_pressed, shift_is_pressed)


	def on_about_gnome_clicked(self, widget):
		"""
		Opens the "About Gnome" dialog.
		"""

		self._cardapio.handle_about_menu_item_clicked('AboutGnome')


	def on_about_distro_clicked(self, widget):
		"""
		Opens the "About %distro%" dialog
		"""

		self._cardapio.handle_about_menu_item_clicked('AboutDistro')


	def on_options_menu_item_clicked(self, *dummy):
		"""
		Opens Cardapio's options dialog	
		"""

		self._cardapio.open_options_dialog()


	def on_edit_menu_item_clicked(self, *dummy):
		"""
		Open the menu editor app
		"""

		self._cardapio.handle_editor_menu_item_clicked()

		
	def on_search_entry_changed(self, *dummy):

		self._cardapio.handle_search_entry_changed()


	def on_search_entry_key_pressed(self, widget, event):
		"""
		Handler for when the user presses a key when the search entry is
		focused.
		"""

		if event.keyval == gtk.gdk.keyval_from_name('Tab'):
			self._cardapio.handle_search_entry_tab_pressed()

		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):
			self._cardapio.handle_search_entry_escape_pressed()

		elif event.keyval == gtk.gdk.keyval_from_name('Return'):
			ctrl_is_pressed = self._get_ctrl_key_state()
			shift_is_pressed = self._get_shift_key_state()
			self._cardapio.handle_search_entry_activate(ctrl_is_pressed, shift_is_pressed)

		elif self._handle_if_key_combo(event): 
			# this case is handled inherently by the handle_* function above
			pass 

		else: return False
		return True


	def on_main_splitter_clicked(self, widget, event):
		"""
		Make sure user can't move the splitter when in mini mode
		"""

		# TODO: collapse to mini mode when main_splitter is clicked (but not dragged)
		#if event.type == gtk.gdk.BUTTON_PRESS:

		if event.button == 1:
			if self._cardapio.settings['mini mode']:
				# block any other type of clicking when in mini mode
				return True


	def on_pin_this_app_clicked(self, widget):

		self._cardapio.handle_pin_this_app_clicked(self._clicked_app_button.app_info)


	def on_unpin_this_app_clicked(self, widget):

		self._cardapio.handle_unpin_this_app_clicked(self._clicked_app_button.app_info)


	def on_add_to_side_pane_clicked(self, widget):

		self._cardapio.handle_add_to_side_pane_clicked(self._clicked_app_button.app_info)


	def on_remove_from_side_pane_clicked(self, widget):

		self._cardapio.handle_remove_from_side_pane_clicked(self._clicked_app_button.app_info)


	def on_open_parent_folder_pressed(self, widget):

		self._cardapio.handle_open_parent_folder_pressed(self._clicked_app_button.app_info)


	def on_launch_in_background_pressed(self, widget):

		self._cardapio.handle_launch_in_background_pressed(self._clicked_app_button.app_info)


	def on_peek_inside_pressed(self, widget):

		self._cardapio.handle_peek_inside_pressed(self._clicked_app_button.app_info)


	def on_eject_pressed(self, widget):

		self._cardapio.handle_eject_pressed(self._clicked_app_button.app_info)


	def on_open_app_pressed(self, widget):

		self._cardapio.handle_launch_app_pressed(self._clicked_app_button.app_info)


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
		
		icon_pixbuf = self._get_icon_pixbuf_from_app_info(button.app_info)
		button.drag_source_set_icon_pixbuf(icon_pixbuf)


	def on_app_button_data_get(self, button, drag_context, selection_data, info, time):
		"""
		In a drag-and-drop operation, send the drop target some information 
		about the dragged app.
		"""

		app_uri = self._cardapio.get_app_uri_for_drag_and_drop(button.app_info)
		selection_data.set_uris([app_uri])


	def on_back_button_clicked(self, widget):
		"""
		Handler for when the "back" button is clicked.
		"""
		self._cardapio.handle_back_button_clicked()


	def on_resize_started(self, widget, event):
		"""
		This function is used to emulate the window manager's resize function
		from Cardapio's borderless window.
		"""

		window_x, window_y = self.main_window.get_position()
		x = event.x_root - window_x
		y = event.y_root - window_y
		window_width, window_height = self.main_window.get_size()
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

		# see the note in show_main_window()
		#gtk.gdk.keyboard_ungrab(0)
		#gtk.gdk.pointer_ungrab(0)

		self.main_window.window.begin_resize_drag(edge, event.button, x, y, event.time)


	def on_resize_ended(self, *dummy):
		"""
		This function is called when the user releases the mouse after resizing the
		Cardapio window.
		"""

		self._cardapio.handle_resize_done()
		self.unblock_focus_out_event()


	def on_reload_button_clicked(self, widget):
		self._cardapio.handle_reload_clicked()


