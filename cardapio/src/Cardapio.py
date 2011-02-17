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
	from SettingsHelper import *
	from hacks import *
	from CardapioGtkView import *
	from OptionsWindow import *
	from CardapioPluginInterface import CardapioPluginInterface
	from CardapioAppletInterface import *
	from CardapioViewInterface import *

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

	version = '0.9.168'

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
		self.load_settings()
		logging.info('...done loading settings!')

		self.APP = APP

		self.cardapio_path    = cardapio_path
		self.home_folder_path = os.path.abspath(os.path.expanduser('~'))

		self.view             = CardapioGtkView(self)
		self.options_window   = OptionsWindow(self)

		self.reset_model()
		self.visible                       = False
		self.no_results_to_show            = False
		self.opened_last_app_in_background = False
		self.keybinding                    = None
		self.reset_search_timer            = None
		self.must_rebuild                  = False
		self.rebuild_timer                 = None
		self.search_timer_local            = None
		self.search_timer_remote           = None
		self.search_timeout_local          = None
		self.search_timeout_remote         = None
		self.in_system_menu_mode           = False
		self.plugins_still_searching       = 0
		self.bookmark_monitor              = None
		self.volume_monitor                = None
		self.last_visibility_toggle        = 0
		self.panel_applet                  = panel_applet

		self.package_root = '' if (__package__ is None) else ( __package__ + '.' )

		logging.info('Loading menus...')
		self.load_menus()
		logging.info('...done loading menus!')

		logging.info('Setting up DBus...')
		self.setup_dbus()
		logging.info('...done setting up DBus!')

		logging.info('Setting up UI...')
		self.setup_ui() # must be the first ui-related method to be called
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

		self.init_desktop_environment()

		logging.info('==> Done initializing Cardapio!')

		self.reset_search()

		if   show == Cardapio.SHOW_NEAR_MOUSE: self.show_hide_near_mouse()
		elif show == Cardapio.SHOW_CENTERED  : self.show()


	# This method is called from the View API
	def save_and_quit(self):
		"""
		Saves the current state and quits
		"""

		self.save()
		self.quit()


	def save(self):
		"""
		Saves the current state
		"""

		try:
			self.settings.save()
		except Exception, ex:
			logging.error('Error while saving settings: %s' % ex)


	def quit(self):
		"""
		Quits without saving the current state.
		"""

		logging.info('Exiting...')
		self.view.quit()


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


	def load_menus(self):
		"""
		Loads the XDG application menus into memory
		"""

		self.sys_tree = gmenu.lookup_tree('gnomecc.menu')
		self.have_control_center = (self.sys_tree.root is not None)

		if not self.have_control_center:
			self.sys_tree = gmenu.lookup_tree('settings.menu')
			logging.warn('Could not find Control Center menu file. Deactivating Control Center button.')

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)


	def setup_dbus(self):
		"""
		Sets up the session bus
		"""

		DBusGMainLoop(set_as_default=True)

		try: 
			self.bus = dbus.SessionBus()
			dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)

		except Exception, exception:
			logging.warn('Could not open dbus. Uncaught exception.')
			logging.warn(exception)


	def setup_ui(self):
		"""
		Calls the UI backend's "setup_ui" function
		"""

		self.no_results_text             = _('No results to show')
		self.no_results_in_category_text = _('No results to show in "%(category_name)s"')
		self.plugin_loading_text         = _('Searching...')
		self.plugin_timeout_text         = _('Search timed out')

		self.executable_file_dialog_text    = _('Do you want to run "%(file_name)s", or display its contents?')
		self.executable_file_dialog_caption = _('"%(file_name)s" is an executable text file.')

		self.icon_helper = IconHelper()
		self.icon_helper.register_icon_theme_listener(self.on_icon_theme_changed)

		self.view.setup_ui()
		self.options_window.setup_ui()


	def setup_panel_applet(self):
		"""
		Prepares Cardapio's applet in any of the compatible panels.
		"""

		if self.panel_applet is None:
			self.panel_applet = CardapioAppletInterface()

		if self.panel_applet.panel_type == PANEL_TYPE_GNOME2:
			self.view.remove_about_context_menu_items()
			self.view.hide_window_frame()

		else:
			self.view.show_window_frame()

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
			os.path.join(self.cardapio_path, 'plugins'),
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


	# This method is called from the View API
	def handle_section_all_clicked(self):
		"""
		This method is activated when the user presses the "All" section button.
		It unselects the currently-selected section if any, otherwise it clears
		the search entry.
		"""

		if self.selected_section is None:
			self.view.clear_search_entry()
			self.view.set_all_sections_sidebar_button_sensitive(False, self.in_system_menu_mode)
			return 

		self.untoggle_and_show_all_sections()


	# This method is called from the View API
	def handle_section_clicked(self, section):
		"""
		This method is activated when the user presses a section button (except
		for the "All" button). It causes that section to be displayed in case
		the it wasn't already visible, or hides it otherwise. Returns a boolean
		indicating whether the section button should be drawn toggled or not.
		"""

		# if already toggled, untoggle
		if self.selected_section == section:
			self.selected_section = None # necessary!
			self.untoggle_and_show_all_sections()
			return False

		# otherwise toggle
		self.toggle_and_show_section(section)
		return True


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


	def setup_plugins(self):
		"""
		Reads all plugins from the plugin folders and activates the ones that
		have been specified in the settings file.
		"""

		self.safe_cardapio_proxy = Cardapio.SafeCardapioProxy()
		self.safe_cardapio_proxy.write_to_log              = self.plugin_write_to_log
		self.safe_cardapio_proxy.handle_search_result      = self.plugin_handle_search_result
		self.safe_cardapio_proxy.handle_search_error       = self.plugin_handle_search_error
		self.safe_cardapio_proxy.ask_for_reload_permission = self.plugin_ask_for_reload_permission

		self.build_plugin_database()
		self.activate_plugins_from_settings() # investigate memory usage here


	def set_keybinding(self):
		"""
		Sets Cardapio's keybinding to the value chosen by the user
		"""

		self.unset_keybinding()

		self.keybinding = self.settings['keybinding']
		keybinder.bind(self.keybinding, self.show_hide)


	def unset_keybinding(self):
		"""
		Sets Cardapio's keybinding to nothing 
		"""

		if self.keybinding is not None:
			try: keybinder.unbind(self.keybinding)
			except: pass


	def apply_settings(self):
		"""
		Setup UI elements according to user preferences
		"""

		# set up keybinding
		self.set_keybinding()

		# set up applet
		if self.panel_applet.panel_type is not None:
			self.panel_applet.update_from_user_settings(self.settings)

		# set up everything else
		self.view.apply_settings()


	def reset_model(self, reset_all = True):
		"""
		Resets the data structures that contain all data related to Cardapio's
		main operation mode
		"""

		self.app_list               = []  # holds a list of all apps for searching purposes
		self.sys_list               = []  # holds a list of all apps in the system menus
		self.section_list           = {}  # holds a list of all sections to allow us to reference them by their section
		self.current_query          = ''
		self.subfolder_stack        = []
		self.selected_section       = None


	def load_settings(self):
		"""
		Loads the user's settings using a SettingsHelper
		"""

		try:
			self.settings = SettingsHelper(self.config_folder_path)

		except Exception, ex:
			msg = 'Unable to read settings: ' + str(ex)
			logging.error(msg)
			fatal_error('Settings error', msg)
			traceback.print_exc()
			sys.exit(1)


	# TODO MVC: Move to a new GnomeHelper.py file
	def init_desktop_environment(self):
		"""
		Runs a few initializations related to the user's desktop environment
		(only handles Gnome for now)
		"""

		if gnome_program_init is not None:
			# The function below prints a warning to the screen, saying that
			# an assertion has failed. Apparently this is normal. Ignore it.
			gnome_program_init('', self.version) 
			client = gnome_ui_master_client()
			client.connect('save-yourself', lambda x: self.save_and_quit())
			

	def build_ui(self):
		"""
		Read the contents of all menus and plugins and build the UI
		elements that support them.
		"""

		self.view.pre_build_ui()

		self.clear_all_panes()
		self.view.build_all_sections_sidebar_buttons(_('All'), _('Show all categories'))

		self.build_special_sections()
		self.build_reorderable_sections()

		if not self.have_control_center:
			self.view.hide_view_mode_button()

		self.fill_places_list()
		self.fill_session_list()
		self.fill_system_list()
		self.fill_uncategorized_list()
		self.fill_favorites_list(self.view.FAVORITES_SECTION, 'pinned items')
		self.fill_favorites_list(self.view.SIDEPANE_SECTION, 'side pane items')

		self.apply_settings()
		self.view.post_build_ui()
		self.view.hide_message_window()


	# TODO: make rebuild smarter: only rebuild whatever is absolutely necessary
	# This method is called from the View API
	def rebuild_ui(self, show_message = False):
		"""
		Rebuild the UI after a timer (this is called when the menu data changes,
		for example)
		"""

		# don't interrupt the user if a rebuild was requested while the window was shown
		# (instead, the rebuild will happen when self.hide() is called)
		if (not show_message) and self.view.is_window_visible(): 
			logging.info('Rebuild postponed: Cardapio is visible!')
			self.must_rebuild = True
			return False

		self.must_rebuild = False

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		logging.info('Rebuilding UI')

		if show_message:
			self.view.show_message_window()

		self.reset_model()
		self.build_ui()

		gc.collect()

		for plugin in self.active_plugin_instances:

			# trying to be too clever here, ended up causing a memory leak:
			#glib.idle_add(plugin.on_reload_permission_granted)

			# so now I'm back to doing this the regular way:
			plugin.on_reload_permission_granted
			# (leak solved!)

		self.reset_search()

		self.view.hide_rebuild_required_bar()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"
		# (actually, in this case this shouldn't be necessary, because we remove
		# the rebuild_timer above. But it's better to be safe then sorry...)


	def clear_all_panes(self):
		"""
		Clears all the different sections of the UI (panes)
		"""

		self.remove_all_buttons_from_section(self.view.APPLICATION_PANE)
		self.remove_all_buttons_from_section(self.view.SIDE_PANE)
		self.remove_all_buttons_from_section(self.view.LEFT_SESSION_PANE)
		self.remove_all_buttons_from_section(self.view.RIGHT_SESSION_PANE)

		self.view.remove_all_buttons_from_category_panes()


	# This method is used by both the View API and the Applet API
	def open_about_dialog(self, verb):
		"""
		Opens either the "About Gnome" dialog, or the "About Ubuntu" dialog,
		or the "About Cardapio" dialog
		"""

		if verb == 'AboutGnome':
			self.launch_raw('gnome-about')

		elif verb == 'AboutDistro':
			self.launch_raw('yelp ghelp:about-%s' % Cardapio.distro_name.lower())
			# NOTE: i'm assuming this is the pattern for all distros...

		else: self.view.open_about_dialog()


	# This method is called from the View API
	def open_options_dialog(self):
		"""
		Show the Options Dialog and populate its widgets with values from the
		user's settings.
		"""

		self.options_window.show()


	def plugin_iterator(self):
		"""
		Iterates first through all active plugins in their user-specified order,
		then through all inactive plugins alphabetically.
		"""

		plugin_list = []
		plugin_list += [basename for basename in self.settings['active plugins']]

		inactive_plugins = [basename for basename in self.plugin_database if basename not in plugin_list]
		plugin_list += sorted(inactive_plugins) # TODO: sort by regular name instead of basename

		for basename in plugin_list:

			plugin_info = self.plugin_database[basename]

			is_active   = (basename in self.settings['active plugins'])
			is_core     = (basename in self.core_plugins)
			is_required = (basename in self.required_plugins)

			yield (basename, plugin_info, is_active, is_core, is_required)


	def get_plugin_info(self, plugin_basename):
		"""
		Given the plugin filename (without the .py) this method returns a
		dictionary containing information about the plugin, such as its full
		name, version, author, and so on.
		"""

		return self.plugin_database[plugin_basename]


	# This method is called from the View API
	def end_resize(self):
		"""
		This function is called when the user releases the mouse after resizing the
		Cardapio window.
		"""

		self.save_dimensions()


	# This method is called from the View API
	def handle_mainwindow_focus_out(self):
		"""
		Make Cardapio disappear when it loses focus
		"""

		self.save_dimensions()

		# Make sure clicking the applet button doesn't cause a focus-out event.
		# Otherwise, the click signal can actually happen *after* the focus-out,
		# which causes the window to be re-shown rather than disappearing.  So
		# by ignoring this focus-out we actually make sure that Cardapio will be
		# hidden after all. Silly.
		mouse_x, mouse_y = self.view.get_cursor_coordinates()
		if self.panel_applet.has_mouse_cursor(mouse_x, mouse_y): return

		# If the last app was opened in the background, make sure Cardapio
		# doesn't hide when the app gets focused

		if self.opened_last_app_in_background:

			self.opened_last_app_in_background = False
			self.view.show_main_window()
			return

		self.hide()


	# This method is called from the View API
	def handle_mainwindow_cursor_leave(self):
		"""
		Handler for when the cursor leaves the Cardapio window.
		If using 'open on hover', this hides the Cardapio window after a delay.
		"""
		if self.panel_applet.panel_type is None: return

		# TODO - Delete this line on Feb 28th
		#if self.settings['open on hover'] and not self.view.focus_out_blocked:
		if self.settings['open on hover']:
			glib.timeout_add(self.settings['autohide delay'], self.hide_if_mouse_away)


	# This method is called from the View API
	def handle_user_closing_mainwindow(self):
		"""
		What happens when the user presses Alt-F4? If in panel mode,
		nothing. If in launcher mode, this terminates Cardapio.
		"""

		if self.panel_applet.panel_type is not None:
			# keep window alive if in panel mode
			return True

		self.save_and_quit()


	def on_menu_data_changed(self, tree):
		"""
		Rebuild the Cardapio UI whenever the menu data changes
		"""

		self.schedule_rebuild()

	
	def on_icon_theme_changed(self, *dummy):
		"""
		Rebuild the Cardapio UI whenever the icon theme changes
		"""

		self.schedule_rebuild()


	# This method is called from the View API 
	def rebuild_now(self):
		"""
		Rebuilds the Cardapio UI immediately. Should *never* be called from a plugin!
		"""
		self.rebuild_ui(show_message = True)


	# This method is called from the View API and plugin API
	def schedule_rebuild(self):
		"""
		Rebuilds the Cardapio UI after a timer
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.view.show_rebuild_required_bar()
		self.rebuild_timer = glib.timeout_add(self.settings['keep results duration'], self.rebuild_ui)


	# This method is called from the View API
	def switch_modes(self, show_system_menus, toggle_mode_button = False):
		"""
		Switches between "all menus" and "system menus" mode
		"""

		self.in_system_menu_mode = show_system_menus

		if toggle_mode_button: self.view.set_view_mode_button_toggled(show_system_menus)

		self.untoggle_and_show_all_sections()
		self.process_query(ignore_if_unchanged = False)

		if show_system_menus:
			self.view.hide_pane(self.view.CATEGORY_PANE)
			self.view.show_pane(self.view.SYSTEM_CATEGORY_PANE)

		else:
			self.view.hide_pane(self.view.SYSTEM_CATEGORY_PANE)
			self.view.show_pane(self.view.CATEGORY_PANE)


	# This method is called from the View API
	def handle_search_entry_icon_pressed(self):
		"""
		Handler for when the "clear" icon of the search entry is pressed
		"""

		if self.view.is_search_entry_empty():
			self.untoggle_and_show_all_sections()

		else:
			self.reset_search_query_and_selected_section()


	def parse_keyword_query(self, text):
		"""
		Returns the (keyword, text) pair of a keyword search of type 
		"?keyword text1 text2 ...", where text = "text1 text2 ..."
		"""

		keyword, dummy, text = text.partition(' ')
		if len(keyword) == 0: return None

		self.current_query = text
		return keyword[1:], text


	def handle_search_entry_changed(self):
		"""
		Handler for when the user types something in the search entry
		"""

		self.process_query(ignore_if_unchanged = True)

	
	def process_query(self, ignore_if_unchanged):
		"""
		Processes user query (i.e. the text in the search entry)
		"""

		text = self.view.get_search_entry_text().strip()
		if ignore_if_unchanged and text and text == self.current_query: return

		self.current_query = text

		self.no_results_to_show = True
		self.view.hide_no_results_text()

		in_subfolder_search_mode = (text and text.find('/') != -1)

		if in_subfolder_search_mode:
			# MUST run these lines BEFORE disappering with all sections
			first_app_info    = self.view.get_first_visible_app()
			# TODO MVC: there should be no need for get_first_visible_app. Instead,
			# the model should know the top app already!
			selected_app_info = self.view.get_selected_app()
			self.view.show_navigation_buttons()
		else:
			self.subfolder_stack = []
			self.view.hide_navigation_buttons()

		self.disappear_with_all_sections_and_category_buttons()
		handled = False

		# if showing the control center menu
		if self.in_system_menu_mode:
			handled = self.search_menus(text, self.sys_list)

		# if doing a subfolder search
		elif in_subfolder_search_mode:
			handled = self.search_subfolders(text, first_app_info, selected_app_info)

		# if doing a keyword search
		elif text and text[0] == '?':
			handled = self.search_with_plugin_keyword(text)

		# if none of these have "handled" the query, then just run a regular
		# search. This includes the regular menus, the system menus, and all
		# active plugins
		if not handled:
			self.view.hide_navigation_buttons()
			self.search_menus(text, self.app_list)
			self.schedule_search_with_all_plugins(text)

		if len(text) == 0: self.disappear_with_all_transitory_sections()
		else: self.view.set_all_sections_sidebar_button_sensitive(True, self.in_system_menu_mode)

		self.consider_showing_no_results_text()


	def search_menus(self, text, app_list):
		"""
		Start a menu search
		"""

		self.view.hide_pane(self.view.APPLICATION_PANE) # for speed

		text = text.lower()

		for app in app_list:

			if app['name'].find(text) == -1 and app['basename'].find(text) == -1:
				self.view.hide_button(app['button'])
			else:
				self.view.show_button(app['button'])
				self.mark_section_has_entries_and_show_category_button(app['section'])
				self.no_results_to_show = False

		if self.selected_section is None:
			self.untoggle_and_show_all_sections()

		self.view.show_pane(self.view.APPLICATION_PANE) # restore APPLICATION_PANE
		
		return True


	def search_subfolders(self, text, first_app_info, selected_app_info):
		"""
		Lets you browse your filesystem through Cardapio by typing slash "/" after
		a search query to "push into" a folder. 
		"""

		search_inside = (text[-1] == '/')
		slash_pos     = text.rfind('/')
		base_text     = text[slash_pos+1:]
		path          = None

		self.view.hide_section(self.view.SUBFOLDERS_SECTION) # for added performance
		self.remove_all_buttons_from_section(self.view.SUBFOLDERS_SECTION)

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
			if text == '' and selected_app_info is None: 
				path        = '/'
				base_text   = ''
				self.subfolder_stack = [(text, path)]

			# if pushing into a folder
			elif prev_level < curr_level:

				if first_app_info is not None:
					if selected_app_info is not None: app_info = selected_app_info
					else: app_info = first_app_info

					if app_info['type'] != 'xdg': return False
					path = self.escape_quotes(self.unescape_url(app_info['command']))

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
		self.view.set_subfolder_section_title(parent_name)

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
				self.add_app_button(_('Show additional results'), 'system-file-manager', self.view.SUBFOLDERS_SECTION, 'xdg', path, _('Show additional search results in a file browser'), None)
				break

			count += 1

			command = os.path.join(path, filename)
			icon_name = self.icon_helper.get_icon_name_from_path(command)
			if icon_name is None: icon_name = 'folder'

			basename, dummy = os.path.splitext(filename)
			self.add_app_button(filename, icon_name, self.view.SUBFOLDERS_SECTION, 'xdg', command, command, None)

		if count:
			self.view.show_section(self.view.SUBFOLDERS_SECTION)
			self.mark_section_has_entries_and_show_category_button(self.view.SUBFOLDERS_SECTION)
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


	def search_with_plugin_keyword(self, text):
		"""
		Search using the plugin that matches the keyword (specified as the first
		word in a query beginning with a question mark). This method always
		returns True, to make sure keyword searches take precedence over other
		types. 
		"""

		keywordtext = self.parse_keyword_query(text)
		if not keywordtext: return True

		keyword, text = keywordtext
		keyword_exists = False

		# search for a registered keyword that has this keyword as a substring
		for plugin_keyword in self.keyword_to_plugin_mapping:
			if plugin_keyword.find(keyword) == 0:
				keyword_exists = True
				keyword = plugin_keyword
				break

		if not keyword_exists: return True

		plugin = self.keyword_to_plugin_mapping[keyword]

		self.cancel_all_plugins()
		self.cancel_all_plugin_timers()

		self.schedule_search_with_specific_plugin(text, plugin.search_delay_type, plugin)

		return True


	def reset_search(self):
		"""
		Sets Cardapio's search to its default empty state
		"""
		self.schedule_search_with_all_plugins('')


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


	def show_plugin_loading_text(self, plugin):
		"""
		Write "Searching..." under the plugin section title
		"""

		self.view.show_section_status_text(plugin.section, self.plugin_loading_text)

		if self.selected_section is None or plugin.section == self.selected_section:
			self.view.show_section(plugin.section)
			self.view.hide_no_results_text()

		self.plugins_still_searching += 1


	def show_all_plugin_timeout_text(self, delay_type):
		"""
		Write "Plugin timed out..." under the plugin section title
		"""

		for plugin in self.active_plugin_instances:

			if not plugin.__is_running: continue
			if plugin.search_delay_type != delay_type: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)

			self.view.show_section_status_text(plugin.section, self.plugin_timeout_text)
			self.view.show_section(plugin.section)

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
		Handler for when a plugin returns some search results. This handler may be
		running on a different thread from the rest of the Cardapio application, since
		plugins can launch their own threads. For this reason, this code is actually 
		sent to be executed in the UI thread (if any).
		"""

		self.view.run_in_ui_thread(self.plugin_handle_search_result_synchronized, plugin, results, original_query)


	# TODO MVC
	def plugin_handle_search_result_synchronized(self, plugin, results, original_query):
		"""
		Handler for when a plugin returns some search results. This one is
		actually synchronized with the UI thread.
		"""

		self.view.hide_section(plugin.section) # for added performance

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

		self.view.remove_all_buttons_from_section(plugin.section)

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

			button = self.add_app_button(result['name'], icon_name, plugin.section, result['type'], result['command'], result['tooltip'], None)
			button.app_info['context menu'] = result['context menu']


		if results:

			self.no_results_to_show = False

			# TODO MVC: get rid of this somehow!
			section_contents = plugin.section.get_children()[0].get_children()[0]
			section_contents.show()

			self.mark_section_has_entries_and_show_category_button(plugin.section)

			if (self.selected_section is None) or (self.selected_section == plugin.section):
				self.view.show_section(plugin.section)
				self.view.hide_no_results_text()

			else:
				self.consider_showing_no_results_text()

		else:

			self.mark_section_empty_and_hide_category_button(plugin.section)

			if (self.selected_section is None) or (self.selected_section == plugin.section):
				self.view.hide_section(plugin.section)

			self.consider_showing_no_results_text()


	def plugin_ask_for_reload_permission(self, plugin):
		"""
		Handler for when a plugin asks Cardapio whether it can reload its
		database
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.view.show_rebuild_required_bar()
		self.rebuild_timer = glib.timeout_add(self.settings['keep results duration'], self.plugin_on_reload_permission_granted, plugin)


	def plugin_on_reload_permission_granted(self, plugin):
		"""
		Tell the plugin that it may rebuild its database now
		"""

		self.rebuild_timer = None
		plugin.on_reload_permission_granted()
		self.view.hide_rebuild_required_bar()

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


	def handle_search_entry_activate(self):
		"""
		Handler for when the user presses Enter on the search entry
		"""

		if self.view.is_search_entry_empty():
			# TODO: why is this needed? I don't see its effects...
			self.disappear_with_all_transitory_sections() 
			return

		app_info = self.view.get_first_visible_app()
		# TODO MVC: there should be no need for get_first_visible_app. Instead,
		# the model should know the top app already!

		if app_info is not None:
			ctrl_is_pressed = self.view.get_ctrl_key_state()
			self.handle_app_clicked(app_info, 1, ctrl_is_pressed)

		if not self.settings['keep search results']:
			self.reset_search_timer = glib.timeout_add(self.settings['keep results duration'], self.reset_search_timer_fired)


	# This method is called from the View API
	def handle_search_entry_tab_pressed(self):
		"""
		Handler for when the tab is pressed while the search entry is focused.
		This moves the focus into the app pane.
		"""
		self.view.focus_first_visible_app()


	# This method is called from the View API
	def handle_search_entry_escape_pressed(self):
		"""
		Handle what should happen when Escape is pressed while the search entry
		is focused.
		"""

		self.cancel_all_plugins()

		text = self.view.get_search_entry_text()
		slash_pos = text.rfind('/')

		if self.subfolder_stack and slash_pos != -1:
			self.go_to_parent_folder()

		elif not self.view.is_search_entry_empty():
			self.reset_search_query()

		elif self.selected_section is not None:
			self.untoggle_and_show_all_sections()

		elif self.in_system_menu_mode:
			self.switch_modes(show_system_menus = False, toggle_mode_button = True)

		else:
			self.hide()


	def choose_coordinates_for_window(self):
		"""
		Returns the appropriate coordinates for the given window. The
		coordinates are determined according to the following algorithm:

		- If there's no Cardapio applet, place the window in the center of the
		  screen

		- Otherwise, position the window near the applet (just below it if the
		  panel is top opriented, just to the left of it if the panel is right
		  oriented, and so on)
		"""

		window_width, window_height = self.view.get_window_size()
		screen_x, screen_y, screen_width, screen_height = self.view.get_screen_dimensions()

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


	def get_coordinates_inside_screen(self, x, y, force_anchor_right = False, force_anchor_bottom = False):
		"""
		If the window won't fit on the usable screen, given its size and
		proposed coordinates, the method will rotate it over its x, y, or x=y
		axis. Also, the window won't hide beyond the top and left borders of the
		usable screen.

		Returns the new x, y coordinates and two booleans indicating whether the
		window was rotated around the x and/or y axis.
		"""

		window_width, window_height = self.view.get_window_size()
		screen_x, screen_y, screen_width, screen_height = self.view.get_screen_dimensions()

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


	def restore_dimensions(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Resize Cardapio according to the user preferences
		"""

		if self.settings['window size'] is not None:
			self.view.resize_main_window(*self.settings['window size'])

		if x is None or y is None:
			x, y = self.choose_coordinates_for_window()

		x, y, anchor_right, anchor_bottom = self.get_coordinates_inside_screen(x, y, force_anchor_right, force_anchor_bottom)
		self.view.move_main_window(x, y, anchor_right, anchor_bottom)

		if self.settings['mini mode']:
			self.view.set_main_splitter_position(0)

		elif self.settings['splitter position'] > 0:
			self.view.set_main_splitter_position(self.settings['splitter position'])

		# decide which search bar to show (top or bottom) depending
		# on the y = 0 axis window invert
		self.view.setup_search_entry(not anchor_bottom, not self.settings['mini mode'])


	def save_dimensions(self):
		"""
		Save Cardapio's size into the user preferences
		"""

		self.settings['window size'] = self.view.get_window_size()
		if not self.settings['mini mode']:
			self.settings['splitter position'] = self.view.get_main_splitter_position()


	def toggle_mini_mode_ui(self):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""
		self.view.toggle_mini_mode_ui()


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

		mouse_x, mouse_y = self.view.get_cursor_coordinates()
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

		if self.reset_search_timer is not None:
			glib.source_remove(self.reset_search_timer)

		# reset to regular mode if 'keep search results' is off
		elif not self.settings['keep search results']:
			self.switch_modes(show_system_menus = False, toggle_mode_button = True)

		self.panel_applet.draw_toggled_state(True)

		self.restore_dimensions(x, y, force_anchor_right = False, force_anchor_bottom = False)

		self.view.focus_search_entry()
		self.view.show_main_window()

 		self.view.scroll_to_top()

		self.visible = True
		self.last_visibility_toggle = time()

		self.opened_last_app_in_background = False

		if self.rebuild_timer is not None:
			# build the UI *after* showing the window, so the user gets the
			# satisfaction of seeing the window pop up, even if it's incomplete...
			#self.rebuild_ui(show_message = True)
			self.view.show_rebuild_required_bar()


	def hide(self):
		"""
		Hides the Cardapio window.
		"""

		if not self.visible: return

		self.panel_applet.draw_toggled_state(False)

		self.visible = False
		self.last_visibility_toggle = time()

		self.view.hide_main_window()

		if self.settings['keep search results']:
			# remembering current search text in all entries
			self.view.set_search_entry_text(self.current_query)
		else:
			self.reset_search_timer = glib.timeout_add(self.settings['keep results duration'], self.reset_search_timer_fired)

		self.cancel_all_plugins()

		logging.info('(RSS = %s)' % get_memory_usage())

		if self.must_rebuild:
			self.schedule_rebuild()

		return False # used for when hide() is called from a timer


	def hide_if_mouse_away(self):
		"""
		Hide the window if the cursor is neither on top of it nor on top of the
		panel applet
		"""

		# TODO - Delete this line on Feb 28th
		#if self.view.focus_out_blocked: return

		mouse_x, mouse_y = self.view.get_cursor_coordinates()

		window_width, window_height = self.view.get_window_size()
		window_x, window_y = self.view.get_window_position()

		cursor_in_window_x = (window_x <= mouse_x <= window_x + window_width)
		cursor_in_window_y = (window_y <= mouse_y <= window_y + window_height)
		if cursor_in_window_x and cursor_in_window_y: return

		if self.panel_applet.has_mouse_cursor(mouse_x, mouse_y): return

		self.hide()


	def remove_section_from_app_list(self, section):
		"""
		Remove from the app list all apps that belong in a given section.
		"""

		i = 0
		while i < len(self.app_list):

			app = self.app_list[i]
			if section == app['section']: self.app_list.pop(i)
			else: i += 1


	def fill_system_list(self):
		"""
		Populate the System section
		"""

		# TODO: add session buttons here

		for node in self.sys_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_section(node.name, node.icon, node.get_comment(), node = node, system_menu = True)

		self.view.hide_pane(self.view.SYSTEM_CATEGORY_PANE)

		section, dummy = self.add_section(_('Uncategorized'), 'applications-other', tooltip = _('Other configuration tools'), hidden_when_no_query = False, system_menu = True)
		self.add_tree_to_app_list(self.sys_tree.root, section, self.sys_list, recursive = False)

		self.add_tree_to_app_list(self.sys_tree.root, self.view.SYSTEM_SECTION, self.app_list)


	def fill_uncategorized_list(self):
		"""
		Populate the Uncategorized section
		"""

		self.add_tree_to_app_list(self.app_tree.root, self.view.UNCATEGORIZED_SECTION, self.app_list, recursive = False)


	def fill_places_list(self):
		"""
		Populate the places list
		"""

		self.fill_bookmarked_places_list()
		self.fill_system_places_list()


	def fill_system_places_list(self):
		"""
		Populate the "system places", which include Computer, the list of
		connected drives, and so on.
		"""

		section = self.view.PLACES_SECTION

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

			self.add_app_button(name, icon_name, section, 'xdg', command, command, self.app_list)
			self.volumes[command] = volume

		self.add_app_button(_('Network'), 'network', section, 'xdg', 'network://', _('Browse the contents of the network'), self.app_list)

		connect_to_server_app_path = which('nautilus-connect-server')
		if connect_to_server_app_path is not None:
			self.add_app_button(_('Connect to Server'), 'network-server', section, 'raw', connect_to_server_app_path, _('Connect to a remote computer or shared disk'), self.app_list)

		self.add_app_button(_('Trash'), 'user-trash', section, 'xdg', 'trash:///', _('Open the trash'), self.app_list)

		if not volume_monitor_already_existed:
			self.volume_monitor.connect('mount-added', self.on_volume_monitor_changed)
			self.volume_monitor.connect('mount-removed', self.on_volume_monitor_changed)


	def fill_bookmarked_places_list(self):
		"""
		Populate the "bookmarked places", which include Home and your personal bookmarks.
		"""

		section = self.view.PLACES_SECTION

		self.add_app_button(_('Home'), 'user-home', section, 'xdg', self.home_folder_path, _('Open your personal folder'), self.app_list)

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
			self.remove_all_buttons_from_section(self.view.PLACES_SECTION)
			self.fill_places_list()

		# same here
		self.bookmark_monitor.handler_unblock_by_func(self.on_bookmark_monitor_changed) 


	def on_volume_monitor_changed(self, monitor, drive):
		"""
		Handler for when volumes are mounted or ejected
		"""

	 	# hoping this helps with bug 662249, in case there is some strange threading problem happening (although there are no explicit threads in this program)	
		self.volume_monitor.handler_block_by_func(self.on_volume_monitor_changed)

		self.remove_all_buttons_from_section(self.view.PLACES_SECTION)
		self.fill_places_list()

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
		self.add_app_button(folder_name, icon_name, self.view.PLACES_SECTION, 'xdg', folder_path, folder_path, self.app_list)


	def fill_favorites_list(self, section, list_name):
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

			app_button = self.add_app_button(app['name'], app['icon name'], section, app['type'], app['command'], app['tooltip'], self.app_list)

			self.view.show_button(app_button)
			self.mark_section_has_entries_and_show_category_button(section)
			self.no_results_to_show = False
			no_results = False

			if section == self.view.SIDEPANE_SECTION:
				button_str, tooltip = self.sanitize_button_info(app['name'], app['tooltip'])
				sidepane_button = self.view.add_sidepane_button(button_str, app['icon name'], self.view.SIDE_PANE, tooltip)
				sidepane_button.app_info = app_button.app_info

		if no_results or (section is self.view.SIDEPANE_SECTION):
			self.disappear_with_section_and_category_button(section)

		elif (self.selected_section is not None) and (self.selected_section != section):
			self.view.hide_section(section)

		else:
			self.mark_section_has_entries_and_show_category_button(section)
			self.view.show_section(section)


	def fill_session_list(self):
		"""
		Populate the Session list
		"""

		items = [
			[
				_('Lock Screen'),
				_('Protect your computer from unauthorized use'),
				'system-lock-screen',
				'gnome-screensaver-command --lock',
				self.view.LEFT_SESSION_PANE,
			],
			[
				_('Log Out...'),
				_('Log out of this session to log in as a different user'),
				'system-log-out',
				'gnome-session-save --logout-dialog',
				self.view.RIGHT_SESSION_PANE,
			],
			[
				_('Shut Down...'),
				_('Shut down the system'),
				'system-shutdown',
				'gnome-session-save --shutdown-dialog',
				self.view.RIGHT_SESSION_PANE,
			],
		]

		for item in items:

			app_button = self.add_app_button(item[0], item[2], self.view.SESSION_SECTION, 'raw', item[3], item[1], self.app_list)

			button_str, tooltip = self.sanitize_button_info(item[0], item[1])
			session_button = self.view.add_session_button(button_str, item[2], item[4], tooltip)

			session_button.app_info = app_button.app_info
			item.append(session_button)

		# TODO MVC
		self.view.session_button_locksys  = items[0][5]
		self.view.session_button_logout   = items[1][5]
		self.view.session_button_shutdown = items[2][5]


	def build_applications_list(self):
		"""
		Populate the Applications list by reading the Gnome menus
		"""

		for node in self.app_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_section(node.name, node.icon, node.get_comment(), node = node, hidden_when_no_query = False)


	def add_section(self, title_str, icon_name = None, tooltip = '', hidden_when_no_query = False, node = None, system_menu = False):
		"""
		Add to the app pane a new section (i.e. a container holding a title
		label and a hbox to be filled with apps). This also adds the section
		name to the left pane, under the View label.
		"""

		if system_menu:
			category_pane = self.view.SYSTEM_CATEGORY_PANE
			app_list = self.sys_list
		else:
			category_pane = self.view.CATEGORY_PANE
			app_list = self.app_list

		# add category to application pane
		section, label = self.view.add_application_section(title_str)

		if node is not None:
			# add all apps in this category to application pane
			self.add_tree_to_app_list(node, section, app_list)

		# add category to category pane
		title_str, tooltip = self.sanitize_button_info(title_str, tooltip)
		category_button = self.view.add_category_button(title_str, icon_name, category_pane, section, tooltip)

		if hidden_when_no_query:
			self.view.hide_button(category_button)
			self.view.hide_section(section)

		self.section_list[section] = {
			'must show'         : not hidden_when_no_query,
			'category button'   : category_button,
			'name'              : title_str,
			'is system section' : system_menu,
			}

		return section, label


	def build_special_sections(self):
		"""
		Builds sections that have special functions in the system, such as the
		one that contains the "no results to show" text and the one containing
		subfolder results.
		"""

		self.view.build_no_results_section()
		self.view.build_subfolders_section(_('Folder Contents'), _('Look inside folders'))


	def build_reorderable_sections(self):
		"""
		Add all the reorderable sections to the app pane
		"""

		self.view.build_sidepane_section(_('Side Pane'), _('Items pinned to the side pane'))

		for basename in self.settings['active plugins']:

			if basename == 'applications':
				self.build_applications_list()
				self.view.build_uncategorized_section(_('Uncategorized'), _('Items that are not under any menu category'))
				self.view.build_session_section(_('Session'), None)
				self.view.build_system_section(_('System'), None)

			elif basename == 'places':
				self.view.build_places_section(_('Places'), _('Access documents and folders'))

			elif basename == 'pinned':
				self.view.build_pinneditems_section(_('Pinned items'), _('Your favorite items'))

			elif basename in self.plugin_database:

				plugin = self.plugin_database[basename]['instance']
				if plugin is None: continue

				plugin.section, dummy = self.add_section(plugin.category_name, plugin.category_icon, plugin.category_tooltip, hidden_when_no_query = plugin.hide_from_sidebar)

			else:
				self.settings['active plugins'].remove(basename)


	def remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section
		"""

		# this is necessary to avoid a memory leak
		if section is not None: 
			self.app_list = [app for app in self.app_list if app['section'] != section]
			self.sys_list = [app for app in self.sys_list if app['section'] != section]

			self.view.remove_all_buttons_from_section(section)


	def reset_search_query(self):
		"""
		Clears search entry.
		"""

		self.reset_search_timer = None
		self.view.clear_search_entry()
		self.subfolder_stack = []


	def reset_search_timer_fired(self):
		"""
		Clears search entry and unselects the selected section button (if any)
		"""

		if not self.view.is_window_visible():
			self.reset_search_query_and_selected_section()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def reset_search_query_and_selected_section(self):
		"""
		Clears search entry and unselects the selected section button (if any)
		"""

		self.reset_search_query()
		self.untoggle_and_show_all_sections()


	def add_app_button(self, button_str, icon_name, section, command_type, command, tooltip, app_list):
		"""
		Adds a new button to the app pane
		"""

		if type(button_str) is str:
			button_str = unicode(button_str, 'utf-8')

		button_str, tooltip = self.sanitize_button_info(button_str, tooltip)
		button = self.view.add_app_button(button_str, icon_name, section, tooltip)

		# save some metadata for easy access
		button.app_info = {
			'name'         : self.unescape_url(button_str),
			'tooltip'      : tooltip,
			'icon name'    : icon_name,
			'command'      : command,
			'type'         : command_type,
			'context menu' : None,
		}

		# NOTE: I'm not too happy about keeping this outside the View, but I can't think
		# of a better solution...
		if command_type == 'app':
			self.view.setup_button_drag_and_drop(button, True)

		elif command_type == 'xdg':
			self.view.setup_button_drag_and_drop(button, False)

		if app_list is not None:

			path, basename = os.path.split(command)
			if basename : basename, dummy = os.path.splitext(basename)
			else        : basename = path

			app_list.append({
				'name'     : button_str.lower(),
				'button'   : button,
				'section'  : self.view.get_section_from_button(button),
				'basename' : basename,
				'command'  : command,
				})

		return button


	def sanitize_button_info(self, button_str, tooltip):
		"""
		Clean up the strings that have to do with a button: its label and its tooltip
		"""

		button_str = self.unescape_url(button_str)
		if tooltip: tooltip = self.unescape_url(tooltip)
		return button_str, tooltip


	def add_tree_to_app_list(self, tree, section, app_list, recursive = True):
		"""
		Adds all the apps in a subtree of Gnome's menu as buttons in a given
		parent widget
		"""

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				self.add_app_button(node.name, node.icon, section, 'app', node.desktop_file_path, node.get_comment(), app_list)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, section, app_list)


	# This method is called from the View API
	def launch_edit_app(self):
		"""
		Opens Gnome's menu editor.
		"""

		self.launch_raw('alacarte')


	def go_to_parent_folder(self):
		"""
		Goes to the parent of the folder specified by the string in the search
		entry.
		"""

		current_path = self.view.get_search_entry_text()
		slash_pos = current_path.rfind('/')

		if current_path[-1] == '/': slash_pos = current_path[:-1].rfind('/')
		current_path = current_path[:slash_pos+1]
		self.view.set_search_entry_text(current_path)
		self.view.place_text_cursor_at_end()


	# This method is called from the View API
	def handle_back_button_clicked(self):
		"""
		Handle the back-button's click action
		"""
		self.go_to_parent_folder()


	# This method is called from the View API
	def handle_pin_this_app_clicked(self, clicked_app_info):
		"""
		Handle the pinning action
		"""

		self.remove_section_from_app_list(self.view.FAVORITES_SECTION)
		self.remove_all_buttons_from_section(self.view.FAVORITES_SECTION)
		self.settings['pinned items'].append(clicked_app_info)
		self.fill_favorites_list(self.view.FAVORITES_SECTION, 'pinned items')


	# This method is called from the View API
	def handle_unpin_this_app_clicked(self, clicked_app_info):
		"""
		Handle the unpinning action
		"""

		self.remove_section_from_app_list(self.view.FAVORITES_SECTION)
		self.remove_all_buttons_from_section(self.view.FAVORITES_SECTION)
		self.settings['pinned items'].remove(clicked_app_info)
		self.fill_favorites_list(self.view.FAVORITES_SECTION, 'pinned items')


	# This method is called from the View API
	def handle_add_to_side_pane_clicked(self, clicked_app_info):
		"""
		Handle the "add to sidepane" action
		"""

		self.remove_section_from_app_list(self.view.SIDEPANE_SECTION)
		self.remove_all_buttons_from_section(self.view.SIDEPANE_SECTION)
 		self.remove_all_buttons_from_section(self.view.SIDE_PANE)
		self.settings['side pane items'].append(clicked_app_info)
		self.fill_favorites_list(self.view.SIDEPANE_SECTION, 'side pane items')
		self.view.SIDE_PANE.queue_resize() # required! or sidepane's allocation will be x,y,width,0 when first item is added
		self.view.get_widget('SideappSubdivider').queue_resize() # required! or sidepane will obscure the mode switcher button


	# This method is called from the View API
	def handle_remove_from_side_pane_clicked(self, clicked_app_info):
		"""
		Handle the "remove from sidepane" action
		"""

		self.remove_section_from_app_list(self.view.SIDEPANE_SECTION)
		self.remove_all_buttons_from_section(self.view.SIDEPANE_SECTION)
 		self.remove_all_buttons_from_section(self.view.SIDE_PANE)
		self.settings['side pane items'].remove(clicked_app_info)
		self.fill_favorites_list(self.view.SIDEPANE_SECTION, 'side pane items')
		self.view.get_widget('SideappSubdivider').queue_resize() # required! or an extra space will show up where but button used to be


	# This method is called from the View API
	def handle_launch_app_pressed(self, clicked_app_info):
		"""
		Handle the "launch" context-menu action
		"""

		self.launch_app(clicked_app_info, True)


	# This method is called from the View API
	def handle_open_parent_folder_pressed(self, clicked_app_info):
		"""
		Handle the "open parent folder" context-menu action
		"""

		parent_folder, dummy = os.path.split(clicked_app_info['command'])
		self.launch_xdg(parent_folder)


	# This method is called from the View API
	def handle_launch_in_background_pressed(self, clicked_app_info):
		"""
		Handle the "launch in background" context-menu action
		"""

		self.launch_app(clicked_app_info, hide = False)


	# This method is called from the View API
	def handle_peek_inside_pressed(self, clicked_app_info):
		"""
		Handle the "peek inside folder" context-menu action
		"""

		self.peek_inside_folder(clicked_app_info)


	# This method is called from the View API
	def handle_eject_pressed(self, clicked_app_info):
		"""
		Handle the "eject" context-menu action
		"""

		volume = self.volumes[clicked_app_info['command']]
		volume.eject(return_true)


	def setup_app_context_menu(self, app_info):
		"""
		Show or hide different context menu options depending on the widget
		"""

		self.view.hide_context_menu_option(self.view.OPEN_PARENT_MENUITEM)
		self.view.hide_context_menu_option(self.view.PEEK_INSIDE_MENUITEM)
		self.view.hide_context_menu_option(self.view.EJECT_MENUITEM)

		if app_info['type'] == 'callback':
			self.view.hide_context_menu_option(self.view.PIN_MENUITEM)
			self.view.hide_context_menu_option(self.view.UNPIN_MENUITEM)
			self.view.hide_context_menu_option(self.view.ADD_SIDE_PANE_MENUITEM)
			self.view.hide_context_menu_option(self.view.REMOVE_SIDE_PANE_MENUITEM)
			# TODO MVC
			self.view.app_menu_separator.hide() # this should happen automatically in setup_plugin_context_menu
			self.setup_plugin_context_menu(app_info)
			return

		already_pinned = False
		already_on_side_pane = False
		# TODO MVC
		self.view.app_menu_separator.show()

		for command in [app['command'] for app in self.settings['pinned items']]:
			if command == app_info['command']:
				already_pinned = True
				break

		for command in [app['command'] for app in self.settings['side pane items']]:
			if command == app_info['command']:
				already_on_side_pane = True
				break

		if already_pinned:
			self.view.hide_context_menu_option(self.view.PIN_MENUITEM)
			self.view.show_context_menu_option(self.view.UNPIN_MENUITEM)
		else:
			self.view.show_context_menu_option(self.view.PIN_MENUITEM)
			self.view.hide_context_menu_option(self.view.UNPIN_MENUITEM)

		if already_on_side_pane:
			self.view.hide_context_menu_option(self.view.ADD_SIDE_PANE_MENUITEM)
			self.view.show_context_menu_option(self.view.REMOVE_SIDE_PANE_MENUITEM)
		else:
			self.view.show_context_menu_option(self.view.ADD_SIDE_PANE_MENUITEM)
			self.view.hide_context_menu_option(self.view.REMOVE_SIDE_PANE_MENUITEM)

		if self.app_info_points_to_valid_folder:
			self.view.show_context_menu_option(self.view.OPEN_PARENT_MENUITEM)
			self.view.show_context_menu_option(self.view.PEEK_INSIDE_MENUITEM)

		# figure out whether to show the 'eject' menuitem
		if app_info['command'] in self.volumes:
			self.view.show_context_menu_option(self.view.EJECT_MENUITEM)

		self.setup_plugin_context_menu(app_info)


	def app_info_points_to_valid_folder(self, app_info):
		"""
		Returns True if the given app_info points to a local folder that exists
		"""

		app_type = app_info['type']

		if app_type == 'app' or app_type == 'raw': return False

		# TODO: move this into Controller
		# figure out whether to show the 'open parent folder' menuitem
		split_command = urllib2.splittype(app_info['command'])

		if app_type == 'xdg' or len(split_command) == 2:

			path_type, canonical_path = split_command
			dummy, extension = os.path.splitext(canonical_path)

			# don't show it for network://, trash://, or .desktop files
			if path_type not in ('computer', 'network', 'trash') and extension != '.desktop':

				#if os.path.exists(self.unescape_url(canonical_path)): 
				if os.path.isdir(self.unescape_url(canonical_path)): 
					return True

		return False


	# This method is called from the View API
	def setup_plugin_context_menu(self, app_info):
		"""
		Sets up context menu items as requested by individual plugins
		"""

		self.view.clear_plugin_context_menu()
		if 'context menu' not in app_info: return
		if app_info['context menu'] is None: return
		self.view.fill_plugin_context_menu(app_info['context menu'])


	def get_icon_pixbuf_from_app_info(self, app_info):
		"""
		Get the icon pixbuf for an app given its app_info dict
		"""

		return self.icon_helper.get_icon_pixbuf(app_info['icon name'], self.icon_helper.icon_size_app)


	def get_app_uri_for_drag_and_drop(self, app_info):
		"""
		Prepare the data that will be sent to the other application when an app is
		dragged from Cardapio.
		"""

		command = app_info['command']
		command_type = app_info['type']

		if command_type == 'app':
			command = 'file://' + command

		elif command_type == 'xdg':

			path_type, dummy = urllib2.splittype(command)
			if path_type is None: command = 'file://' + command

			# TODO: figure out how to handle drag-and-drop for 'computer://' and
			# 'trash://' (it seems that nautilus has the same problems...)

		# TODO: handle command_type == 'raw' by creating a new desktop file and link?

		return command


	# This method is called from the View API
	def handle_app_clicked(self, app_info, button, ctrl_is_pressed):
		"""
		Handles the on-click event for buttons on the app list
		"""

		if button == 1:
			# I'm not sure this is a good idea:
			#self.peek_or_launch_app(app_info, hide = not ctrl_is_pressed)

			# So i'm going back to this, for now:
			self.launch_app(app_info, hide = not ctrl_is_pressed)

			# I have more thinking to do about this...

		elif button == 2:
			self.launch_app(app_info, hide = False)

		elif button == 3:
			self.setup_app_context_menu(app_info)
			self.view.block_focus_out_event()
			self.view.popup_app_context_menu(app_info)


	def peek_or_launch_app(self, app_info, hide):
		"""
		Either peek inside a folder (if the app_info describes a local folder)
		or launch the item in the app_info
		"""

		if self.app_info_points_to_valid_folder(app_info):
			self.peek_inside_folder(app_info)

		else:
			self.launch_app(app_info, hide)


	def launch_app(self, app_info, hide):
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


	def peek_inside_folder(self, app_info):
		"""
		Shows within Cardapio the folder that given app_info points to
		"""

		dummy, path = urllib2.splittype(app_info['command'])
		if os.path.isfile(path): path, dummy = os.path.split(path)

		path = self.unescape_url(path)
		name = app_info['name']

		if self.subfolder_stack:
			entry_text = self.view.get_search_entry_text() + name
			self.subfolder_stack.append((entry_text, path))
		else:
			self.subfolder_stack = [(name, path)]
			entry_text = name

		self.view.set_search_entry_text(entry_text + '/')


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

		path = self.escape_quotes_for_shell(self.unescape_url(path))
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

				arg_dict = {'file_name': os.path.basename(path)}

				primary_text = self.executable_file_dialog_text % arg_dict
				secondary_text = self.executable_file_dialog_caption % arg_dict
				hide_terminal_option = not self.can_launch_in_terminal()

				# show "Run in Terminal", "Display", "Cancel", "Run"
				response = self.view.show_executable_file_dialog(primary_text, secondary_text, hide_terminal_option)

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


	# This method is called from the View API
	def can_launch_in_terminal(self):
		"""
		Returns true if the libraries for launching in a terminal are installed
		"""

		return (gnome_execute_terminal_shell is not None)


	def launch_raw_in_terminal(self, path, hide = True):
		"""
		Run a command inside Gnome's default terminal
		"""

		try:
			if self.can_launch_in_terminal():
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


	def escape_quotes_for_shell(self, text):
		"""
		Sanitize a string by escaping quotation marks, but treat single quotes
		differently since they cannot be escaped by the shell when in already
		single-quote mode (i.e. strong quoting).
		"""

		text = text.replace("'", r"'\''")
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
			if self.section_list[sec]['must show'] and self.section_list[sec]['is system section'] == self.in_system_menu_mode:
				self.view.show_section(sec)
				self.no_results_to_show = False
			else:
				self.view.hide_section(sec)

		if not self.no_results_to_show:
			self.view.hide_no_results_text()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category button']
			self.view.set_sidebar_button_toggled(widget, False)

		self.selected_section = None
		self.view.set_all_sections_sidebar_button_toggled(True, self.in_system_menu_mode)

		if self.view.is_search_entry_empty():
			self.view.set_all_sections_sidebar_button_sensitive(False, self.in_system_menu_mode)


	def toggle_and_show_section(self, section):
		"""
		Show a given section, make sure its button is toggled, and that
		no other buttons are toggled
		"""

		# hide all sections
		self.view.hide_sections(self.section_list)

		# untoggle the currently-toggled button, if any
		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category button']
			self.view.set_sidebar_button_toggled(widget, False)

		# untoggled and make sensitive the "All" buttons
		self.view.set_all_sections_sidebar_button_toggled(False, True)
		self.view.set_all_sections_sidebar_button_toggled(False, False)
		self.view.set_all_sections_sidebar_button_sensitive(True, True)
		self.view.set_all_sections_sidebar_button_sensitive(True, False)

		self.selected_section = section
		self.consider_showing_no_results_text()
 		self.view.scroll_to_top()


	def consider_showing_no_results_text(self):
		"""
		Decide whether the "No results" text should be shown (and, if so, show it)
		"""

		if self.selected_section is None:

			if self.plugins_still_searching > 0:
				return

			if self.no_results_to_show:
				self.view.show_no_results_text()

			return

		if self.section_list[self.selected_section]['must show']:
			self.view.show_section(self.selected_section)
			self.view.hide_no_results_text()

		else:
			self.view.hide_section(self.selected_section)
			self.view.show_no_results_text(self.no_results_in_category_text % {'category_name': self.section_list[self.selected_section]['name']})


	def disappear_with_all_transitory_sections(self):
		"""
		Hides all sections that should not appear in the sidebar when
		there is no text in the search entry
		"""

		self.disappear_with_section_and_category_button(self.view.SUBFOLDERS_SECTION)
		self.disappear_with_section_and_category_button(self.view.SESSION_SECTION)
		self.disappear_with_section_and_category_button(self.view.SYSTEM_SECTION)
		self.disappear_with_section_and_category_button(self.view.SIDEPANE_SECTION)
		self.disappear_with_section_and_category_button(self.view.UNCATEGORIZED_SECTION)

		self.disappear_with_all_transitory_plugin_sections()


	def disappear_with_section_and_category_button(self, section):
		"""
		Mark a section as empty, hide it, and hide its category button
		"""

		self.mark_section_empty_and_hide_category_button(section)
		self.view.hide_section(section)


	def disappear_with_all_sections_and_category_buttons(self):
		"""
		Hide all sections, including plugins and non-plugins
		"""

		for section in self.section_list:
			self.mark_section_empty_and_hide_category_button(section)
			self.view.hide_section(section)


	def disappear_with_all_transitory_plugin_sections(self):
		"""
		Hide the section for all plugins that are marked as transitory
		"""

		for plugin in self.active_plugin_instances:
			if plugin.hide_from_sidebar:
				self.disappear_with_section_and_category_button(plugin.section)


	def mark_section_empty_and_hide_category_button(self, section):
		"""
		Mark a section as empty (no search results) and hide its sidebar button
		"""

		if not self.section_list[section]['must show']: return
		self.section_list[section]['must show'] = False
		self.view.hide_button(self.section_list[section]['category button'])


	def mark_section_has_entries_and_show_category_button(self, section):
		"""
		Mark a section as having entries and show its sidebar button
		"""

		# check first for speed improvement (since this function usually gets
		# called several times, once for each app in the section)
		if self.section_list[section]['must show']: return

		self.section_list[section]['must show'] = True
		self.view.show_button(self.section_list[section]['category button'])

	
import __builtin__
__builtin__._ = _
__builtin__.CardapioPluginInterface = CardapioPluginInterface
__builtin__.dbus        = dbus
__builtin__.logging     = logging
__builtin__.subprocess  = subprocess
__builtin__.get_output  = get_output
__builtin__.fatal_error = fatal_error
__builtin__.which       = which

