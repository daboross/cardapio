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


except Exception, exception:
	fatal_error("Fatal error loading Cardapio's GTK interface", exception)
	sys.exit(1)

if gtk.ver < (2, 14, 0):
	fatal_error("Fatal error loading Cardapio's GTK interface", 'Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


class CardapioGtkView:

	def __init__(self, cardapio):

		self.cardapio = cardapio
		self.focus_out_blocked = False


	def setup_base_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		self.rebuild_timer = None

		main_ui_filepath    = os.path.join(self.cardapio.cardapio_path, 'ui', 'cardapio.ui')
		options_ui_filepath = os.path.join(self.cardapio.cardapio_path, 'ui', 'options.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(self.cardapio.APP)
		builder.add_from_file(main_ui_filepath)
		builder.add_from_file(options_ui_filepath)
		builder.connect_signals(self.cardapio)

		self.get_widget = builder.get_object
		self.window                    = self.get_widget('CardapioWindow')
		self.message_window            = self.get_widget('MessageWindow')
		self.about_dialog              = self.get_widget('AboutDialog')
		self.options_dialog            = self.get_widget('OptionsDialog')
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
		self.cardapio.app_menu_separator        = self.get_widget('AppMenuSeparator')
		self.cardapio.pin_menuitem              = self.get_widget('PinMenuItem')
		self.cardapio.unpin_menuitem            = self.get_widget('UnpinMenuItem')
		self.cardapio.add_side_pane_menuitem    = self.get_widget('AddSidePaneMenuItem')
		self.cardapio.remove_side_pane_menuitem = self.get_widget('RemoveSidePaneMenuItem')
		self.cardapio.open_folder_menuitem      = self.get_widget('OpenParentFolderMenuItem')
		self.cardapio.peek_inside_menuitem      = self.get_widget('PeekInsideMenuItem')
		self.cardapio.eject_menuitem            = self.get_widget('EjectMenuItem')
		self.cardapio.plugin_tree_model         = self.get_widget('PluginListstore')
		self.cardapio.plugin_checkbox_column    = self.get_widget('PluginCheckboxColumn')
		self.cardapio.view_mode_button          = self.get_widget('ViewModeButton')
		self.cardapio.main_splitter             = self.get_widget('MainSplitter')

		# start with any search entry -- doesn't matter which
		self.cardapio.search_entry = self.get_widget('TopLeftSearchEntry')

		# HACK: fix names of widgets to allow theming
		# (glade doesn't seem to properly add names to widgets anymore...)
		for widget in builder.get_objects():

			# skip the about dialog or the app name will be overwritten!
			if widget == self.about_dialog: continue

			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		self.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)

		# dynamic translation of MenuItem defined in .ui file
		about_distro_label = _('_About %(distro_name)s') % {'distro_name' : self.cardapio.distro_name}
		self.get_widget('AboutDistroMenuItem').set_label(about_distro_label)

		# grab some widget properties from the ui file
		self.cardapio.section_label_attributes = self.get_widget('SectionName').get_attributes()
		self.cardapio.fullsize_mode_padding = self.get_widget('CategoryMargin').get_padding()

		# make sure buttons have icons!
		self.cardapio.gtk_settings = gtk.settings_get_default()
		self.cardapio.gtk_settings.set_property('gtk-button-images', True)
		self.cardapio.gtk_settings.connect('notify', self.cardapio.on_gtk_settings_changed)

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


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self.cardapio.auto_toggled_sidebar_button:
			self.cardapio.auto_toggled_sidebar_button = False
			return True

		if self.cardapio.selected_section is None:
			self.cardapio.search_entry.set_text('')
			widget.set_sensitive(False)

		else:
			self.cardapio.untoggle_and_show_all_sections()


	def on_sidebar_button_clicked(self, widget, section_slab):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self.cardapio.auto_toggled_sidebar_button:
			self.cardapio.auto_toggled_sidebar_button = False
			return True

		if self.cardapio.selected_section == section_slab:
			self.cardapio.selected_section = None # necessary!
			self.cardapio.untoggle_and_show_all_sections()
			return True

		self.cardapio.toggle_and_show_section(section_slab)


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
		Stop window from hiding when context menu is shown
		"""

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self.view.block_focus_out_event()
			glib.timeout_add(Cardapio.FOCUS_BLOCK_INTERVAL, self.view.unblock_focus_out_event)


	# This method is part of the View API
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
		self.cardapio.show_window_on_top(self.message_window)

		# ensure window is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()


	# This method is part of the View API
	def show_about_dialog(self):
		"""
		Shows the "About" dialog
		"""

		self.about_dialog.show()


	# This method is part of the View API
	def show_options_dialog(self, state):
		"""
		Shows the "Options" dialog
		"""

		if state : self.options_dialog.show()
		else     : self.options_dialog.hide()


	# This method is part of the View API
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


	# This method is part of the View API
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


	# This method is part of the View API
	def clear_plugin_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""

		for menu_item in self.app_context_menu:
			if menu_item.name is not None and menu_item.name.startswith('PluginAction'):
				self.app_context_menu.remove(menu_item)

