#
#  Cardapio is an alternative Gnome menu applet, launcher, and much more!
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

# TODO: fix shift-tab from first app widget
# TODO: alt-1, ..., alt-9, alt-0 should activate 1st, ..., 9th, 10th results
# TODO: ctrl-1, ..., ctrl-9, ctrl-0 should activate categories
# TODO: grid view / multiple columns when window is wide enough (like gnome-control-center)
# TODO: add "most recent" and "most frequent" with a zeitgeist plugin
# plus other TODO's elsewhere in the code...

# these imports are outside of the "try" block because it defines
# the function fatal_error(), which is used in the "except"
from misc import *
import sys

try:
	from icons import *
	from settings import *
	from hacks import *
	from CardapioPluginInterface import CardapioPluginInterface
	from CardapioAppletInterface import *

	import gc
	import os
	import re
	import gtk
	import gio
	import glib
	import json
	import gmenu
	import urllib2
	import gettext
	import logging
	import platform
	import keybinder
	import traceback
	import subprocess
	import dbus, dbus.service

	from time import time
	from xdg import DesktopEntry
	from pango import ELLIPSIZE_END
	from threading import Lock, Thread
	from locale import setlocale, LC_ALL
	from dbus.mainloop.glib import DBusGMainLoop

except Exception, exception:
	fatal_error('Fatal error loading Cardapio', exception)
	sys.exit(1)

try:
	from gnome import execute_terminal_shell as gnome_execute_terminal_shell

except Exception, exception:
	print('Warning: you will not be able to execute scripts in the terminal')
	gnome_execute_terminal_shell = None

try:
	from gnome import program_init as gnome_program_init
	from gnome.ui import master_client as gnome_ui_master_client

except Exception, exception:
	print('Warning: Cardapio will not be able to tell when the session is closed')
	gnome_program_init     = None
	gnome_ui_master_client = None


if gtk.ver < (2, 14, 0):
	fatal_error('Fatal error loading Cardapio', 'Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


# Set up translations

# try path like /usr/share/locale
cardapio_path = os.path.dirname(os.path.realpath(__file__))
prefix_path = cardapio_path.split(os.path.sep)[:-2]
prefix_path = [os.path.sep] + prefix_path + ['share', 'locale']
prefix_path = os.path.join(*prefix_path)

# try path like cardapio_path/../locale
if not os.path.exists(prefix_path):
	prefix_path = cardapio_path.split(os.path.sep)[:-1]
	prefix_path = [os.path.sep] + prefix_path + ['locale']
	prefix_path = os.path.join(*prefix_path)

DIR = prefix_path
APP = 'cardapio'

setlocale(LC_ALL, '')
gettext.bindtextdomain(APP, DIR)

if hasattr(gettext, 'bind_textdomain_codeset'):
    gettext.bind_textdomain_codeset(APP, 'UTF-8')

gettext.textdomain(APP)
_ = gettext.gettext


# Hack for making translations work with ui files

import gtk.glade
gtk.glade.bindtextdomain(APP, DIR)
gtk.glade.textdomain(APP)


# Main Cardapio class

class Cardapio(dbus.service.Object):

	distro_name = platform.linux_distribution()[0]

	MIN_VISIBILITY_TOGGLE_INTERVAL    = 0.200 # seconds (this is a bit of a hack to fix some focus problems)
	FOCUS_BLOCK_INTERVAL              = 50  # milliseconds

	LOG_FILE_MAX_SIZE                 = 1000000 # bytes

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	version = '0.9.163'

	core_plugins = [
			'applications',
			'command_launcher',
			'google',
			'google_localized',
			'pinned',
			'places',
			'software_center',
			'tracker',
			'tracker_fts',
			'zg_recent_documents',
			]

	required_plugins = ['applications', 'places', 'pinned']

	APP_BUTTON      = 0
	CATEGORY_BUTTON = 1
	SESSION_BUTTON  = 2
	SIDEPANE_BUTTON = 3

	DONT_SHOW       = 0
	SHOW_CENTERED   = 1
	SHOW_NEAR_MOUSE = 2

	REMOTE_PROTOCOLS = ['ftp', 'sftp', 'smb']

	class SafeCardapioProxy:
		pass

	def __init__(self, show = False, panel_applet = None, debug = False):
		"""
		Creates a instance of Cardapio.
		"""

		self.create_xdg_folders()  # must happen before logging is setup
		self.setup_log_file(debug)

		logging.info('----------------- Cardapio launched -----------------')
		logging.info('Cardapio version: %s' % Cardapio.version)
		logging.info('Distribution: %s' % platform.platform())

		logging.info('Loading settings...')

		try:
			self.settings = SettingsHelper(self.config_folder_path)

		except Exception, ex:
			msg = 'Unable to read settings: ' + str(ex)
			logging.error(msg)
			fatal_error('Settings error', msg)
			traceback.print_exc()
			sys.exit(1)

		logging.info('...done loading settings!')

		self.home_folder_path = os.path.abspath(os.path.expanduser('~'))
		self.visible                       = False
		self.app_list                      = []    # used for searching the regular menus
		self.sys_list                      = []    # used for searching the system menus
		self.section_list                  = {}
		self.current_query                 = ''
		self.subfolder_stack               = []
		self.selected_section              = None
		self.no_results_to_show            = False
		self.previously_focused_widget     = None
		self.opened_last_app_in_background = False
		self.auto_toggled_sidebar_button   = False
		self.auto_toggled_view_mode_button = False
		self.focus_out_blocked             = False
		self.clicked_app                   = None
		self.keybinding                    = None
		self.search_timer_local            = None
		self.search_timer_remote           = None
		self.search_timeout_local          = None
		self.search_timeout_remote         = None
		self.plugin_database               = {}
		self.keyword_to_plugin_mapping     = {}
		self.active_plugin_instances       = []
		self.in_system_menu_mode           = False
		self.plugins_still_searching       = 0
		self.bookmark_monitor              = None
		self.volume_monitor                = None
		self.last_visibility_toggle        = 0
		self.panel_applet                  = panel_applet

		self.sys_tree = gmenu.lookup_tree('gnomecc.menu')
		self.have_control_center = (self.sys_tree.root is not None)

		if not self.have_control_center:
			self.sys_tree = gmenu.lookup_tree('settings.menu')
			logging.warn('Could not find Control Center menu file. Deactivating Control Center button.')

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		self.package_root = ''
		if __package__ is not None:
			self.package_root = __package__ + '.'

		logging.info('Setting up DBus...')
		self.setup_dbus()
		logging.info('...done setting up DBus!')

		logging.info('Setting up UI...')
		self.setup_base_ui() # must be the first ui-related method to be called
		logging.info('...done setting up UI!')

		logging.info('Setting up panel applet (if any)...')
		self.setup_panel_applet()
		logging.info('...done setting up panel applet!')
			
		logging.info('Setting up Plugins...')
		self.setup_plugins()
		logging.info('...done setting up Plugins!')

		logging.info('Building UI...')
		self.build_ui()
		logging.info('...done building UI!')

		self.schedule_search_with_all_plugins('')

		if   show == Cardapio.SHOW_NEAR_MOUSE: self.show_hide_near_mouse()
		elif show == Cardapio.SHOW_CENTERED  : self.show()

		if gnome_program_init is not None:
			gnome_program_init('', self.version) # Prints a warning to the screen. Ignore it.
			client = gnome_ui_master_client()
			client.connect('save-yourself', self.save_and_quit)

		logging.info('==> Done initializing Cardapio!')


	def on_mainwindow_destroy(self, *dummy):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self.save_and_quit()


	def save_and_quit(self, *dummy):
		"""
		Saves the current state and quits
		"""

		try:
			self.settings.save()
		except Exception, ex:
			logging.error('error while saving settings: %s' % ex)
		self.quit()


	def quit(self, *dummy):
		"""
		Quits without saving the current state.
		"""

		logging.info('Exiting...')
		gtk.main_quit()


	def setup_log_file(self, debug):
		"""
		Opens the log file, clears it if it's too large, and prepares the logging module
		"""

		logging_filename = os.path.join(self.cache_folder_path, 'cardapio.log')

		if debug : logging_level = logging.DEBUG
		else     : logging_level = logging.INFO

		logging_format = r'%(relativeCreated)- 10d %(levelname)- 10s %(message)s'

		# clear log file if too large
		if os.path.exists(logging_filename) and os.path.getsize(logging_filename) > Cardapio.LOG_FILE_MAX_SIZE:
			try:
				logfile = open(logging_filename, 'w')
				logfile.close()

			except Exception, exception:
				fatal_error('Error clearing log file', exception)

		logging.basicConfig(filename = logging_filename, level = logging_level, format = logging_format)


	def setup_dbus(self):
		"""
		Sets up the session bus
		"""

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)


	def setup_panel_applet(self):
		"""
		Prepares Cardapio's applet in any of the compatible panels.
		"""

		if self.panel_applet is None:
			self.panel_applet = CardapioAppletInterface()

		if self.panel_applet.panel_type == PANEL_TYPE_GNOME2:
			self.get_widget('AboutGnomeMenuItem').set_visible(False)
			self.get_widget('AboutDistroMenuItem').set_visible(False)

		else:
			self.window.set_decorated(True)
			self.window.set_deletable(False) # remove "close" button from window frame (doesn't work with Compiz!)
			self.get_widget('MainWindowBorder').set_shadow_type(gtk.SHADOW_NONE)

		self.panel_applet.setup(self)


	def get_plugin_class(self, basename):
		"""
		Returns the CardapioPlugin class from the plugin at plugins/basename.py.
		If it fails, it returns a string decribing the error.
		"""

		package = '%splugins.%s' % (self.package_root, basename)
		try:
			plugin_module = __import__(package, fromlist = 'CardapioPlugin', level = -1)
		except:
			return 'Could not import the plugin module'

		plugin_class = plugin_module.CardapioPlugin

		if plugin_class.plugin_api_version != CardapioPluginInterface.plugin_api_version:
			return 'Incorrect API version'

		return plugin_class


	def build_plugin_database(self):
		"""
		Searches the plugins/ folder for .py files not starting with underscore.
		Creates the dict self.plugin_database indexed by the plugin filename's base name.
		"""

		self.plugin_database = {}

		self.plugin_database['applications'] = {
				'name'              : _('Application menu'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays installed applications'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'applications-other',
				'instance'          : None,
				}

		self.plugin_database['places'] = {
				'name'              : _('Places menu'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays a list of folders'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'folder',
				'instance'          : None,
				}

		self.plugin_database['pinned'] = {
				'name'              : _('Pinned items'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays the items that you marked as "pinned" using the context menu'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'emblem-favorite',
				'instance'          : None,
				}

		plugin_dirs = [
			os.path.join(cardapio_path, 'plugins'),
			os.path.join(DesktopEntry.xdg_config_home, 'Cardapio', 'plugins')
			]

		for plugin_dir in plugin_dirs:
			for root, dir_, files in os.walk(plugin_dir):
				for file_ in files:
					if len(file_) > 3 and file_[-3:] == '.py' and file_[0] != '_':
						basename = file_[:-3]
						plugin_class = self.get_plugin_class(basename)

						if type(plugin_class) is str: continue

						self.plugin_database[basename] = {
							'name'              : plugin_class.name,
							'author'            : plugin_class.author,
							'description'       : plugin_class.description,
							'version'           : plugin_class.version,
							'category name'     : plugin_class.category_name,
							'category icon'     : plugin_class.category_icon,
							'instance'          : None,
							}

		# TODO: figure out how to make Python unmap all the memory that gets
		# freed when the garbage collector releases the inactive plugins

	
	def activate_plugins_from_settings(self):
		"""
		Initializes plugins in the database if the user's settings say so.
		"""

		for basename in self.plugin_database:
			plugin = self.plugin_database[basename]['instance']
			if plugin is not None: plugin.__del__()
			self.plugin_database[basename]['instance'] = None

		self.active_plugin_instances = []
		self.keyword_to_plugin_mapping = {}

		all_plugin_settings = self.settings['plugin settings']

		for basename in self.settings['active plugins']:

			if basename in self.required_plugins: continue

			basename = str(basename)
			plugin_class = self.get_plugin_class(basename)

			if type(plugin_class) is str:
				logging.error('[%s] %s' % (basename, plugin_class))
				self.settings['active plugins'].remove(basename)
				continue

			logging.info('[%s] Initializing...' % basename)

			try:
				plugin = plugin_class(self.safe_cardapio_proxy)

			except Exception, exception:
				logging.error('[%s] Plugin did not load properly: uncaught exception.' % basename)
				logging.error(exception)
				self.settings['active plugins'].remove(basename)
				continue

			if not plugin.loaded:
				self.plugin_write_to_log(plugin, 'Plugin did not load properly')
				self.settings['active plugins'].remove(basename)
				continue

			logging.info('[%s]             ...done!' % basename)

			keyword = plugin.default_keyword
			show_only_with_keyword = False

			if basename in all_plugin_settings:

				plugin_settings = all_plugin_settings[basename]

				if 'keyword' in plugin_settings:
					keyword = plugin_settings['keyword']

				if 'show only with keyword' in plugin_settings:
					show_only_with_keyword = plugin_settings['show only with keyword']

			all_plugin_settings[basename] = {}
			all_plugin_settings[basename]['keyword'] = keyword
			all_plugin_settings[basename]['show only with keyword'] = show_only_with_keyword

			plugin.__is_running             = False
			plugin.__show_only_with_keyword = show_only_with_keyword

			if plugin.search_delay_type is not None:
				plugin.search_delay_type = plugin.search_delay_type.partition(' search update delay')[0]

			self.active_plugin_instances.append(plugin)
			self.plugin_database[basename]['instance'] = plugin
			self.keyword_to_plugin_mapping[keyword] = plugin

		gc.collect()


	def plugin_write_to_log(self, plugin, text, is_debug = False, is_warning = False, is_error = False):
		"""
		Writes 'text' to the log file, prefixing it with [plugin name]. Different
		levels of messages can be used by setting one of is_debug, is_warning, is_error:

		debug       - Used for any debugging message, including any messages that may
		              be privacy sensitive. Messages set with the flag is_debug=True
		              will *not* be logged unless the user enters debug mode.

		info        - This is the default level when you don't set any of the flags.
		              Used for things that normal users should see in their logs.

		warning     - Used for reporting things that have gone wrong, but that still
		              allow the plugin to function, even if partially.

		error       - Used for reporting things that have gone wrong, and which do not
		              allow the plugin to function at all.
		"""

		if is_error:
			write = logging.error

		elif is_warning:
			write = logging.warning

		elif is_debug:
			write = logging.debug

		else:
			write = logging.info

		write('[%s] %s'  % (plugin.name, text))


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section is None:
			self.search_entry.set_text('')
			widget.set_sensitive(False)

		else:
			self.untoggle_and_show_all_sections()


	def on_sidebar_button_clicked(self, widget, section_slab):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section == section_slab:
			self.selected_section = None # necessary!
			self.untoggle_and_show_all_sections()
			return True

		self.toggle_and_show_section(section_slab)


	def on_sidebar_button_hovered(self, widget):
		"""
		Handler for when the user hovers over a category in the sidebar
		"""

		widget.set_active(True)


	def create_xdg_folders(self):
		"""
		Creates Cardapio's config and cache folders (usually at ~/.config/Cardapio and
		~/.cache/Cardapio)
		"""

		self.config_folder_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio')

		if not os.path.exists(self.config_folder_path):
			os.mkdir(self.config_folder_path)

		elif not os.path.isdir(self.config_folder_path):
			fatal_error('Error creating config folder!', 'Cannot create folder "%s" because a file with that name already exists!' % self.config_folder_path)
			self.quit()

		self.cache_folder_path = os.path.join(DesktopEntry.xdg_cache_home, 'Cardapio')

		if not os.path.exists(self.cache_folder_path):
			os.mkdir(self.cache_folder_path)

		elif not os.path.isdir(self.cache_folder_path):
			fatal_error('Error creating cache folder!', 'Cannot create folder "%s" because a file with that name already exists!' % self.cache_folder_path)
			self.quit()


	def setup_base_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		self.rebuild_timer = None

		main_ui_filepath    = os.path.join(cardapio_path, 'ui', 'cardapio.ui')
		options_ui_filepath = os.path.join(cardapio_path, 'ui', 'options.ui')

		self.builder = gtk.Builder()
		self.builder.set_translation_domain(APP)
		self.builder.add_from_file(main_ui_filepath)
		self.builder.add_from_file(options_ui_filepath)
		self.builder.connect_signals(self)

		self.get_widget = self.builder.get_object
		self.window                    = self.get_widget('CardapioWindow')
		self.message_window            = self.get_widget('MessageWindow')
		self.about_dialog              = self.get_widget('AboutDialog')
		self.options_dialog            = self.get_widget('OptionsDialog')
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
		self.plugin_tree_model         = self.get_widget('PluginListstore')
		self.plugin_checkbox_column    = self.get_widget('PluginCheckboxColumn')
		self.view_mode_button          = self.get_widget('ViewModeButton')
		self.main_splitter             = self.get_widget('MainSplitter')

		self.search_entry              = self.get_widget('TopLeftSearchEntry') # start with any search entry -- doesn't matter which

		# HACK: fix names of widgets to allow theming
		# (glade doesn't seem to properly add names to widgets anymore...)
		for widget in self.builder.get_objects():

			# skip the about dialog or the app name will be overwritten!
			if widget == self.about_dialog: continue

			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		self.icon_helper = IconHelper()
		self.icon_helper.register_icon_theme_listener(self.schedule_rebuild)

		self.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)

		# dynamic translation of MenuItem defined in .ui file
		about_distro_label = _('_About %(distro_name)s') % {'distro_name' : Cardapio.distro_name}
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


	def setup_plugins(self):
		"""
		Reads all plugins from the plugin folders and activates the ones that
		have been specified in the settings file.
		"""

		self.safe_cardapio_proxy = Cardapio.SafeCardapioProxy()
		self.safe_cardapio_proxy.write_to_log = self.plugin_write_to_log
		self.safe_cardapio_proxy.handle_search_result = self.plugin_handle_search_result
		self.safe_cardapio_proxy.handle_search_error = self.plugin_handle_search_error
		self.safe_cardapio_proxy.ask_for_reload_permission = self.plugin_ask_for_reload_permission

		self.build_plugin_database()
		self.activate_plugins_from_settings() # investigate memory usage here


	def setup_ui_from_all_settings(self):
		"""
		Setup UI elements according to user preferences
		"""

		self.setup_ui_from_gui_settings()
		self.toggle_mini_mode_ui(update_window_size = False)


	def setup_ui_from_gui_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""

		if self.keybinding is not None:
			try: keybinder.unbind(self.keybinding)
			except: pass

		self.keybinding = self.settings['keybinding']
		keybinder.bind(self.keybinding, self.show_hide)

		if not self.settings['applet icon']: 
			self.settings['applet icon'] = 'start-here'

		if self.panel_applet.panel_type is not None:
			self.panel_applet.update_from_user_settings(self.settings)

		if self.settings['show session buttons']:
			self.get_widget('SessionPane').show()
		else:
			self.get_widget('SessionPane').hide()

		# set up open-on-hover for categories

		category_buttons = self.category_pane.get_children() + self.system_category_pane.get_children()

		if self.settings['open categories on hover']:
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


	def build_ui(self):
		"""
		Read the contents of all menus and plugins and build the UI
		elements that support them.
		"""

		# MODEL/VIEW SEPARATION EFFORT: model
		self.app_list              = []  # holds a list of all apps for searching purposes
		self.sys_list              = []  # holds a list of all apps in the system menus
		self.section_list          = {}  # holds a list of all sections to allow us to reference them by their "slab" widgets
		self.current_query         = ''
		self.subfolder_stack       = []

		# MODEL/VIEW SEPARATION EFFORT: view
		self.no_results_text             = _('No results to show')
		self.no_results_in_category_text = _('No results to show in "%(category_name)s"')
		self.plugin_loading_text         = _('Searching...')
		self.plugin_timeout_text         = _('Search timed out')

		self.read_gtk_theme_info()

		self.clear_pane(self.application_pane)
		self.clear_pane(self.category_pane)
		self.clear_pane(self.system_category_pane)
		self.clear_pane(self.sidepane)
		self.clear_pane(self.left_session_pane)
		self.clear_pane(self.right_session_pane)

		# "All" button for the regular menu
		button = self.add_button(_('All'), None, self.category_pane, tooltip = _('Show all categories'), button_type = Cardapio.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		# "All" button for the system menu
		button = self.add_button(_('All'), None, self.system_category_pane, tooltip = _('Show all categories'), button_type = Cardapio.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_system_sections_sidebar_button = button
		self.set_sidebar_button_active(button, True)
		self.all_system_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		if self.panel_applet.panel_type in (None, PANEL_TYPE_DOCKY):
			self.get_widget('AppletOptionPane').hide()

		elif self.panel_applet.panel_type is PANEL_TYPE_AWN:
			self.get_widget('LabelAppletLabel').hide()
			self.get_widget('OptionAppletLabel').hide()

		if not self.have_control_center:
			self.view_mode_button.hide()

		self.add_subfolders_slab()
		self.add_all_reorderable_slabs()

		# MODEL/VIEW SEPARATION EFFORT:
		# the methods below mix the model with the view
		self.build_places_list()
		self.build_session_list()
		self.build_system_list()
		self.build_uncategorized_list()
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')

		self.setup_ui_from_all_settings()
		self.set_message_window_visible(False)


	def rebuild_ui(self, show_message = False):
		"""
		Rebuild the UI after a timer (this is called when the menu data changes,
		for example)
		"""

		logging.info('Rebuilding UI')

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		if show_message:
			self.set_message_window_visible(True)

		self.build_ui()

		gc.collect()

		for plugin in self.active_plugin_instances:

			# trying to be too clever here, ended up causing a memory leak:
			#glib.idle_add(plugin.on_reload_permission_granted)

			# so now I'm back to doing this the regular way:
			plugin.on_reload_permission_granted
			# (leak solved!)

		self.schedule_search_with_all_plugins('')


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

		if gnome_execute_terminal_shell is None:
			self.get_widget('ExecutableDialogRunInTerminal').hide()

		self.executable_file_dialog.set_focus(self.get_widget('ExecutableDialogCancel'))

		response = self.executable_file_dialog.run()
		self.executable_file_dialog.hide()

		return response


	def open_about_gnome_dialog(self, widget):
		"""
		Opens the "About Gnome" dialog.
		"""

		self.open_about_dialog(widget, 'AboutGnome')


	def open_about_distro_dialog(self, widget):
		"""
		Opens the "About %distro%" dialog
		"""

		self.open_about_dialog(widget, 'AboutDistro')


	def open_about_dialog(self, widget, verb = None):
		"""
		Opens either the "About Gnome" dialog, or the "About Ubuntu" dialog,
		or the "About Cardapio" dialog
		"""

		if verb == 'AboutGnome':
			self.launch_raw('gnome-about')

		elif verb == 'AboutDistro':
			self.launch_raw('yelp ghelp:about-%s' % Cardapio.distro_name.lower())
			# i'm assuming this is the pattern for all distros...

		else: self.about_dialog.show()


	def on_dialog_close(self, dialog, response = None):
		"""
		Handler for when a dialog's X button is clicked
		"""

		dialog.hide()
		return True


	def set_widget_from_option(self, widget_str, option_str):
		"""
		Set the value of the widget named 'widget_str' to 'option_str'
		"""

		widget = self.get_widget(widget_str)
		try    : widget.handler_block_by_func(self.on_options_changed)
		except : pass

		if type(widget) is gtk.Entry:
			widget.set_text(self.settings[option_str])

		elif type(widget) is gtk.CheckButton:
			widget.set_active(self.settings[option_str])

		else:
			logging.error('Widget %s (%s) was not written' % (widget_str, type(widget)))

		try    : widget.handler_unblock_by_func(self.on_options_changed)
		except : pass


	def open_options_dialog(self, *dummy):
		"""
		Show the Options Dialog and populate its widgets with values from the
		user's settings (self.settings).
		"""

		self.set_widget_from_option('OptionKeybinding', 'keybinding')
		self.set_widget_from_option('OptionAppletLabel', 'applet label')
		self.set_widget_from_option('OptionAppletIcon', 'applet icon')
		self.set_widget_from_option('OptionSessionButtons', 'show session buttons')
		self.set_widget_from_option('OptionKeepResults', 'keep search results')
		self.set_widget_from_option('OptionOpenOnHover', 'open on hover')
		self.set_widget_from_option('OptionOpenCategoriesOnHover', 'open categories on hover')
		self.set_widget_from_option('OptionMiniMode', 'mini mode') # using a different handler

		icon_size = gtk.icon_size_lookup(4)[0] # 4 because it's that same as in the UI file

		self.plugin_tree_model.clear()

		# place active plugins at the top of the list, in order

		plugin_list = []
		plugin_list += [basename for basename in self.settings['active plugins']]

		inactive_plugins = [basename for basename in self.plugin_database if basename not in plugin_list]
		plugin_list += sorted(inactive_plugins) # TODO: sort by regular name instead of basename

		for basename in plugin_list:

			plugin_info = self.plugin_database[basename]
			name = plugin_info['name']

			is_active   = (basename in self.settings['active plugins'])
			is_core     = (basename in self.core_plugins)
			is_required = (basename in self.required_plugins)

			if is_required : title = '<b>%s</b>' % name

			icon_pixbuf = self.icon_helper.get_icon_pixbuf(plugin_info['category icon'], icon_size, 'package-x-generic')

			self.plugin_tree_model.append([basename, name, name, is_active, is_core, not is_required, icon_pixbuf])

		self.update_plugin_description()
		self.options_dialog.show()


	def on_options_dialog_closed(self, *dummy):
		"""
		Hides the Options Dialog
		"""

		self.options_dialog.hide()
		try:
			self.settings.save()
		except Exception, ex:
			logging.error('error while saving settings: %s' % ex)

		return True


	def on_options_changed(self, *dummy):
		"""
		Updates Cardapio's options when the user alters them in the Options
		Dialog
		"""

		self.settings['keybinding'] = self.get_widget('OptionKeybinding').get_text()
		self.settings['applet label'] = self.get_widget('OptionAppletLabel').get_text()
		self.settings['applet icon'] = self.get_widget('OptionAppletIcon').get_text()
		self.settings['show session buttons'] = self.get_widget('OptionSessionButtons').get_active()
		self.settings['keep search results'] = self.get_widget('OptionKeepResults').get_active()
		self.settings['open on hover'] = self.get_widget('OptionOpenOnHover').get_active()
		self.settings['open categories on hover'] = self.get_widget('OptionOpenCategoriesOnHover').get_active()
		self.settings['mini mode'] = self.get_widget('OptionMiniMode').get_active()
		self.setup_ui_from_gui_settings()


	def on_grab_new_shortcut_toggled(self, button):
		"""
		Starts/stops listening for new keybindings
		"""

		if button.get_active():

			if self.keybinding is not None:
				try: keybinder.unbind(self.keybinding)
				except: pass

			self.key_grab_handler = self.options_dialog.connect('key-press-event', self.on_new_keybinding_press)
			self.get_widget('OptionGrabKeybinding').set_label(_('Recording...'))

		else:

			self.options_dialog.disconnect(self.key_grab_handler)
			self.get_widget('OptionGrabKeybinding').set_label(_('Grab new shortcut'))
			self.on_options_changed()


	def on_new_keybinding_press(self, widget, event):
		"""
		Handler for then the options window is listening for a new keybinding.

		Behavior:
		- All keys combos are valid, except pure "Esc" (which cancels the
		  operation), and pure "Del" or pure "Backspace" (both of which clear
		  keybinding).
		- When the user presses a non-special key (such as "space" or "a"), we
		  stop listening and save the combo.
		- If a non-standard key combo is desired (such as pure "Super_L"), the
		  user must untoggle the keybinding options button with the mouse.
		"""

		main_key = event.keyval
		main_key_string = gtk.gdk.keyval_name(main_key)

		modifier_key = event.state
		modifier_string = u''

		if modifier_key & gtk.gdk.SHIFT_MASK   : modifier_string += '<shift>'
		if modifier_key & gtk.gdk.CONTROL_MASK : modifier_string += '<control>'
		if modifier_key & gtk.gdk.SUPER_MASK   : modifier_string += '<super>'
		if modifier_key & gtk.gdk.HYPER_MASK   : modifier_string += '<hyper>'
		if modifier_key & gtk.gdk.META_MASK    : modifier_string += '<meta>'
		if modifier_key & gtk.gdk.MOD1_MASK    : modifier_string += '<alt>'

		# TODO: Are these needed? How to resolve the case where Super = Mod4, causing
		# both keys to be detected at the same time?
		# TODO: Why is MOD2 always ON no matter what?! (on one of my computers)
		#if modifier_key & gtk.gdk.MOD2_MASK    : modifier_string += '<mod2>'
		#if modifier_key & gtk.gdk.MOD3_MASK    : modifier_string += '<mod3>'
		#if modifier_key & gtk.gdk.MOD4_MASK    : modifier_string += '<mod4>'
		#if modifier_key & gtk.gdk.MOD5_MASK    : modifier_string += '<mod5>'

		shortcut_string = modifier_string + main_key_string

		# cancel on "Escape"
		if main_key == gtk.keysyms.Escape and not modifier_string:
			self.get_widget('OptionKeybinding').set_text(self.settings['keybinding'])
			self.get_widget('OptionGrabKeybinding').set_active(False)
			return True

		# clear on "BackSpace" or "Delete"
		if main_key in (gtk.keysyms.BackSpace, gtk.keysyms.Delete) and not modifier_string:
			self.get_widget('OptionKeybinding').set_text('')
			self.get_widget('OptionGrabKeybinding').set_active(False)
			return True

		if main_key_string:
			self.get_widget('OptionKeybinding').set_text(shortcut_string)

			if main_key not in (
					gtk.keysyms.Shift_L, gtk.keysyms.Shift_R, gtk.keysyms.Shift_Lock,
					gtk.keysyms.Control_L, gtk.keysyms.Control_R,
					gtk.keysyms.Super_L, gtk.keysyms.Super_R,
					gtk.keysyms.Hyper_L, gtk.keysyms.Hyper_R,
					gtk.keysyms.Meta_L, gtk.keysyms.Meta_R,
					gtk.keysyms.Alt_L, gtk.keysyms.Alt_R, gtk.keysyms.Mode_switch,
					# TODO: what else?
					#gtk.keysyms.ISO_Level3_Shift, gtk.keysyms.ISO_Group_Shift, 
					):
				self.get_widget('OptionGrabKeybinding').set_active(False)

		return True


	def update_plugin_description(self, *dummy):
		"""
		Writes information about the currently-selected plugin on the GUI
		"""

		model, iter_ = self.get_widget('PluginTreeView').get_selection().get_selected()

		if iter_ is None:
			is_core = True
			plugin_info = {'name': '', 'version': '', 'author': '', 'description': ''}

		else:
			is_core  = self.plugin_tree_model.get_value(iter_, 4)
			basename = self.plugin_tree_model.get_value(iter_, 0)
			plugin_info = self.plugin_database[basename]

		description = _('<b>Plugin:</b> %(name)s %(version)s\n<b>Author:</b> %(author)s\n<b>Description:</b> %(description)s') % plugin_info
		if not is_core  : description += '\n<small>(' + _('This is a community-supported plugin') + ')</small>'

		label = self.get_widget('OptionPluginInfo')
		dummy, dummy, width, dummy = label.get_allocation()
		label.set_markup(description)
		label.set_line_wrap(True)

		# make sure the label doesn't resize the window!
		if width > 1:
			label.set_size_request(width - self.scrollbar_width - 20, -1)

		# The -20 is a hack because some themes add extra padding that I need to
		# account for. Since I don't know where that padding is comming from, I
		# just enter a value (20px) that is larger than I assume any theme would
		# ever use.


	def apply_plugins_from_option_window(self, *dummy):
		"""
		Handler for when the user clicks on "Apply" in the plugin tab of the
		Options Dialog
		"""

		self.settings['active plugins'] = []
		iter_ = self.plugin_tree_model.get_iter_first()

		while iter_ is not None:

			if self.plugin_tree_model.get_value(iter_, 3):
				self.settings['active plugins'].append(self.plugin_tree_model.get_value(iter_, 0))

			iter_ = self.plugin_tree_model.iter_next(iter_)

		self.options_dialog.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))

		# ensure cursor is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()

		self.activate_plugins_from_settings() # investigate memory usage here
		self.options_dialog.window.set_cursor(None)

		self.schedule_rebuild()


	def on_plugintreeview_hover(self, treeview, event):
		"""
		Change the cursor to show that plugins are draggable.
		"""

		pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))

		if pthinfo is None:
			treeview.window.set_cursor(None)
			return

		path, col, cellx, celly = pthinfo

		if col == self.plugin_checkbox_column:
			treeview.window.set_cursor(None)
		else:
			treeview.window.set_cursor(self.drag_allowed_cursor)


	def on_plugin_state_toggled(self, cell, path):
		"""
		Believe it or not, GTK requires you to manually tell the checkbuttons
		that reside within a tree to toggle when the user clicks on them.
		This function does that.
		"""

		iter_ = self.plugin_tree_model.get_iter(path)
		basename = self.plugin_tree_model.get_value(iter_, 0)

		if basename in self.required_plugins: return

		self.plugin_tree_model.set_value(iter_, 3, not cell.get_active())
		self.apply_plugins_from_option_window()


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
			self.block_focus_out_event()
			glib.timeout_add(Cardapio.FOCUS_BLOCK_INTERVAL, self.unblock_focus_out_event)


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

		self.save_dimensions()
		self.unblock_focus_out_event()


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


	def on_mainwindow_after_key_pressed(self, widget, event):
		"""
		Send all keypresses to the search entry, so the user can search
		from anywhere without the need to focus the search entry first
		"""

		w = self.window.get_focus()

		if w != self.search_entry and w == self.previously_focused_widget:
			if event.is_modifier:
				return

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


	def on_mainwindow_focus_out(self, widget, event):
		"""
		Make Cardapio disappear when it loses focus
		"""

		self.save_dimensions()

		# Make sure clicking the applet button doesn't cause a focus-out event.
		# Otherwise, the click signal actually happens *after* the focus-out,
		# which causes the applet to be re-shown rather than disappearing.
		# So by ignoring this focus-out we actually make sure that Cardapio
		# will be hidden after all. Silly.
		root_window = gtk.gdk.get_default_root_window()
		mouse_x, mouse_y, dummy = root_window.get_pointer()
		if self.panel_applet.has_mouse_cursor(mouse_x, mouse_y): return

		# If the last app was opened in the background, make sure Cardapio
		# doesn't hide when the app gets focused

		if self.opened_last_app_in_background:

			self.opened_last_app_in_background = False
			self.show_window_on_top(self.window)
			return

		self.hide()


	def on_mainwindow_cursor_leave(self, widget, event):
		"""
		Handler for when the cursor leaves the Cardapio window.
		If using 'open on hover', this hides the Cardapio window after a delay.
		"""

		if self.panel_applet.panel_type is None: return

		if self.settings['open on hover'] and not self.focus_out_blocked:
			glib.timeout_add(self.settings['autohide delay'], self.hide_if_mouse_away)


	def on_mainwindow_delete_event(self, widget, event):
		"""
		What happens when the user presses Alt-F4? If in panel mode,
		nothing. If in launcher mode, this terminates Cardapio.
		"""

		if self.panel_applet.panel_type is not None:
			# keep window alive if in panel mode
			return True

		self.save_and_quit()


	def on_gtk_settings_changed(self, gobj, property_changed):
		"""
		Rebuild the Cardapio UI whenever the color scheme or gtk theme change
		"""

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self.read_gtk_theme_info()
			self.schedule_rebuild()


	def on_menu_data_changed(self, tree):
		"""
		Rebuild the Cardapio UI whenever the menu data changes
		"""

		self.schedule_rebuild()


	def schedule_rebuild(self):
		"""
		Rebuilds the Cardapio UI after a timer
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.rebuild_ui)


	def on_view_mode_toggled(self, widget):
		"""
		Handler for when the "system menu" button is toggled
		"""

		if self.auto_toggled_view_mode_button:
			self.auto_toggled_view_mode_button = False
			return True

		self.switch_modes(show_system_menus = widget.get_active())


	def switch_modes(self, show_system_menus, toggle_mode_button = False):
		"""
		Switched between "all menus" and "system menus" mode
		"""

		self.in_system_menu_mode = show_system_menus

		if toggle_mode_button:
			if self.view_mode_button.get_active() != show_system_menus:
				self.auto_toggled_view_mode_button = True
				self.view_mode_button.set_active(show_system_menus)

		self.untoggle_and_show_all_sections()
		self.on_search_entry_changed()

		if show_system_menus:
			self.category_pane.hide()
			self.system_category_pane.show()

		else:
			self.system_category_pane.hide()
			self.category_pane.show()


	def on_search_entry_icon_pressed(self, widget, iconpos, event):
		"""
		Handler for when the "clear" icon of the search entry is pressed
		"""

		if self.is_search_entry_empty():
			self.untoggle_and_show_all_sections()

		else:
			self.clear_search_entry()


	def on_search_entry_changed(self, *dummy):
		"""
		Handler for when the user types something in the search entry
		"""

		# MODEL/VIEW SEPARATION EFFORT: everything in here should be
		# model/controller stuff. View stuff should go on separate, well-defined
		# calls that are made from here.

		text = self.search_entry.get_text().strip()

		if text and text == self.current_query: return
		self.current_query = text

		self.no_results_to_show = True
		self.hide_no_results_text()

		handled = False
		in_subfolder_search_mode = (text and text.find('/') != -1)

		if not in_subfolder_search_mode:
			self.subfolder_stack = []
			# clean up the UI for every mode except subfolder_search, since it
			# needs to know the topmost result:
			self.fully_hide_all_sections()

		# if showing the control center menu
		if self.in_system_menu_mode:
			self.search_menus(text, self.sys_list)
			handled = True

		# if doing a keyword search
		elif text and text[0] == '?':
			keyword, dummy, text = text.partition(' ')
			self.current_query = text

			if len(keyword) >= 1 and text:
				self.search_with_plugin_keyword(keyword[1:], text)

			self.consider_showing_no_results_text()
			handled = True

		# if doing a subfolder search
		elif in_subfolder_search_mode:
			first_app_widget = self.get_first_visible_app()
			selected_app_widget = self.get_selected_app()
			self.fully_hide_all_sections()
			self.previously_focused_widget = None
			handled = self.search_subfolders(text, first_app_widget, selected_app_widget)

		# if none of these (or if the subfolder search tells you this is not a
		# proper subfolder), then just run a regular search. This includes the
		# regular menus, the system menus, and all active plugins
		if not handled:
			# search all menus (apps, places and system)
			self.search_menus(text, self.app_list)

			# search with all plugins
			self.schedule_search_with_all_plugins(text)

			# NOTE: To fix a bug where plugins with hide_from_sidebar=False were
			# not being placed on the sidebar, I replaced the block below for
			# the line above. I'm just wondering if there are any unforeseen
			# side effects, though. So I'm leaving the block below in the code
			# for a few versions as a reminder. If nothing pops up, we can just
			# remove it.

			## if query is large enough
			#if len(text) >= self.settings['min search string length']:
			#
			#	# search with all plugins
			#	self.schedule_search_with_all_plugins(text)
			#
			#else:
			#	# clean up plugin results
			#	self.fully_hide_plugin_sections()

		if len(text) == 0:
			self.hide_all_transitory_sections(fully_hide = True)

		else:
			self.all_sections_sidebar_button.set_sensitive(True)
			self.all_system_sections_sidebar_button.set_sensitive(True)

		self.consider_showing_no_results_text()


	def search_menus(self, text, app_list):
		"""
		Start a menu search
		"""

		text = text.lower()

		self.application_pane.hide() # for speed

		for app in app_list:

			if app['name'].find(text) == -1 and app['basename'].find(text) == -1:
				app['button'].hide()
			else:
				app['button'].show()
				self.set_section_has_entries(app['section'])
				self.no_results_to_show = False

		if self.selected_section is None:
			self.untoggle_and_show_all_sections()

		self.application_pane.show() # restore application_pane


	def create_subfolder_stack(self, path):
		"""
		Fills in the subfolder_stack array with all ancestors of a given path
		"""

		path = '/' + path.strip('/')
		self.subfolder_stack = [('', '/')]

		i = 0
		while True:
			i = path.find('/', i+1)
			if i == -1: break
			partial_path = path[:i]
			self.subfolder_stack.append((partial_path, partial_path))

		self.subfolder_stack.append((path, path))


	def search_subfolders(self, text, first_app_widget, selected_app_widget):
		"""
		Lets you browse your filesystem through Cardapio by typing slash "/" after
		a search query to "push into" a folder. 
		"""

		search_inside = (text[-1] == '/')
		slash_pos     = text.rfind('/')
		base_text     = text[slash_pos+1:]
		path          = None

		self.subfolders_section_slab.hide() # for added performance
		self.clear_pane(self.subfolders_section_contents)

		if not search_inside:
			if not self.subfolder_stack: return False
			slash_count = text.count('/')
			path = self.subfolder_stack[slash_count - 1][1]
			self.subfolder_stack = self.subfolder_stack[:slash_count]

		else:
			text = text[:-1]
			curr_level = text.count('/')

			if self.subfolder_stack:
				prev_level = self.subfolder_stack[-1][0].count('/')
			else: 
				prev_level = -1

			# if typed root folder
			if text == '': 
				path        = '/'
				base_text   = ''
				self.subfolder_stack = [(text, path)]

			# if pushing into a folder
			elif prev_level < curr_level:

				if first_app_widget is not None:
					if selected_app_widget is not None: widget = selected_app_widget
					else: widget = first_app_widget

					if widget.app_info['type'] != 'xdg': return False
					path = self.escape_quotes(self.unescape_url(widget.app_info['command']))

					path_type, path = urllib2.splittype(path)
					if path_type and path_type != 'file': return False
					if not os.path.isdir(path): return False
					self.subfolder_stack.append((text, path))

			# if popping out of a folder
			else:
				if prev_level > curr_level: self.subfolder_stack.pop()
				path = self.subfolder_stack[-1][1]

		if path is None: return False

		if path == '/': parent_name = _('Filesystem Root')
		else: parent_name = os.path.basename(path)
		self.subfolders_label.set_text(parent_name)

		count = 0
		limit = self.settings['long search results limit']
		base_text = base_text.lower()
		
		if base_text:
			matches = [f for f in os.listdir(path) if f.lower().find(base_text) != -1]
		else:
			matches = os.listdir(path)

		for filename in sorted(matches, key = str.lower):

			# ignore hidden files
			if filename[0] == '.': continue

			if count >= limit: 
				self.add_app_button(_('Show additional results'), 'system-file-manager', self.subfolders_section_contents, 'xdg', path, tooltip = _('Show additional search results in a file browser'), app_list = None)
				break

			count += 1

			command = os.path.join(path, filename)
			icon_name = self.icon_helper.get_icon_name_from_path(command)
			if icon_name is None: icon_name = 'folder'

			basename, dummy = os.path.splitext(filename)
			self.add_app_button(filename, icon_name, self.subfolders_section_contents, 'xdg', command, tooltip = command, app_list = None)

		if count:
			self.subfolders_section_slab.show()
			self.set_section_has_entries(self.subfolders_section_slab)
			self.no_results_to_show = False

		else:
			self.no_results_to_show = True

		return True


	def cancel_all_plugin_timers(self):
		"""
		Cancels both the "search start"-type timers and the "search timeout"-type ones
		"""

		if self.search_timer_local is not None:
			glib.source_remove(self.search_timer_local)

		if self.search_timer_remote is not None:
			glib.source_remove(self.search_timer_remote)

		if self.search_timeout_local is not None:
			glib.source_remove(self.search_timeout_local)

		if self.search_timeout_remote is not None:
			glib.source_remove(self.search_timeout_remote)


	def search_with_plugin_keyword(self, keyword, text):
		"""
		Search using the plugin that matches the given keyword
		"""

		if not keyword: return

		keyword_exists = False

		# search for a registered keyword that has this keyword as a substring
		for plugin_keyword in self.keyword_to_plugin_mapping:
			if plugin_keyword.find(keyword) == 0:
				keyword_exists = True
				keyword = plugin_keyword
				break

		if not keyword_exists: return

		plugin = self.keyword_to_plugin_mapping[keyword]

		self.cancel_all_plugins()
		self.cancel_all_plugin_timers()

		self.schedule_search_with_specific_plugin(text, plugin.search_delay_type, plugin)


	def schedule_search_with_all_plugins(self, text):
		"""
		Cleans up plugins and timers, and creates new timers to search with all
		plugins
		"""

		self.cancel_all_plugins()
		self.cancel_all_plugin_timers()

		self.schedule_search_with_specific_plugin(text, None)
		self.schedule_search_with_specific_plugin(text, 'local')
		self.schedule_search_with_specific_plugin(text, 'remote')


	def schedule_search_with_specific_plugin(self, text, delay_type = None, specific_plugin = None):
		"""
		Sets up timers to start searching with the plugins specified by the
		delay_type and possibly by "specific_plugin"
		"""

		if delay_type is None:
			self.search_with_specific_plugin(text, None, specific_plugin)

		elif delay_type == 'local':
			timer_delay = self.settings['local search update delay']
			timeout     = self.settings['local search timeout']
			self.search_timer_local   = glib.timeout_add(timer_delay, self.search_with_specific_plugin, text, delay_type, specific_plugin)
			self.search_timeout_local = glib.timeout_add(timeout, self.show_all_plugin_timeout_text, delay_type)
		
		else:
			timer_delay = self.settings['remote search update delay']
			timeout     = self.settings['remote search timeout']
			self.search_timer_remote   = glib.timeout_add(timer_delay, self.search_with_specific_plugin, text, delay_type, specific_plugin)
			self.search_timeout_remote = glib.timeout_add(timeout, self.show_all_plugin_timeout_text, delay_type)


	def search_with_specific_plugin(self, text, delay_type, specific_plugin = None):
		"""
		Start a plugin-based search
		"""

		if delay_type == 'local':
			if self.search_timer_local is not None:
				glib.source_remove(self.search_timer_local)
				self.search_timer_local = None

		elif delay_type == 'remote':
			if self.search_timer_remote is not None:
				glib.source_remove(self.search_timer_remote)
				self.search_timer_remote = None

		if specific_plugin is not None:

			plugin = specific_plugin
			plugin.__is_running = True

			try:
				self.show_plugin_loading_text(plugin)
				plugin.search(text, self.settings['long search results limit'])

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

			return False # Required!

		query_is_too_short = (len(text) < self.settings['min search string length'])
		number_of_results = self.settings['search results limit']

		for plugin in self.active_plugin_instances:

			if plugin.search_delay_type != delay_type or plugin.__show_only_with_keyword:
				continue

			if plugin.hide_from_sidebar and query_is_too_short:
				continue

			plugin.__is_running = True

			try:
				self.show_plugin_loading_text(plugin)
				plugin.search(text, number_of_results)

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def reset_plugin_section_contents(self, plugin):
		"""
		Clear the contents of a plugin's slab, usually to fill it with results later
		"""

		container = plugin.section_contents.parent

		# if plugin was deactivated while waiting for search result
		if container is None: return False

		container.remove(plugin.section_contents)
		plugin.section_contents = gtk.VBox()
		container.add(plugin.section_contents)

		return True


	def show_plugin_loading_text(self, plugin):
		"""
		Write "Searching..." under the plugin slab title
		"""

		self.reset_plugin_section_contents(plugin)
		label = gtk.Label(self.plugin_loading_text)
		label.set_alignment(0, 0.5)
		label.set_sensitive(False)
		label.show()

		plugin.section_contents.pack_start(label, expand = False, fill = False)
		plugin.section_contents.show()

		if self.selected_section is None or plugin.section_slab == self.selected_section:
			plugin.section_slab.show()
			self.hide_no_results_text()

		self.plugins_still_searching += 1


	def show_all_plugin_timeout_text(self, delay_type):
		"""
		Write "Plugin timed out..." under the plugin slab title
		"""

		for plugin in self.active_plugin_instances:

			if not plugin.__is_running: continue
			if plugin.search_delay_type != delay_type: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)

			self.reset_plugin_section_contents(plugin)
			label = gtk.Label(self.plugin_timeout_text)
			label.set_alignment(0, 0.5)
			label.set_sensitive(False)
			label.show()

			plugin.section_contents.pack_start(label, expand = False, fill = False)
			plugin.section_contents.show()
			plugin.section_slab.show()

			self.plugins_still_searching -= 1

		self.consider_showing_no_results_text()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def plugin_handle_search_error(self, plugin, text):
		"""
		Handler for when a plugin returns an error
		"""

		plugin.__is_running = False
		self.plugin_write_to_log(plugin, text, is_error = True)

		# must be outside the lock!
		self.plugin_handle_search_result(plugin, [], '')


	def plugin_handle_search_result(self, plugin, results, original_query):
		"""
		Handler for when a plugin returns some search results
		"""

		plugin.section_slab.hide() # for added performance

		plugin.__is_running = False
		self.plugins_still_searching -= 1

		query_is_too_short = (len(self.current_query) < self.settings['min search string length'])

		if plugin.hide_from_sidebar and query_is_too_short:

			# Handle the case where user presses backspace *very* quickly, and the
			# search starts when len(text) > min_search_string_length, but after
			# search_update_delay milliseconds this method is called while the
			# search entry now has len(text) < min_search_string_length

			# Anyways, it's hard to explain, but suffice to say it's a race
			# condition and we handle it here.

			results = []

		if original_query != self.current_query:
			results = []

		gtk.gdk.threads_enter()

		self.reset_plugin_section_contents(plugin)

		for result in results:

			icon_name = result['icon name']
			fallback_icon = plugin.fallback_icon or 'text-x-generic'

			if icon_name == 'inode/symlink':
				icon_name = None

			if icon_name is not None:
				icon_name = self.icon_helper.get_icon_name_from_theme(icon_name)

			elif result['type'] == 'xdg':
				icon_name = self.icon_helper.get_icon_name_from_path(result['command'])

			if icon_name is None:
				icon_name = fallback_icon

			button = self.add_app_button(result['name'], icon_name, plugin.section_contents, result['type'], result['command'], tooltip = result['tooltip'])
			button.app_info['context menu'] = result['context menu']


		if results:

			self.no_results_to_show = False

			plugin.section_contents.show()
			self.set_section_has_entries(plugin.section_slab)

			if (self.selected_section is None) or (self.selected_section == plugin.section_slab):
				plugin.section_slab.show()
				self.hide_no_results_text()

			else:
				self.consider_showing_no_results_text()

		else:

			self.set_section_is_empty(plugin.section_slab)

			if (self.selected_section is None) or (self.selected_section == plugin.section_slab):
				plugin.section_slab.hide()

			self.consider_showing_no_results_text()

		gtk.gdk.threads_leave()


	def plugin_ask_for_reload_permission(self, plugin):
		"""
		Handler for when a plugin asks Cardapio whether it can reload its
		database
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.plugin_on_reload_permission_granted, plugin)


	def plugin_on_reload_permission_granted(self, plugin):
		"""
		Tell the plugin that it may rebuild its database now
		"""

		self.rebuild_timer = None
		plugin.on_reload_permission_granted()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def cancel_all_plugins(self):
		"""
		Tell all plugins to stop a possibly-time-consuming search
		"""

		self.plugins_still_searching = 0

		for plugin in self.active_plugin_instances:

			if not plugin.__is_running: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)


	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_search_entry_activate(self, widget):
		"""
		Handler for when the user presses Enter on the search entry
		"""

		if self.is_search_entry_empty():
			self.hide_all_transitory_sections() # TODO: should fully_hide be True?
			return

		first_app_widget = self.get_first_visible_app()
		if first_app_widget is not None:
			first_app_widget.emit('clicked')

		if not self.settings['keep search results']:
			self.clear_search_entry()
			self.untoggle_and_show_all_sections()


	def on_search_entry_key_pressed(self, widget, event):
		"""
		Handler for when the user presses Tab or Escape on the search entry
		"""

		# make Tab go to first result element
		if event.keyval == gtk.gdk.keyval_from_name('Tab'):

			if self.selected_section is not None:

				contents = self.section_list[self.selected_section]['contents']
				visible_children = [c for c in contents.get_children() if c.get_property('visible')]

				if visible_children:
					self.window.set_focus(visible_children[0])

			else:
				first_app_widget = self.get_first_visible_app()
				if first_app_widget is not None:
					self.window.set_focus(first_app_widget)


		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):

			self.cancel_all_plugins()

			text = self.search_entry.get_text()
			slash_pos = text.rfind('/')

			if self.subfolder_stack and slash_pos != -1:
				if text[-1] == '/': slash_pos = text[:-1].rfind('/')
				text = text[:slash_pos+1]
				self.search_entry.set_text(text)
				self.search_entry.set_position(-1)

			elif not self.is_search_entry_empty():
				self.clear_search_entry()

			elif self.selected_section is not None:
				self.untoggle_and_show_all_sections()

			elif self.in_system_menu_mode:
				self.switch_modes(show_system_menus = False, toggle_mode_button = True)

			else:
				self.hide()

		else: return False
		return True


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


	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""

		widget = self.previously_focused_widget

		if (type(widget) is gtk.Button and 'app_info' in dir(widget)):
			return widget

		return None


	def choose_coordinates_for_window(self, window):
		"""
		Returns the appropriate coordinates for the given window. The
		coordinates are determined according to the following algorithm:

		- If there's no Cardapio applet, place the window in the center of the
		  screen

		- Otherwise, position the window near the applet (just below it if the
		  panel is top opriented, just to the left of it if the panel is right
		  oriented, and so on)

		"""

		window_width, window_height = window.get_size()
		screen_x, screen_y, screen_width, screen_height = self.get_screen_dimensions()

		if self.panel_applet.panel_type != None:
			orientation = self.panel_applet.get_orientation()
			x, y = self.panel_applet.get_position()
			w, h = self.panel_applet.get_size()
			if orientation == POS_LEFT: x += w
			if orientation == POS_TOP : y += h

		else:
			x = (screen_width - window_width)/2
			y = (screen_height - window_height)/2

		return x, y


	def get_coordinates_inside_screen(self, window, x, y, force_anchor_right = False, force_anchor_bottom = False):
		"""
		If the window won't fit on the usable screen, given its size and
		proposed coordinates, the method will rotate it over its x, y, or x=y
		axis. Als , the window won't hide beyond the top and left borders of the
		usable screen.

		Returns the new x, y coordinates and two booleans indicating whether the
		window was rotated around the x and/or y axis.
		"""

		window_width, window_height = window.get_size()
		screen_x, screen_y, screen_width, screen_height = self.get_screen_dimensions()

		# maximal coordinates of window and usable screen
		max_window_x, max_window_y = x + window_width, y + window_height
		max_screen_x, max_screen_y = screen_x + screen_width, screen_y + screen_height

		anchor_right  = False
		anchor_bottom = False

		orientation = self.panel_applet.get_orientation()
		w, h = self.panel_applet.get_size()

		# if the window won't fit horizontally, flip it over its y axis
		if max_window_x > max_screen_x: 
			anchor_right = True
			if orientation == POS_TOP or orientation == POS_BOTTOM: x += w 

		# if the window won't fit horizontally, flip it over its x axis
		if max_window_y > max_screen_y: 
			anchor_bottom = True
			if orientation == POS_LEFT or orientation == POS_RIGHT: y += h

		if force_anchor_right : anchor_right  = True
		if force_anchor_bottom: anchor_bottom = True

		# just to be sure: never hide behind top and left borders of the usable
		# screen!
		if x < screen_x: x = screen_x
		if y < screen_y: y = screen_y

		if anchor_right and x - window_width < screen_x: 
			x = screen_x + screen_width

		if anchor_bottom and y - window_height < screen_y: 
			y = screen_y + screen_height

		return x, y, anchor_right, anchor_bottom


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


	def restore_dimensions(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Resize Cardapio according to the user preferences
		"""

		if self.settings['window size'] is not None:
			self.window.resize(*self.settings['window size'])

		if x is None or y is None:
			x, y = self.choose_coordinates_for_window(self.window)

		x, y, anchor_right, anchor_bottom = self.get_coordinates_inside_screen(self.window, x, y, force_anchor_right, force_anchor_bottom)

		if anchor_right:
			if anchor_bottom: self.window.set_gravity(gtk.gdk.GRAVITY_SOUTH_EAST)
			else: self.window.set_gravity(gtk.gdk.GRAVITY_NORTH_EAST)

		else:
			if anchor_bottom: self.window.set_gravity(gtk.gdk.GRAVITY_SOUTH_WEST)
			else: self.window.set_gravity(gtk.gdk.GRAVITY_NORTH_WEST)

		if gtk.ver[0] == 2 and gtk.ver[1] <= 21 and gtk.ver[2] < 5:
			gtk_window_move_with_gravity(self.window, x, y)
		else:
			self.window.move(x, y)

		if self.settings['mini mode']:
			self.main_splitter.set_position(0)

		elif self.settings['splitter position'] > 0:
			self.main_splitter.set_position(self.settings['splitter position'])

		# decide which search bar to show (top or bottom) depending
		# on the y = 0 axis window invert
		self.setup_search_entry(place_at_top = not anchor_bottom)


	def save_dimensions(self, *dummy):
		"""
		Save Cardapio's size into the user preferences
		"""

		self.settings['window size'] = list(self.window.get_size())
		if not self.settings['mini mode']:
			self.settings['splitter position'] = self.main_splitter.get_position()


	def on_main_splitter_clicked(self, widget, event):
		"""
		Make sure user can't move the splitter when in mini mode
		"""

		# TODO: collapse to mini mode when main_splitter is clicked (but not dragged)
		#if event.type == gtk.gdk.BUTTON_PRESS:

		if event.button == 1:
			if self.settings['mini mode']:
				# block any other type of clicking when in mini mode
				return True

	
	def on_mini_mode_button_toggled(self, widget):
		"""
		Handler for the minimode checkbox in the preferences window
		"""

		self.settings['mini mode'] = self.get_widget('OptionMiniMode').get_active()
		self.toggle_mini_mode_ui(update_window_size = True)
		return True


	def toggle_mini_mode_ui(self, update_window_size):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""

		category_buttons = self.category_pane.get_children() +\
				self.system_category_pane.get_children() + self.sidepane.get_children()

		if self.settings['mini mode']:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].hide()

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
			#self.main_splitter.set_position(0)

			# hack to make sure the viewport resizes to the minisize correctly
			self.get_widget('SideappViewport').hide()
			self.get_widget('SideappViewport').show()

			if update_window_size:
				self.settings['window size'][0] -= self.main_splitter.get_position()

		else:

			for category_button in category_buttons:
				category_button.child.child.get_children()[1].show()

			self.get_widget('ViewLabel').set_size_request(-1, -1)
			self.get_widget('ViewLabel').show()
			self.get_widget('ControlCenterLabel').show()
			self.get_widget('ControlCenterArrow').show()
			self.get_widget('CategoryScrolledWindow').set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

			self.get_widget('CategoryMargin').set_padding(*self.fullsize_mode_padding)
			
			self.main_splitter.set_position(self.settings['splitter position'])

			if update_window_size:
				self.settings['window size'][0] += self.main_splitter.get_position()


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


	@dbus.service.method(dbus_interface = bus_name_str, in_signature = None, out_signature = None)
	def show_hide(self):
		"""
		Toggles Cardapio's visibility and places the window near the applet or,
		if there is no applet, centered on the screen.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		return self.show_hide_near_point()


	@dbus.service.method(dbus_interface = bus_name_str, in_signature = None, out_signature = None)
	def show_hide_near_mouse(self):
		"""
		Toggles Cardapio's visibility and places the window near the mouse.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		mouse_x, mouse_y, dummy = gtk.gdk.get_default_root_window().get_pointer()
		return self.show_hide_near_point(mouse_x, mouse_y)


	@dbus.service.method(dbus_interface = bus_name_str, in_signature = 'iibb', out_signature = None)
	def show_hide_near_point(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Toggles Cardapio's visibility and places the window at the given (x,y)
		location -- or as close as possible so that the window still fits on the
		screen.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		if time() - self.last_visibility_toggle < Cardapio.MIN_VISIBILITY_TOGGLE_INTERVAL:
			return

		if self.visible: 
			self.hide()
		else: 
			if x is not None: x = int(x)
			if y is not None: y = int(y)
			if x < 0: x = None
			if y < 0: y = None
			self.show(x, y, force_anchor_right, force_anchor_bottom)

		return True
	

	def show(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Shows the Cardapio window.

		If arguments x and y are given, the window will be positioned somewhere
		near that point.  Otherwise, the window will be positioned near applet
		or in the center of the screen (if there's no applet).
		"""

		self.panel_applet.draw_toggled_state(True)

		self.restore_dimensions(x, y, force_anchor_right = False, force_anchor_bottom = False)

		self.window.set_focus(self.search_entry)
		self.show_window_on_top(self.window)

 		self.scroll_to_top()

		self.visible = True
		self.last_visibility_toggle = time()

		self.opened_last_app_in_background = False

		if self.rebuild_timer is not None:
			# build the UI *after* showing the window, so the user gets the
			# satisfaction of seeing the window pop up, even if it's incomplete...
			self.rebuild_ui(show_message = True)

		if not self.settings['keep search results']:
			self.switch_modes(show_system_menus = False, toggle_mode_button = True)


	def hide(self, *dummy):
		"""
		Hides the Cardapio window.
		"""

		if not self.visible: return

		self.panel_applet.draw_toggled_state(False)

		self.visible = False
		self.last_visibility_toggle = time()

		self.window.hide()

		if not self.settings['keep search results']:
			self.clear_search_entry()
			self.untoggle_and_show_all_sections()
		else:
			# remembering current search text in all entries
			self.search_entry.set_text(self.current_query)

		self.cancel_all_plugins()

		logging.info('(RSS = %s)' % get_memory_usage())

		return False # used for when hide() is called from a timer


	def hide_if_mouse_away(self):
		"""
		Hide the window if the cursor is *not* on top of it
		"""

		if self.focus_out_blocked: return

		root_window = gtk.gdk.get_default_root_window()
		mouse_x, mouse_y, dummy = root_window.get_pointer()

		dummy, dummy, window_width, window_height = self.window.get_allocation()
		window_x, window_y = self.window.get_position()

		cursor_in_window_x = (window_x <= mouse_x <= window_x + window_width)
		cursor_in_window_y = (window_y <= mouse_y <= window_y + window_height)
		if cursor_in_window_x and cursor_in_window_y: return

		if self.panel_applet.has_mouse_cursor(mouse_x, mouse_y): return

		self.hide()


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


	def remove_section_from_app_list(self, section_slab):
		"""
		Remove from the app list (used when searching) all apps that belong in a
		given section.
		"""

		i = 0
		while i < len(self.app_list):

			app = self.app_list[i]
			if section_slab == app['section']: self.app_list.pop(i)
			else: i += 1


	def build_system_list(self):
		"""
		Populate the System section
		"""

		# TODO: add session buttons here

		for node in self.sys_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, system_menu = True)

		self.system_category_pane.hide()

		section_slab, section_contents, dummy = self.add_slab(_('Uncategorized'), 'applications-other', tooltip = _('Other configuration tools'), hide = False, system_menu = True)
		self.add_tree_to_app_list(self.sys_tree.root, section_contents, self.sys_list, recursive = False)

		self.add_tree_to_app_list(self.sys_tree.root, self.system_section_contents, self.app_list)


	def build_uncategorized_list(self):
		"""
		Populate the Uncategorized section
		"""

		self.add_tree_to_app_list(self.app_tree.root, self.uncategorized_section_contents, self.app_list, recursive = False)


	def build_places_list(self):
		"""
		Populate the places list
		"""

		self.build_bookmarked_places_list(self.places_section_contents)
		self.build_system_places_list(self.places_section_contents)


	def build_system_places_list(self, section_contents):
		"""
		Populate the "system places", which include Computer, the list of
		connected drives, and so on.
		"""

		if self.volume_monitor is None:
			volume_monitor_already_existed = False
			self.volume_monitor = gio.volume_monitor_get() # keep a reference to avoid getting it garbage-collected
		else:
			volume_monitor_already_existed = True

		self.volumes = {}

		for mount in self.volume_monitor.get_mounts():

			volume = mount.get_volume()
			if volume is None: continue

			name = volume.get_name()
			icon_name = self.icon_helper.get_icon_name_from_gio_icon(volume.get_icon())

			try    : command = str(volume.get_mount().get_root().get_uri())
			except : command = ''

			self.add_app_button(name, icon_name, section_contents, 'xdg', command, tooltip = command, app_list = self.app_list)
			self.volumes[command] = volume

		self.add_app_button(_('Network'), 'network', section_contents, 'xdg', 'network://', tooltip = _('Browse the contents of the network'), app_list = self.app_list)

		connect_to_server_app_path = which('nautilus-connect-server')
		if connect_to_server_app_path is not None:
			self.add_app_button(_('Connect to Server'), 'network-server', section_contents, 'raw', connect_to_server_app_path, tooltip = _('Connect to a remote computer or shared disk'), app_list = self.app_list)

		self.add_app_button(_('Trash'), 'user-trash', section_contents, 'xdg', 'trash:///', tooltip = _('Open the trash'), app_list = self.app_list)

		if not volume_monitor_already_existed:
			self.volume_monitor.connect('mount-added', self.on_volume_monitor_changed)
			self.volume_monitor.connect('mount-removed', self.on_volume_monitor_changed)


	def build_bookmarked_places_list(self, section_contents):
		"""
		Populate the "bookmarked places", which include Home and your personal bookmarks.
		"""

		self.add_app_button(_('Home'), 'user-home', section_contents, 'xdg', self.home_folder_path, tooltip = _('Open your personal folder'), app_list = self.app_list)

		xdg_folders_file_path = os.path.join(DesktopEntry.xdg_config_home, 'user-dirs.dirs')
		xdg_folders_file = file(xdg_folders_file_path, 'r')

		# find desktop path and add desktop button
		for line in xdg_folders_file.readlines():

			res = re.match('\s*XDG_DESKTOP_DIR\s*=\s*"(.+)"', line)
			if res is not None:
				path = res.groups()[0]

				# check if the desktop path is the home folder, in which case we
				# do *not* need to add the desktop button.
				if os.path.abspath(path) == self.home_folder_path: break

				self.add_place(_('Desktop'), path, 'user-desktop')
				break

		xdg_folders_file.close()

		bookmark_file_path = os.path.join(self.home_folder_path, '.gtk-bookmarks')
		bookmark_file = file(bookmark_file_path, 'r')

		for line in bookmark_file.readlines():
			if line.strip(' \n\r\t'):

				name, path = self.get_place_name_and_path(line)
				path_type, dummy = urllib2.splittype(path)

				gio_path_obj = gio.File(path)
				if not gio_path_obj.query_exists() and path_type not in Cardapio.REMOTE_PROTOCOLS: continue

				self.add_place(name, path, 'folder')

		bookmark_file.close()

		if self.bookmark_monitor is None:
			self.bookmark_monitor = gio.File(bookmark_file_path).monitor_file() # keep a reference to avoid getting it garbage-collected
			self.bookmark_monitor.connect('changed', self.on_bookmark_monitor_changed)


	def on_bookmark_monitor_changed(self, monitor, file, other_file, event):
		"""
		Handler for when the user adds/removes a bookmarked folder using
		Nautilus or some other program
		"""

	 	# hoping this helps with bug 662249, in case there is some strange threading problem happening (although there are no explicit threads in this program)	
		self.bookmark_monitor.handler_block_by_func(self.on_bookmark_monitor_changed)

		if event == gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:
			self.clear_pane(self.places_section_contents)
			self.build_places_list()

		# same here
		self.bookmark_monitor.handler_unblock_by_func(self.on_bookmark_monitor_changed) 


	def on_volume_monitor_changed(self, monitor, drive):
		"""
		Handler for when volumes are mounted or ejected
		"""

	 	# hoping this helps with bug 662249, in case there is some strange threading problem happening (although there are no explicit threads in this program)	
		self.volume_monitor.handler_block_by_func(self.on_volume_monitor_changed)

		self.clear_pane(self.places_section_contents)
		self.build_places_list()

		# same here
		self.volume_monitor.handler_unblock_by_func(self.on_volume_monitor_changed) 


	def get_folder_name_and_path(self, folder_path):
		"""
		Returns a folder's name and path from its full filename
		"""

		path = folder_path.strip(' \n\r\t')

		res = folder_path.split(os.path.sep)
		if res:
			name = res[-1].strip(' \n\r\t').replace('%20', ' ')
			if name: return name, path

		# TODO: name remote folders like nautilus does (i.e. '/home on ftp.myserver.net')
		name = path.replace('%20', ' ')
		return name, path


	def get_place_name_and_path(self, folder_path):
		"""
		Return the name and path of a bookmarked folder given a line from the
		gtk-bookmarks file
		"""

		res = folder_path.split(' ')
		if len(res) > 1:
			name = ' '.join(res[1:]).strip(' \n\r\t')
			path = res[0]
			return name, path

		return self.get_folder_name_and_path(folder_path)


	def add_place(self, folder_name, folder_path, folder_icon):
		"""
		Add a folder to the Places list in Cardapio
		"""

		folder_path = os.path.expanduser(folder_path.replace('$HOME', '~')).strip(' \n\r\t')

		dummy, canonical_path = urllib2.splittype(folder_path)
		canonical_path = self.unescape_url(canonical_path)

		icon_name = self.icon_helper.get_icon_name_from_path(folder_path)
		if icon_name is None: icon_name = folder_icon
		self.add_app_button(folder_name, icon_name, self.places_section_contents, 'xdg', folder_path, tooltip = folder_path, app_list = self.app_list)


	def build_favorites_list(self, slab, list_name):
		"""
		Populate either the Pinned Items or Side Pane list
		"""

		no_results = True

		for app in self.settings[list_name]:

			# fixing a misspelling from the old config files...
			if 'icon_name' in app:
				app['icon name'] = app['icon_name']
				app.pop('icon_name')

			# adding a new property that was not in the old config files...
			if 'context menu' not in app:
				app['context menu'] = None

			button = self.add_app_button(app['name'], app['icon name'], self.section_list[slab]['contents'], app['type'], app['command'], tooltip = app['tooltip'], app_list = self.app_list)

			button.show()
			self.set_section_has_entries(slab)
			self.no_results_to_show = False
			no_results = False

			if slab == self.sidepane_section_slab:

				app_info = button.app_info
				button = self.add_button(app['name'], app['icon name'], self.sidepane, tooltip = app['tooltip'], button_type = Cardapio.SIDEPANE_BUTTON)
				button.app_info = app_info
				button.connect('clicked', self.on_app_button_clicked)
				button.connect('button-press-event', self.on_app_button_button_pressed)

		if no_results or (slab is self.sidepane_section_slab):
			self.hide_section(slab, fully_hide = True)

		elif (self.selected_section is not None) and (self.selected_section != slab):
			self.hide_section(slab)

		else:
			self.show_section(slab, fully_show = True)


	def build_session_list(self):
		"""
		Populate the Session list
		"""

		items = [
			[
				_('Lock Screen'),
				_('Protect your computer from unauthorized use'),
				'system-lock-screen',
				'gnome-screensaver-command --lock',
				self.left_session_pane,
			],
			[
				_('Log Out...'),
				_('Log out of this session to log in as a different user'),
				'system-log-out',
				'gnome-session-save --logout-dialog',
				self.right_session_pane,
			],
			[
				_('Shut Down...'),
				_('Shut down the system'),
				'system-shutdown',
				'gnome-session-save --shutdown-dialog',
				self.right_session_pane,
			],
		]

		for item in items:

			button = self.add_app_button(item[0], item[2], self.session_section_contents, 'raw', item[3], tooltip = item[1], app_list = self.app_list)
			app_info = button.app_info
			button = self.add_button(item[0], item[2], item[4], tooltip = item[1], button_type = Cardapio.SESSION_BUTTON)
			button.app_info = app_info
			button.connect('clicked', self.on_app_button_clicked)


	def build_applications_list(self):
		"""
		Populate the Applications list by reading the Gnome menus
		"""

		for node in self.app_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, hide = False)


	def add_slab(self, title_str, icon_name = None, tooltip = '', hide = False, node = None, system_menu = False):
		"""
		Add to the app pane a new section slab (i.e. a container holding a title
		label and a hbox to be filled with apps). This also adds the section
		name to the left pane, under the View label.
		"""

		if system_menu:
			category_pane = self.system_category_pane
			app_list = self.sys_list
		else:
			category_pane = self.category_pane
			app_list = self.app_list

		# add category to category pane
		sidebar_button = self.add_button(title_str, icon_name, category_pane, tooltip = tooltip, button_type = Cardapio.CATEGORY_BUTTON)

		# add category to application pane
		section_slab, section_contents, label = self.add_application_section(title_str)

		if node is not None:
			# add all apps in this category to application pane
			self.add_tree_to_app_list(node, section_contents, app_list)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)

		if hide:
			sidebar_button.hide()
			section_slab.hide()
			self.section_list[section_slab] = {
					'has entries': False,
					'category': sidebar_button,
					'contents': section_contents,
					'name': title_str,
					'is system section': system_menu,
					}

		else:
			self.section_list[section_slab] = {
					'has entries': True,
					'category': sidebar_button,
					'contents': section_contents,
					'name': title_str,
					'is system section': system_menu,
					}

		return section_slab, section_contents, label


	def add_places_slab(self):
		"""
		Add the Places slab to the app pane
		"""
		
		section_slab, section_contents, dummy = self.add_slab(_('Places'), 'folder', tooltip = _('Access documents and folders'), hide = False)
		self.places_section_slab = section_slab
		self.places_section_contents = section_contents


	def add_subfolders_slab(self):
		"""
		Add the Folder Contents slab to the app pane
		"""

		section_slab, section_contents, label = self.add_slab(_('Folder Contents'), 'system-file-manager', tooltip = _('Look inside folders'), hide = True)
		self.subfolders_section_slab = section_slab
		self.subfolders_section_contents = section_contents
		self.subfolders_label = label


	def add_pinneditems_slab(self):
		"""
		Add the Pinned Items slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Pinned items'), 'emblem-favorite', tooltip = _('Your favorite items'), hide = False)
		self.favorites_section_slab = section_slab
		self.favorites_section_contents = section_contents


	def add_sidepane_slab(self):
		"""
		Add the Side Pane slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Side Pane'), 'emblem-favorite', tooltip = _('Items pinned to the side pane'), hide = True)
		self.sidepane_section_slab = section_slab
		self.sidepane_section_contents = section_contents


	def add_uncategorized_slab(self):
		"""
		Add the Uncategorized slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Uncategorized'), 'applications-other', tooltip = _('Items that are not under any menu category'), hide = True)
		self.uncategorized_section_slab = section_slab
		self.uncategorized_section_contents = section_contents


	def add_session_slab(self):
		"""
		Add the Session slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Session'), 'session-properties', hide = True)
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents


	def add_system_slab(self):
		"""
		Add the System slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('System'), 'applications-system', hide = True)
		self.system_section_slab = section_slab
		self.system_section_contents = section_contents


	def add_plugin_slab(self, basename):
		"""
		Add the slab for a plugin (as identified by the basename)
		"""

		if basename not in self.plugin_database:
			self.settings['active plugins'].remove(basename)
			return

		plugin = self.plugin_database[basename]['instance']
		if plugin is None: return

		section_slab, section_contents, dummy = self.add_slab(plugin.category_name, plugin.category_icon, plugin.category_tooltip, hide = plugin.hide_from_sidebar)
		plugin.section_slab = section_slab
		plugin.section_contents = plugin.section_slab.get_children()[0].get_children()[0]


	def add_all_reorderable_slabs(self):
		"""
		Add all the reorderable slabs to the app pane
		"""

		self.add_sidepane_slab()

		for basename in self.settings['active plugins']:

			if basename == 'applications':
				self.build_applications_list()
				self.add_uncategorized_slab()
				self.add_session_slab()
				self.add_system_slab()

			elif basename == 'places':
				self.add_places_slab()

			elif basename == 'pinned':
				self.add_pinneditems_slab()

			else:
				self.add_plugin_slab(basename)


	def clear_pane(self, container):
		"""
		Remove all children from a GTK container
		"""

		# this is necessary when clearing section contents to avoid a memory
		# leak, but does nothing when clearing other containers:
		if container is not None: 
			if container.parent is not None and container.parent.parent is not None:
				self.app_list = [app for app in self.app_list if app['section'] != container.parent.parent]
				self.sys_list = [app for app in self.sys_list if app['section'] != container.parent.parent]

			for	child in container.get_children():
				container.remove(child)


	def setup_search_entry(self, place_at_top = False):
		"""
		Hides 3 of the 4 search entries and returns the visible entry.
		"""

		text = self.search_entry.get_text()

		place_at_left = not self.settings['mini mode']

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


	def clear_search_entry(self):
		"""
		Clears search entry.
		"""

		self.search_entry.set_text('')
		self.subfolder_stack = []


	# MODEL/VIEW SEPARATION EFFORT: mix of view and model
	def add_app_button(self, button_str, icon_name, parent_widget, command_type, command, tooltip = '', app_list = None):
		"""
		Adds a new button to the app pane
		"""

		# MODEL/VIEW SEPARATION EFFORT: view
		button = self.add_button(button_str, icon_name, parent_widget, tooltip, button_type = Cardapio.APP_BUTTON)

		button.connect('clicked', self.on_app_button_clicked)
		button.connect('button-press-event', self.on_app_button_button_pressed)
		button.connect('focus-in-event', self.on_app_button_focused)

		if command_type != 'callback' and command_type != 'raw':

			if command_type == 'app':
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

		# MODEL/VIEW SEPARATION EFFORT: model
		if app_list is not None:

			path, basename = os.path.split(command)
			if basename : basename, dummy = os.path.splitext(basename)
			else        : basename = path

			app_list.append({'name': button_str.lower(), 'button': button, 'section': parent_widget.parent.parent, 'basename' : basename, 'command' : command})

			# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
			# HARD-TO-FIND BUGS!!

		# save some metadata for easy access
		button.app_info = {
			'name'         : self.unescape_url(button_str),
			'tooltip'      : tooltip,
			'icon name'    : icon_name,
			'command'      : command,
			'type'         : command_type,
			'context menu' : None,
		}

		return button


	# MODEL/VIEW SEPARATION EFFORT: view
	def add_button(self, button_str, icon_name, parent_widget, tooltip = '', button_type = APP_BUTTON):
		"""
		Adds a button to a parent container
		"""

		if button_type != Cardapio.CATEGORY_BUTTON:
			button = gtk.Button()
		else:
			button = gtk.ToggleButton()

		button_str = self.unescape_url(button_str)

		label = gtk.Label(button_str)

		if button_type == Cardapio.APP_BUTTON:
			icon_size_pixels = self.icon_helper.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)

			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#layout = label.get_layout()
			#extents = layout.get_pixel_extents()
			#label.set_ellipsize(ELLIPSIZE_END)
			#label.set_max_width_chars(20)

		elif button_type == Cardapio.CATEGORY_BUTTON or button_type == Cardapio.SIDEPANE_BUTTON:
			icon_size_pixels = self.icon_helper.icon_size_category

		else:
			icon_size_pixels = self.icon_helper.icon_size_app

		icon_pixbuf = self.icon_helper.get_icon_pixbuf(icon_name, icon_size_pixels)
		icon = gtk.image_new_from_pixbuf(icon_pixbuf)

		hbox = gtk.HBox()
		hbox.add(icon)
		hbox.add(label)
		hbox.set_spacing(5)
		hbox.set_homogeneous(False)

		align = gtk.Alignment(0, 0.5)
		align.add(hbox)

		if tooltip:
			tooltip = self.unescape_url(tooltip)
			button.set_tooltip_text(tooltip)

		button.add(align)
		button.set_relief(gtk.RELIEF_NONE)
		button.set_use_underline(False)

		button.show_all()
		parent_widget.pack_start(button, expand = False, fill = False)

		return button


	# MODEL/VIEW SEPARATION EFFORT: view
	def add_application_section(self, section_title = None):
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

		self.application_pane.pack_start(section_slab, expand = False, fill = False)

		return section_slab, section_contents, label


	# MODEL/VIEW SEPARATION EFFORT: controller
	def add_tree_to_app_list(self, tree, parent_widget, app_list, recursive = True):
		"""
		Adds all the apps in a subtree of Gnome's menu as buttons in a given
		parent widget
		"""

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				self.add_app_button(node.name, node.icon, parent_widget, 'app', node.desktop_file_path, tooltip = node.get_comment(), app_list = app_list)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget, app_list)


	# MODEL/VIEW SEPARATION EFFORT: view
	def read_gtk_theme_info(self):
		"""
		Reads colors and other info from the GTK theme so that the app better
		adapt to any custom theme
		"""

		dummy_window = gtk.Window()
		dummy_window.set_name('ApplicationPane')
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_app_button_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_app_button_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_widget('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)

		scrollbar = gtk.VScrollbar()
		self.scrollbar_width = scrollbar.style_get_property('slider-width')


	# MODEL/VIEW SEPARATION EFFORT: controller
	def launch_edit_app(self, *dummy):
		"""
		Opens Gnome's menu editor.
		"""

		self.launch_raw('alacarte')


	# MODEL/VIEW SEPARATION EFFORT: controller
	def on_pin_this_app_clicked(self, widget):
		"""
		Handle the pinning action
		"""

		self.remove_section_from_app_list(self.favorites_section_slab)
		self.clear_pane(self.favorites_section_contents)
		self.settings['pinned items'].append(self.clicked_app)
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')


	# MODEL/VIEW SEPARATION EFFORT: controller
	def on_unpin_this_app_clicked(self, widget):
		"""
		Handle the unpinning action
		"""

		self.remove_section_from_app_list(self.favorites_section_slab)
		self.clear_pane(self.favorites_section_contents)
		self.settings['pinned items'].remove(self.clicked_app)
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')


	# MODEL/VIEW SEPARATION EFFORT: controller
	def on_add_to_side_pane_clicked(self, widget):
		"""
		Handle the "add to sidepane" action
		"""

		self.remove_section_from_app_list(self.sidepane_section_slab)
		self.clear_pane(self.sidepane_section_contents)
 		self.clear_pane(self.sidepane)
		self.settings['side pane items'].append(self.clicked_app)
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')
		self.sidepane.queue_resize() # required! or sidepane's allocation will be x,y,width,0 when first item is added
		self.get_widget('SideappSubdivider').queue_resize() # required! or sidepane will obscure the mode switcher button


	# MODEL/VIEW SEPARATION EFFORT: controller
	def on_remove_from_side_pane_clicked(self, widget):
		"""
		Handle the "remove from sidepane" action
		"""

		self.remove_section_from_app_list(self.sidepane_section_slab)
		self.clear_pane(self.sidepane_section_contents)
 		self.clear_pane(self.sidepane)
		self.settings['side pane items'].remove(self.clicked_app)
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')
		self.get_widget('SideappSubdivider').queue_resize() # required! or an extra space will show up where but button used to be


	def on_open_parent_folder_pressed(self, widget):
		"""
		Handle the "open parent folder" action
		"""

		parent_folder, dummy = os.path.split(self.clicked_app['command'])
		self.launch_xdg(parent_folder)


	def on_launch_in_background_pressed(self, widget):
		"""
		Handle the "launch in background" action
		"""

		self.launch_button_command(self.clicked_app, hide = False)


	def on_peek_inside_pressed(self, widget):
		"""
		Handle the "peek inside folder" action
		"""

		dummy, path = urllib2.splittype(self.clicked_app['command'])
		if os.path.isfile(path): path, dummy = os.path.split(path)
		path = self.unescape_url(path)
 		self.create_subfolder_stack(path)
		self.search_entry.set_text(self.subfolder_stack[-1][1] + '/')


	def on_eject_pressed(self, widget):
		"""
		Handle the "eject" action
		"""

		volume = self.volumes[self.clicked_app['command']]
		volume.eject(return_true)


	def on_app_button_button_pressed(self, widget, event):
		"""
		Show context menu for app buttons
		"""

		if event.type != gtk.gdk.BUTTON_PRESS: return

		if  event.button == 2:

			self.launch_button_command(widget.app_info, hide = False)

		elif event.button == 3:

			self.setup_context_menu(widget)
			self.block_focus_out_event()
			self.app_context_menu.popup(None, None, None, event.button, event.time)


	def setup_context_menu(self, widget):
		"""
		Show or hide different context menu options depending on the widget
		"""

		self.clicked_app = widget.app_info

		self.open_folder_menuitem.hide()
		self.peek_inside_menuitem.hide()
		self.eject_menuitem.hide()

		if widget.app_info['type'] == 'callback':
			self.pin_menuitem.hide()
			self.unpin_menuitem.hide()
			self.add_side_pane_menuitem.hide()
			self.remove_side_pane_menuitem.hide()
			self.app_menu_separator.hide()
			self.plugin_setup_context_menu()
			return

		already_pinned = False
		already_on_side_pane = False
		self.app_menu_separator.show()

		for command in [app['command'] for app in self.settings['pinned items']]:
			if command == widget.app_info['command']:
				already_pinned = True
				break

		for command in [app['command'] for app in self.settings['side pane items']]:
			if command == widget.app_info['command']:
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


		# figure out whether to show the 'open parent folder' menuitem
		split_command = urllib2.splittype(widget.app_info['command'])

		if widget.app_info['type'] == 'xdg' or len(split_command) == 2:

			path_type, canonical_path = split_command
			dummy, extension = os.path.splitext(canonical_path)

			# don't show it for network://, trash://, or .desktop files
			if path_type not in ('computer', 'network', 'trash') and extension != '.desktop':

				# only show if path that exists
				if os.path.exists(self.unescape_url(canonical_path)):
					self.open_folder_menuitem.show()
					self.peek_inside_menuitem.show()

		# figure out whether to show the 'eject' menuitem
		if widget.app_info['command'] in self.volumes:
			self.eject_menuitem.show()

		self.plugin_setup_context_menu()


	def plugin_setup_context_menu(self):
		"""
		Sets up context menu items as requested by individual plugins
		"""

		self.plugin_clear_context_menu()
		if 'context menu' not in self.clicked_app: return
		if self.clicked_app['context menu'] is None: return
		self.plugin_fill_context_menu()


	def plugin_clear_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""

		for menu_item in self.app_context_menu:
			if menu_item.name is not None and menu_item.name.startswith('PluginAction'):
				self.app_context_menu.remove(menu_item)


	def plugin_fill_context_menu(self):
		"""
		Add plugin-related actions to the context menu
		"""

		i = 0

		for item_info in self.clicked_app['context menu']:

			menu_item = gtk.ImageMenuItem(item_info['name'], True)
			menu_item.set_tooltip_text(item_info['tooltip'])
			menu_item.set_name('PluginAction' + str(i))
			i += 1

			if item_info['icon name'] is not None:
				icon_pixbuf = self.icon_helper.get_icon_pixbuf(item_info['icon name'], self.icon_helper.icon_size_menu)
				icon = gtk.image_new_from_pixbuf(icon_pixbuf)
				menu_item.set_image(icon)

			menu_item.app_info = item_info
			menu_item.connect('activate', self.on_app_button_clicked)

			menu_item.show_all()
			self.app_context_menu.append(menu_item)


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
		Set up drag action (not much goes on here...)
		"""

		icon_pixbuf = self.icon_helper.get_icon_pixbuf(button.app_info['icon name'], self.icon_helper.icon_size_app)
		button.drag_source_set_icon_pixbuf(icon_pixbuf)


	def on_app_button_data_get(self, button, drag_context, selection_data, info, time):
		"""
		Prepare the data that will be sent to the other app when the drag-and-drop
		operation is done
		"""

		command = button.app_info['command']
		command_type = button.app_info['type']

		if command_type == 'app':
			command = 'file://' + command

		elif command_type == 'xdg':

			path_type, dummy = urllib2.splittype(command)
			if path_type is None: command = 'file://' + command

			# TODO: figure out how to handle drag-and-drop for 'computer://' and
			# 'trash://' (it seems that nautilus has the same problems...)

		# TODO: handle command_type == 'raw' by creating a new desktop file and link?
		selection_data.set_uris([command])


	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list
		"""

		hide = (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK != gtk.gdk.CONTROL_MASK)
		self.launch_button_command(widget.app_info, hide = hide)


	def launch_button_command(self, app_info, hide):
		"""
		Execute app_info['command'], for any app_info['type']
		"""

		command = app_info['command']
		command_type = app_info['type']

		self.opened_last_app_in_background = not hide

		if command_type == 'app':
			self.launch_desktop(command, hide)

		elif command_type == 'raw':
			self.launch_raw(command, hide)

		elif command_type == 'xdg':
			self.launch_xdg(command, hide)

		elif command_type == 'callback':
			text = self.current_query
			if hide: self.hide()
			command(text)


	def launch_desktop(self, command, hide = True):
		"""
		Launch applications represented by .desktop files
		"""

		if os.path.exists(command):

			path = DesktopEntry.DesktopEntry(command).getExec()
			path = self.unescape_string(path)

			# Strip parts of the path that contain %<a-Z>

			path_parts = path.split()

			for i in xrange(len(path_parts)):
				if path_parts[i][0] == '%':
					path_parts[i] = ''

			path = ' '.join(path_parts)
			
			if DesktopEntry.DesktopEntry(command).getTerminal():
				return self.launch_raw_in_terminal(path, hide)
			else:
				return self.launch_raw(path, hide)

		else:
			logging.warn('Tried launching an app that does not exist: %s' % desktop_path)


	def launch_xdg(self, path, hide = True):
		"""
		Open a url, file or folder
		"""

		path = self.escape_quotes(self.unescape_url(path))
		path_type, dummy = urllib2.splittype(path)

		# if the file is executable, ask what to do
		if os.path.isfile(path) and os.access(path, os.X_OK):

			dummy, extension = os.path.splitext(path)

			# treat '.desktop' files differently
			if extension == '.desktop':
				self.launch_desktop(path, hide)
				return

			gio_file_info = gio.File(path).query_info('standard::content-type')
			content_type = gio_file_info.get_content_type()

			# only show the executable dialog for executable text files and scripts
			if content_type[:5] == 'text/' or content_type == 'application/x-shellscript':

				# show "Run in Terminal", "Display", "Cancel", "Run"
				response = self.show_executable_file_dialog(path)

				# if "Run in Terminal"
				if response == 1:
					return self.launch_raw_in_terminal(path, hide)

				# if "Display"
				elif response == 2:
					pass

				# if "Run"
				elif response == 3:
					return self.launch_raw(path, hide)

				# if "Cancel"
				else:
					return

		elif path_type in Cardapio.REMOTE_PROTOCOLS:
			special_handler = self.settings['handler for %s paths' % path_type]
			return self.launch_raw(special_handler % path, hide)

		return self.launch_raw("xdg-open '%s'" % path, hide)


	def launch_raw(self, path, hide = True):
		"""
		Run a command as a subprocess
		"""

		try:
			if self.panel_applet.panel_type is not None: # TODO: Why is this check here? Makes no sense!
				# allow launched apps to use Ubuntu's AppMenu
				os.environ['UBUNTU_MENUPROXY'] = 'libappmenu.so'

			subprocess.Popen(path, shell = True, cwd = self.home_folder_path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)
			return False

		if hide: self.hide()

		return True


	def launch_raw_in_terminal(self, path, hide = True):
		"""
		Run a command inside Gnome's default terminal
		"""

		try:
			gnome_execute_terminal_shell(self.home_folder_path, path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)
			return False

		if hide: self.hide()

		return True


	def escape_quotes(self, text):
		"""
		Sanitize a string by escaping quotation marks
		"""

		text = text.replace("'", r"\'")
		text = text.replace('"', r'\"')
		return text


	def unescape_url(self, text):
		"""
		Clear all sorts of escaping from a URL, like %20 -> [space]
		"""

		return urllib2.unquote(str(text)) # NOTE: it is possible that with python3 we will have to change this line


	def unescape_string(self, text):
		"""
		Clear all sorts of escaping from a string, like slash slash -> slash
		"""

		return text.decode('string-escape')


	def untoggle_and_show_all_sections(self):
		"""
		Show all sections that currently have search results, and untoggle all
		category buttons
		"""

		self.no_results_to_show = True

		for sec in self.section_list:
			if self.section_list[sec]['has entries'] and self.section_list[sec]['is system section'] == self.in_system_menu_mode:
				sec.show()
				self.no_results_to_show = False
			else:
				sec.hide()

		if not self.no_results_to_show:
			self.hide_no_results_text()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		self.selected_section = None

		if self.in_system_menu_mode:
			widget = self.all_system_sections_sidebar_button
		else:
			widget = self.all_sections_sidebar_button

		self.set_sidebar_button_active(widget, True)

		if self.is_search_entry_empty():
			widget.set_sensitive(False)


	def toggle_and_show_section(self, section_slab):
		"""
		Show a given section, make sure its button is toggled, and that
		no other buttons are toggled
		"""

		for sec in self.section_list:
			sec.hide()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		elif self.in_system_menu_mode and self.all_system_sections_sidebar_button.get_active():
			widget = self.all_system_sections_sidebar_button
			self.set_sidebar_button_active(widget, False)

		elif self.all_sections_sidebar_button.get_active():
			widget = self.all_sections_sidebar_button
			self.set_sidebar_button_active(widget, False)

		self.all_sections_sidebar_button.set_sensitive(True)
		self.all_system_sections_sidebar_button.set_sensitive(True)
		self.selected_section = section_slab

		self.consider_showing_no_results_text()
 		self.scroll_to_top()


	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""

		if text is None: text = self.no_results_text

		self.no_results_label.set_text(text)
		self.no_results_slab.show()


	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""

		self.no_results_slab.hide()


	def consider_showing_no_results_text(self):
		"""
		Decide whether the "No results" text should be shown
		"""

		if self.selected_section is None:

			if self.plugins_still_searching > 0:
				return

			if self.no_results_to_show:
				self.show_no_results_text()

			return

		if self.section_list[self.selected_section]['has entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(self.no_results_in_category_text % {'category_name': self.section_list[self.selected_section]['name']})


	def hide_all_transitory_sections(self, fully_hide = False):
		"""
		Hides all sections that should not appear in the sidebar when
		there is no text in the search entry
		"""

		# TODO: should fully_hide always be True here?
		self.hide_section(self.subfolders_section_slab, fully_hide)
		self.hide_section(self.session_section_slab, fully_hide)
		self.hide_section(self.system_section_slab, fully_hide)
		self.hide_section(self.sidepane_section_slab, fully_hide)
		self.hide_section(self.uncategorized_section_slab, fully_hide)

		self.hide_transitory_plugin_sections(fully_hide)


	def hide_section(self, section_slab, fully_hide = False):
		"""
		Hide a section slab. When fully_hide == False, the section is just
		hidden from the GUI, but not marked as empty in the model. When
		fully_hide = True, the section is both hidden in the GUI and marked
		as empty in the model.
		"""

		if fully_hide: self.set_section_is_empty(section_slab)
		section_slab.hide()


	def fully_hide_all_sections(self):
		"""
		Hide all sections, including plugins and non-plugins
		"""

		for section_slab in self.section_list:
			self.set_section_is_empty(section_slab)
			section_slab.hide()


	def fully_hide_plugin_sections(self):
		"""
		Hide all plugin sections
		"""

		for plugin in self.active_plugin_instances:
			if plugin.hide_from_sidebar:
				self.set_section_is_empty(plugin.section_slab)
				plugin.section_slab.hide()


	def hide_transitory_plugin_sections(self, fully_hide = False):
		"""
		Hide the section slabs for all plugins that are marked as transitory
		"""

		for plugin in self.active_plugin_instances:
			if plugin.hide_from_sidebar:
				self.hide_section(plugin.section_slab, fully_hide)


	def show_section(self, section_slab, fully_show = False):
		"""
		Show a section slab
		"""

		if fully_show:
			self.set_section_has_entries(section_slab)

		section_slab.show()


	def set_section_is_empty(self, section_slab):
		"""
		Mark a section as empty (no search results) and hide it
		"""

		self.section_list[section_slab]['has entries'] = False
		self.section_list[section_slab]['category'].hide()


	def set_section_has_entries(self, section_slab):
		"""
		Mark a section as having entries and show it
		"""

		self.section_list[section_slab]['has entries'] = True
		self.section_list[section_slab]['category'].show()


	def set_sidebar_button_active(self, button, state):
		"""
		Toggle a sidebar button
		"""

		if button.get_active() != state:
			self.auto_toggled_sidebar_button = True
			button.set_active(state)


	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""

		self.scroll_adjustment.set_value(0)



import __builtin__
__builtin__._ = _
__builtin__.CardapioPluginInterface = CardapioPluginInterface
__builtin__.dbus        = dbus
__builtin__.logging     = logging
__builtin__.subprocess  = subprocess
__builtin__.get_output  = get_output
__builtin__.fatal_error = fatal_error
__builtin__.which       = which

