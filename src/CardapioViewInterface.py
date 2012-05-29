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

class CardapioViewInterface:

	# all these constants can be overridden, so long as they
	# maintain their uniqueness (within their own groups)

	APPLICATION_PANE          = 100
	CATEGORY_PANE             = 101
	SYSTEM_CATEGORY_PANE      = 102
	SIDE_PANE                 = 103
	LEFT_SESSION_PANE         = 104
	RIGHT_SESSION_PANE        = 105

	SUBFOLDERS_SECTION        = 200
	SESSION_SECTION           = 201
	SYSTEM_SECTION            = 202
	SIDEPANE_SECTION          = 203
	UNCATEGORIZED_SECTION     = 204
	PLACES_SECTION            = 205
	FAVORITES_SECTION         = 206

	PIN_MENUITEM              = 300
	UNPIN_MENUITEM            = 301
	ADD_SIDE_PANE_MENUITEM    = 302
	REMOVE_SIDE_PANE_MENUITEM = 303
	OPEN_PARENT_MENUITEM      = 304
	PEEK_INSIDE_MENUITEM      = 305
	EJECT_MENUITEM            = 306
	OPEN_MENUITEM             = 307
	SEPARATOR_MENUITEM        = 308

	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details.
		"""
		raise NotImplementedError("You must implement this method!")


	def set_sidebar_button_toggled(self, button, state):
		"""
		Toggle a sidebar button
		"""
		raise NotImplementedError("You must implement this method!")


	def set_all_sections_sidebar_button_toggled(self, state, is_system_mode):
		"""
		Toggle the "All" sidebar button for either the main mode or
		the system mode sidebar.
		"""
		raise NotImplementedError("You must implement this method!")


	def set_all_sections_sidebar_button_sensitive(self, state, is_system_mode):
		"""
		Makes the "All" button unclickable
		"""
		raise NotImplementedError("You must implement this method!")


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""
		raise NotImplementedError("You must implement this method!")


	def show_section(self, section):
		"""
		Shows a given application section
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_section(self, section):
		"""
		Hides a given application section
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_sections(self, sections):
		"""
		Hides the application sections listed in the array "sections"
		"""
		raise NotImplementedError("You must implement this method!")


	def clear_search_entry(self):
		"""
		Removes all text from the search entry.
		"""
		raise NotImplementedError("You must implement this method!")


	def set_search_entry_text(self, text):
		"""
		Removes all text from the search entry.
		"""
		raise NotImplementedError("You must implement this method!")


	def get_search_entry_text(self):
		"""
		Gets the text that is currently displayed in the search entry, formatted
		in UTF8.
		"""
		raise NotImplementedError("You must implement this method!")


	def show_message_window(self):
		"""
		Show the "Rebuilding..." message window
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_message_window(self):
		"""
		Hide the "Rebuilding..." message window
		"""
		raise NotImplementedError("You must implement this method!")


	def show_main_window(self):
		"""
		Show's Cardapio's main window
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_main_window(self):
		"""
		Hides Cardapio's main window
		"""
		raise NotImplementedError("You must implement this method!")


	def open_about_dialog(self):
		"""
		Shows the "About" dialog
		"""
		raise NotImplementedError("You must implement this method!")


	def show_executable_file_dialog(self, primary_text, secondary_text, hide_terminal_option):
		"""
		Opens a dialog similar to the one in Nautilus, that asks whether an
		executable script should be launched or edited.
		"""
		raise NotImplementedError("You must implement this method!")


	def block_focus_out_event(self):
		"""
		Blocks the focus-out event
		"""
		raise NotImplementedError("You must implement this method!")


	def fill_plugin_context_menu(self, clicked_app_info_context_menu):
		"""
		Add plugin-related actions to the context menu
		"""
		raise NotImplementedError("You must implement this method!")


	def clear_plugin_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""
		raise NotImplementedError("You must implement this method!")


	def show_context_menu_option(self, menu_item):
		"""
		Shows the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_context_menu_option(self, menu_item):
		"""
		Hides the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""
		raise NotImplementedError("You must implement this method!")


	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""
		raise NotImplementedError("You must implement this method!")


	def set_view_mode_button_toggled(self, state):
		"""
		Toggle the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		raise NotImplementedError("You must implement this method!")


	def show_view_mode_button(self):
		"""
		Shows the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_view_mode_button(self):
		"""
		Hides the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		raise NotImplementedError("You must implement this method!")


	def set_main_splitter_position(self, position):
		"""
		Set the position of the "splitter" which separates the sidepane from the
		app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def get_main_splitter_position(self):
		"""
		Get the position of the "splitter" which separates the sidepane from the
		app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def get_window_size(self):
		"""
		Get the width and height of the Cardapio window
		"""
		raise NotImplementedError("You must implement this method!")


	def get_window_position(self):
		"""
		Get the x,y coordinates of the top-left corner of the Cardapio window
		"""
		raise NotImplementedError("You must implement this method!")


	def apply_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""
		raise NotImplementedError("You must implement this method!")


	def get_cursor_coordinates(self):
		"""
		Returns the x,y coordinates of the mouse cursor with respect
		to the current screen.
		"""
		raise NotImplementedError("You must implement this method!")


	def get_monitor_dimensions(self, x, y):
		"""
		Returns the dimensions of the monitor that contains the point x,y.  It
		would be *great* if these dimensions could be the *usable* dimensions,
		but it seems that the xdesktop spec does not define a way to get this...
		"""
		raise NotImplementedError("You must implement this method!")


	def get_screen_dimensions(self):
		"""
		Returns usable dimensions of the current desktop in a form of
		a tuple: (x, y, width, height). If the real numbers can't be
		determined, returns the size of the whole screen instead.
		"""
		raise NotImplementedError("You must implement this method!")


	def is_window_visible(self):
		"""
		Returns True if the main window is visible
		"""
		raise NotImplementedError("You must implement this method!")


	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""
		raise NotImplementedError("You must implement this method!")


	def focus_first_visible_app(self):
		"""
		Focuses the first visible button in the app pane.
		"""
		raise NotImplementedError("You must implement this method!")


	def get_nth_visible_app(self, n):
		"""
		Returns the app_info for the nth app in the right pane, if any.
		"""
		raise NotImplementedError("You must implement this method!")


	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""
		raise NotImplementedError("You must implement this method!")


	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the search entry's text
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""
		raise NotImplementedError("You must implement this method!")


	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""
		raise NotImplementedError("You must implement this method!")


	def show_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		raise NotImplementedError("You must implement this method!")


	def add_app_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the app pane, and returns a handler to it
		"""
		raise NotImplementedError("You must implement this method!")


	def add_category_button(self, button_str, icon_name, pane_or_section, section, tooltip):
		"""
		Adds a toggle-button to the category pane, and returns a handler to it
		"""
		raise NotImplementedError("You must implement this method!")


	def add_session_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the session pane, and returns a handler to it
		"""
		raise NotImplementedError("You must implement this method!")


	def add_sidepane_button(self, button_str, icon_name, pane_or_section, tooltip):
		"""
		Adds a button to the sidepane, and returns a handler to it
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_button(self, button):
		"""
		Hides a button
		"""
		raise NotImplementedError("You must implement this method!")


	def setup_button_drag_and_drop(self, button, is_desktop_file):
		"""
		Sets up the event handlers for drag-and-drop
		"""
		raise NotImplementedError("You must implement this method!")


	def get_section_from_button(self, button):
		"""
		Returns a unique handler describing the section that a given app button
		belongs to
		"""
		raise NotImplementedError("You must implement this method!")


	def pre_build_ui(self):
		"""
		Prepares the UI before building any of the actual content-related widgets
		"""
		raise NotImplementedError("You must implement this method!")


	def post_build_ui(self):
		"""
		Performs operations after building the actual content-related widgets
		"""
		raise NotImplementedError("You must implement this method!")


	def build_all_sections_sidebar_buttons(self, title, tooltip):
		"""
		Creates the "All sections" buttons for both the regular and system modes
		"""
		raise NotImplementedError("You must implement this method!")


	def build_no_results_section(self):
		"""
		Creates the section that will be used to display the "No results to show" text
		"""
		raise NotImplementedError("You must implement this method!")


	def build_subfolders_section(self, title, tooltip):
		"""
		Creates the Folder Contents section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_uncategorized_section(self, title, tooltip):
		"""
		Creates the Uncategorized section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_session_section(self, title, tooltip):
		"""
		Creates the Session section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_system_section(self, title, tooltip):
		"""
		Creates the System section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_places_section(self, title, tooltip):
		"""
		Creates the Places section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_pinneditems_section(self, title, tooltip):
		"""
		Creates the Pinned Items section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def build_sidepane_section(self, title, tooltip):
		"""
		Creates the Side Pane section to the app pane
		"""
		raise NotImplementedError("You must implement this method!")


	def remove_about_context_menu_items(self):
		"""
		Removes "About Gnome" and "About %distro" from Cardapio's context menu
		"""
		raise NotImplementedError("You must implement this method!")


	def show_window_frame(self):
		"""
		Shows the window frame around Cardapio
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_window_frame(self):
		"""
		Hides the window frame around Cardapio
		"""
		raise NotImplementedError("You must implement this method!")


	def remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section or from a pane
		"""
		raise NotImplementedError("You must implement this method!")


	def remove_all_buttons_from_category_panes(self):
		"""
		Removes all buttons from both the regular and system category panes
		(i.e. the category filter lists)
		"""
		raise NotImplementedError("You must implement this method!")


	def toggle_mini_mode_ui(self, update_window_size = True):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""
		raise NotImplementedError("You must implement this method!")


	def setup_search_entry(self, place_at_top, place_at_left):
		"""
		Hides 3 of the 4 search entries and returns the visible entry.
		"""
		raise NotImplementedError("You must implement this method!")


	def focus_search_entry(self):
		"""
		Focuses the search entry
		"""
		raise NotImplementedError("You must implement this method!")


	def show_section_status_text(self, section, text):
		"""
		Shows some status text inside a section (for instance, this is called to
		write the "loading..." text for slow plugins).
		"""
		raise NotImplementedError("You must implement this method!")


	def run_in_ui_thread(self, function, *args, **kwargs):
		"""
		Runs a function making sure that no other thread can write to the UI.
		"""
		raise NotImplementedError("You must implement this method!")


	def add_application_section(self, section_title):
		"""
		Adds a new section to the applications pane
		"""
		raise NotImplementedError("You must implement this method!")


	def quit(self):
		"""
		Do the last cleaning up you need to do --- this is the last thing that
		happens before Cardapio closes.
		"""
		raise NotImplementedError("You must implement this method!")


	def show_pane(self, pane):
		"""
		Show the pane given by one of the *_PANE constants
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_pane(self, pane):
		"""
		Hide the pane given by one of the *_PANE constants
		"""
		raise NotImplementedError("You must implement this method!")


	def resize_main_window(self, width, height):
		"""
		Resizes the main Cardapio window
		"""
		raise NotImplementedError("You must implement this method!")


	def move_main_window(self, x, y, anchor_right, anchor_bottom):
		"""
		Moves the main Cardapio window, obeying the anchor_* booleans
		"""
		raise NotImplementedError("You must implement this method!")


	def set_subfolder_section_title(self, title):
		"""
		Sets the title of the subfolder section
		"""
		raise NotImplementedError("You must implement this method!")


	def show_rebuild_required_bar(self):
		"""
		Shows the "rebuild required" bar, which allows the user to click the
		"reload" button, which rebuilds all of Cardapio's menus
		"""
		raise NotImplementedError("You must implement this method!")


	def hide_rebuild_required_bar(self):
		"""
		Hide the "rebuild required" bar.
		"""
		raise NotImplementedError("You must implement this method!")


	def set_screen(self, screen_number):
		"""
		Sets the screen where the view will be shown (given as an integer)
		"""
		raise NotImplementedError("You must implement this method!")


	def get_screen_with_pointer(self):
		"""
		Returns the number of the screen that currently contains the mouse
		pointer
		"""
		raise NotImplementedError("You must implement this method!")


	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the text entry
		"""
		raise NotImplementedError("You must implement this method!")


