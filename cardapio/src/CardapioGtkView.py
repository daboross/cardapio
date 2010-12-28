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
		self.cardapio.window                    = self.get_widget('CardapioWindow')
		self.cardapio.message_window            = self.get_widget('MessageWindow')
		self.cardapio.about_dialog              = self.get_widget('AboutDialog')
		self.cardapio.options_dialog            = self.get_widget('OptionsDialog')
		self.cardapio.executable_file_dialog    = self.get_widget('ExecutableFileDialog')
		self.cardapio.application_pane          = self.get_widget('ApplicationPane')
		self.cardapio.category_pane             = self.get_widget('CategoryPane')
		self.cardapio.system_category_pane      = self.get_widget('SystemCategoryPane')
		self.cardapio.sidepane                  = self.get_widget('SideappPane')
		self.cardapio.scroll_adjustment         = self.get_widget('ScrolledWindow').get_vadjustment()
		self.cardapio.left_session_pane         = self.get_widget('LeftSessionPane')
		self.cardapio.right_session_pane        = self.get_widget('RightSessionPane')
		self.cardapio.context_menu              = self.get_widget('CardapioContextMenu')
		self.cardapio.app_context_menu          = self.get_widget('AppContextMenu')
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
			if widget == self.cardapio.about_dialog: continue

			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		self.cardapio.icon_helper = IconHelper()
		self.cardapio.icon_helper.register_icon_theme_listener(self.cardapio.schedule_rebuild)

		self.cardapio.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)

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

		self.cardapio.window.set_keep_above(True)

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




