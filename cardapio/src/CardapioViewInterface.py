
class CardapioViewInterface:

	APP_BUTTON      = 0
	CATEGORY_BUTTON = 1
	SESSION_BUTTON  = 2
	SIDEPANE_BUTTON = 3

	PIN_MENUITEM               = 0
	UNPIN_MENUITEM             = 1
	ADD_SIDE_PANE_MENUITEM     = 2
	REMOVE_SIDE_PANE_MENUITEM  = 3
	OPEN_FOLDER_MENUITEM       = 4
	PEEK_INSIDE_MENUITEM       = 5
	EJECT_MENUITEM             = 6

	# TODO: Add virtual methods here, once they are well-defined

	def setup_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""
		pass


	def set_sidebar_button_toggled(self, button, state):
		"""
		Toggle a sidebar button
		"""
		pass


	def set_all_sections_sidebar_button_toggled(self, state, is_system_mode):
		"""
		Toggle the "All" sidebar button for either the main mode or
		the system mode sidebar.
		"""
		pass


	def set_all_sections_sidebar_button_sensitive(self, state, is_system_mode):
		"""
		Makes the "All" button unclickable
		"""
		pass


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""
		pass


	def show_section(self, section):
		"""
		Shows a given application section
		"""
		pass


	def hide_section(self, section):
		"""
		Hides a given application section
		"""
		pass


	def hide_sections(self, sections):
		"""
		Hides the application sections listed in the array "sections"
		"""
		pass


	def clear_search_entry(self):
		"""
		Removes all text from the search entry.
		"""
		pass


	def set_search_entry_text(self, text):
		"""
		Removes all text from the search entry.
		"""
		pass


	def get_search_entry_text(self):
		"""
		Gets the text that is currently displayed in the search entry, formatted
		in UTF8.
		"""
		pass


	def show_message_window(self):
		"""
		Show the "Rebuilding..." message window
		"""
		pass


	def hide_message_window(self):
		"""
		Hide the "Rebuilding..." message window
		"""
		pass


	def show_main_window(self):
		"""
		Show's Cardapio's main window
		"""
		pass


	def open_about_dialog(self):
		"""
		Shows the "About" dialog
		"""
		pass


	def show_executable_file_dialog(self, primary_text, secondary_text, hide_terminal_option):
		"""
		Opens a dialog similar to the one in Nautilus, that asks whether an
		executable script should be launched or edited.
		"""
		pass


	def block_focus_out_event(self):
		"""
		Blocks the focus-out event
		"""
		pass


	def fill_plugin_context_menu(self, clicked_app_info_context_menu):
		"""
		Add plugin-related actions to the context menu
		"""
		pass


	def clear_plugin_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""
		pass


	def show_context_menu_option(self, menu_item):
		"""
		Shows the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""
		pass


	def hide_context_menu_option(self, menu_item):
		"""
		Hides the context menu option specified by "menu_item". The "menu_item"
		parameter is one of the *_MENUITEM constants declared in
		CardapioViewInterface.
		"""
		pass


	def popup_app_context_menu(self, app_info):
		"""
		Show context menu for app buttons
		"""
		pass


	def set_view_mode_button_toggled(self, state):
		"""
		Toggle the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		pass


	def show_view_mode_button(self):
		"""
		Shows the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		pass


	def hide_view_mode_button(self):
		"""
		Hides the "view mode" button, which switches between "app view" and
		"control center" view
		"""
		pass


	def set_main_splitter_position(self, position):
		"""
		Set the position of the "splitter" which separates the sidepane from the
		app pane
		"""
		pass


	def get_main_splitter_position(self):
		"""
		Get the position of the "splitter" which separates the sidepane from the
		app pane
		"""
		pass


	def get_window_size(self):
		"""
		Get the width and height of the Cardapio window
		"""
		pass


	def apply_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""
		pass


	def get_cursor_coordinates(self):
		"""
		Returns the x,y coordinates of the mouse cursor with respect
		to the current screen.
		"""
		pass


	def get_screen_dimensions(self):
		"""
		Returns usable dimensions of the current desktop in a form of
		a tuple: (x, y, width, height). If the real numbers can't be
		determined, returns the size of the whole screen instead.
		"""
		pass


	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""
		pass


	def get_first_visible_app(self):
		"""
		Returns the app_info for the first app in the right pane, if any.
		"""
		pass


	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""
		pass


	def place_text_cursor_at_end(self):
		"""
		Places the text cursor at the end of the search entry's text
		"""
		pass


	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""
		pass


	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""
		pass


	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""
		pass


	def show_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		pass


	def hide_navigation_buttons(self):
		"""
		Shows the row of navigation buttons on top of the main app pane.
		"""
		pass


	def add_button(self, button_str, icon_name, parent_widget, tooltip, button_type):
		"""
		Adds a button to a parent container
		"""
		pass


	def setup_button_drag_and_drop(self, button, is_desktop_file):
		"""
		Sets up the event handlers for drag-and-drop
		"""
		pass


	def get_section_from_button(self, button):
		"""
		Returns a unique handler describing the section that a given app button
		belongs to
		"""
		pass


	def pre_build_ui(self):
		"""
		Prepares the UI before building any of the actual content-related widgets
		"""
		pass


	def post_build_ui(self):
		"""
		Performs operations after building the actual content-related widgets
		"""
		pass


	def build_all_sections_sidebar_buttons(self, title, tooltip):
		"""
		Creates the "All sections" buttons for both the regular and system modes
		"""
		pass


	def build_no_results_slab(self):
		"""
		Creates the slab that will be used to display the "No results to show" text
		"""
		pass


	def build_subfolders_slab(self, title, tooltip):
		"""
		Creates the Folder Contents slab to the app pane
		"""
		pass


	def build_uncategorized_slab(self, title, tooltip):
		"""
		Creates the Uncategorized slab to the app pane
		"""
		pass


	def build_session_slab(self, title, tooltip):
		"""
		Creates the Session slab to the app pane
		"""
		pass


	def build_system_slab(self, title, tooltip):
		"""
		Creates the System slab to the app pane
		"""
		pass


	def build_places_slab(self, title, tooltip):
		"""
		Creates the Places slab to the app pane
		"""
		pass


	def build_pinneditems_slab(self, title, tooltip):
		"""
		Creates the Pinned Items slab to the app pane
		"""
		pass


	def build_sidepane_slab(self, title, tooltip):
		"""
		Creates the Side Pane slab to the app pane
		"""
		pass


	def remove_about_context_menu_items(self):
		"""
		Removes "About Gnome" and "About %distro" from Cardapio's context menu
		"""
		pass


	def show_window_frame(self):
		"""
		Shows the window frame around Cardapio
		"""
		pass


	def hide_window_frame(self):
		"""
		Hides the window frame around Cardapio
		"""
		pass


	def remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section slab
		"""
		pass


	def remove_all_buttons_from_category_panes(self):
		"""
		Removes all buttons from both the regular and system category panes
		(i.e. the category filter lists)
		"""
		pass


	def toggle_mini_mode_ui(self, update_window_size = True):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""
		pass


	def setup_search_entry(self, place_at_top, place_at_left):
		"""
		Hides 3 of the 4 search entries and returns the visible entry.
		"""
		pass


	def focus_search_entry(self):
		"""
		Focuses the search entry
		"""
		pass



