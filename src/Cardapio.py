#
#  Cardapio is an alternative menu applet, launcher, and much more!
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
	from SettingsHelper import *
	from CardapioGtkView import *
	from OptionsWindow import *
	from DesktopEnvironment import *
	from CardapioPluginInterface import CardapioPluginInterface
	from CardapioSimpleDbusApplet import CardapioSimpleDbusApplet 
	from CardapioAppletInterface import *
	from CardapioViewInterface import *
	from MenuHelperInterface import *
	import Constants

	import gc
	import os
	import re
	import gtk
	import gio
	import glib
	import json

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

# if the computer has the gmenu module, use that (wrapped in the GMenuHelper module)
try:
	from GMenuHelper import GMenuHelper as MenuHelper

# otherwise use xdg (wrapped in the XDGMenuHelper module)
except Exception, exception:
	try:
		from XDGMenuHelper import XDGMenuHelper as MenuHelper
	except Exception, exception:
		fatal_error('Fatal error loading Cardapio', exception)
		sys.exit(1)

if gtk.ver < (2, 14, 0):
	fatal_error('Fatal error loading Cardapio', 'Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
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

setlocale(LC_ALL, '')
gettext.bindtextdomain(Constants.APP, prefix_path)

if hasattr(gettext, 'bind_textdomain_codeset'):
    gettext.bind_textdomain_codeset(Constants.APP, 'UTF-8')

gettext.textdomain(Constants.APP)
_ = gettext.gettext


# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
# Hack for making translations work with ui files

import gtk.glade
gtk.glade.bindtextdomain(Constants.APP, prefix_path)
gtk.glade.textdomain(Constants.APP)


# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
# Main Cardapio class

class Cardapio(dbus.service.Object):

	distro_name = platform.linux_distribution()[0]

	MIN_VISIBILITY_TOGGLE_INTERVAL    = 0.200 # seconds (this is a bit of a hack to fix some focus problems)
	PLUGIN_REBUILD_DELAY              = 30000 # milliseconds

	LOG_FILE_MAX_SIZE                 = 1000000 # bytes

	version = '0.9.200'

	REMOTE_PROTOCOLS = ['ftp', 'sftp', 'smb']


	class SafeCardapioProxy:
		"""
		Used to pass to the plugins an object containing a subset of Cardapio's
		members
		"""
		pass


	def __init__(self, show = False, panel_applet = None, debug = False):
		"""
		Creates an instance of Cardapio.
		"""

		self._create_xdg_folders()  # must happen before logging is setup
		self._setup_log_file(debug)

		logging.info('----------------- Cardapio launched -----------------')
		logging.info('Cardapio version: %s' % Cardapio.version)
		logging.info('Distribution: %s' % platform.platform())

		logging.info('Loading settings...')
		self._load_settings()
		logging.info('...done loading settings!')

		self.cardapio_path     = cardapio_path
		self._home_folder_path = os.path.abspath(os.path.expanduser('~'))

		logging.info('Setting up DBus...')
		self._setup_dbus()
		logging.info('...done setting up DBus!')

		self._view   = CardapioGtkView(self)
		self._applet = self._get_applet(panel_applet)
		self._options_window = OptionsWindow(self, self._applet.panel_type)

		self._reset_model()
		self._reset_members()

		logging.info('Setting up UI...')
		self._setup_ui() # must be the first ui-related method to be called
		logging.info('...done setting up UI!')

		logging.info('Setting up panel applet (if any)...')
		self._setup_applet()
		logging.info('...done setting up panel applet!')
			
		logging.info('Setting up Plugins...')
		self._setup_plugins()
		logging.info('...done setting up Plugins!')

		logging.info('Building UI...')
		self._build_ui()
		logging.info('...done building UI!')

		self.de.register_session_close_handler(self.save_and_quit)

		logging.info('==> Done initializing Cardapio!')

		# send the on_cardapio_loaded signal through DBus
		self.on_cardapio_loaded()

		self._reset_search()

		if   show == Constants.SHOW_NEAR_MOUSE: self.show_hide_near_mouse()
		elif show == Constants.SHOW_CENTERED  : self._show()


	def save_and_quit(self):
		"""
		Saves the current state and quits
		"""

		self.save()
		self._quit()


	def save(self):
		"""
		Saves the current state
		"""

		try:
			self.settings.save()
		except Exception, exception:
			logging.error('Error while saving settings: %s' % exception)


	def _quit(self):
		"""
		Quits without saving the current state.
		"""

		logging.info('Exiting...')
		self._view.quit()
		sys.exit(0)


	def _setup_log_file(self, debug):
		"""
		Opens the log file, clears it if it's too large, and prepares the logging module
		"""

		logging_filename = os.path.join(self._cache_folder_path, 'cardapio.log')

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


	def _load_application_menus(self):
		"""
		Loads the XDG application menus into memory
		"""

		self._sys_tree = MenuHelper('gnomecc.menu')
		self._have_control_center = self._sys_tree.is_valid()

		if not self._have_control_center:
			self._sys_tree = MenuHelper('settings.menu')
			logging.warn('Could not find gnomecc.menu. Trying settings.menu.')

			if not self._sys_tree.is_valid():
				self._sys_tree = MenuHelperInterface()
				logging.warn('Could not find settings.menu. Deactivating Control Center button.')


		self._app_tree = MenuHelper('applications.menu')
		self._app_tree.set_on_change_handler(self._on_menu_data_changed)
		self._sys_tree.set_on_change_handler(self._on_menu_data_changed)


	def _setup_dbus(self):
		"""
		Sets up the session bus
		"""

		DBusGMainLoop(set_as_default=True)

		try: 
			self._bus = dbus.SessionBus()
			dbus.service.Object.__init__(self, self._bus, Constants.BUS_OBJ_STR)

		except Exception, exception:
			logging.warn('Could not open dbus. Uncaught exception.')
			logging.warn(exception)


	def _setup_ui(self):
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
		self.icon_helper.register_icon_theme_listener(self._on_icon_theme_changed)

		self._view.setup_ui()
		self._options_window.setup_ui()


	def _get_applet(self, applet):
		"""
		Makes sure we detect applets that interact through the DBus, and also
		provide a fallback for when there is no applet.
		"""

		if applet is None:
			try    : applet = CardapioSimpleDbusApplet(self._bus)
			except : applet = CardapioStandAlone()

		return applet


	@dbus.service.signal(dbus_interface = Constants.BUS_NAME_STR, signature = None)
	def on_cardapio_loaded(self):
		"""
		This defines a DBus signal that gets called when Cardapio is finished
		loading for the first time.
		"""

		# nothing to do here
		pass


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = None)
	def quit(self):
		"""
		Allows applications to quit Cardapio through a DBus command
		"""

		self._quit()


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = 'b')
	def is_visible(self):
		"""
		Let's calling applications know whether Cardapio is visible at any moment in time
		"""
		return self._visible

	@dbus.service.signal(dbus_interface = Constants.BUS_NAME_STR, signature = None)
	def on_menu_visibility_changed(self):
		"""
		A signal that can be emitted over DBUS to determine exactly when a window is hidden/shown
		"""
		# nothing to do here
		pass

	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = 'ss')
	def get_applet_configuration(self):
		"""
		This method gets called when a DBus-connected applet gets initialized, to
		get the user-defined applet label and icon
		"""

		self._applet = self._get_applet(None)
		self._options_window.prepare_panel_related_options(self._applet.panel_type)
		self._setup_applet()

		return [self.settings['applet label'], self.settings['applet icon']]


	def _setup_applet(self):
		"""
		Prepares Cardapio's applet in any of the compatible panels.
		"""

		if (self._applet.panel_type == PANEL_TYPE_GNOME2 or 
		    self._applet.panel_type == PANEL_TYPE_MATE):
			self._view.remove_about_context_menu_items()

		if self.settings['show titlebar']:
			self._view.show_window_frame()
		else:
			self._view.hide_window_frame()

		self._applet.setup(self)


	def _load_plugin_class(self, basename):
		"""
		Returns the CardapioPlugin class from the plugin at basename.py.
		If it fails, it returns a string decribing the error.
		"""

		if __package__ is None:
			package = basename
		else:
			package = __package__ + '.plugins.' + basename

		try:
			plugin_module = __import__(package, fromlist = ['CardapioPlugin'], level = -1)
		except:
			return 'Could not import the plugin module'

		plugin_class = plugin_module.CardapioPlugin

		if plugin_class.plugin_api_version != CardapioPluginInterface.plugin_api_version:
			return 'Incorrect API version'

		return plugin_class


	def _build_plugin_database(self):
		"""
		Searches the plugins/ folder for .py files not starting with underscore.
		Creates the dict self._plugin_database indexed by the plugin filename's base name.
		"""

		self._plugin_database = {}

		plugin_class = CardapioPluginInterface(None)
		plugin_class.name              = _('Application menu')
		plugin_class.author            = _('Cardapio Team')
		plugin_class.description       = _('Displays installed applications')
		plugin_class.icon              = 'applications-other'
		plugin_class.version           = self.version
		plugin_class.category_name     = None
		plugin_class.category_tooltip  = None
		plugin_class.category_icon     = 'applications-other'
		self._plugin_database['applications'] = {'class' : plugin_class, 'instances' : []}

		plugin_class = CardapioPluginInterface(None)
		plugin_class.name              = _('Places menu')
		plugin_class.author            = _('Cardapio Team')
		plugin_class.description       = _('Displays a list of folders')
		plugin_class.icon              = 'folder'
		plugin_class.version           = self.version
		plugin_class.category_name     = _('Places')
		plugin_class.category_tooltip  = _('Access documents and folders')
		plugin_class.category_icon     = 'folder'
		self._plugin_database['places'] = {'class' : plugin_class, 'instances' : []}

		plugin_class = CardapioPluginInterface(None)
		plugin_class.name              = _('Pinned items')
		plugin_class.author            = _('Cardapio Team')
		plugin_class.description       = _('Displays the items that you marked as "pinned" using the context menu')
		plugin_class.icon              = 'emblem-favorite'
		plugin_class.version           = self.version
		plugin_class.category_name     = _('Pinned items')
		plugin_class.category_tooltip  = _('Your favorite items')
		plugin_class.category_icon     = 'emblem-favorite'
		self._plugin_database['pinned'] = {'class' : plugin_class, 'instances' : []}

		plugin_dirs = [
			os.path.join(DesktopEntry.xdg_config_home, 'Cardapio', 'plugins'),
			os.path.join(self.cardapio_path, 'plugins'),
			]

		# prepend in inverse order, to make sure ~/.config/Cardapio/plugins
		# ends up being the first on the list
		if plugin_dirs[1] not in sys.path: sys.path = [plugin_dirs[1]] + sys.path
		if plugin_dirs[0] not in sys.path: sys.path = [plugin_dirs[0]] + sys.path

		for plugin_dir in plugin_dirs:

			for root, dir_, files in os.walk(plugin_dir):
				for file_ in files:
					if len(file_) > 3 and file_[-3:] == '.py' and file_[0] != '_' and file_[0] != '.':
						basename = file_[:-3]
						plugin_class = self._load_plugin_class(basename)

						if type(plugin_class) is str: 
							logging.error('[%s] %s' % (basename, plugin_class))
							continue

						self._plugin_database[basename] = {
							'class'     : plugin_class,
							'instances' : [],
							}

		# TODO: figure out how to make Python unmap all the memory that gets
		# freed when the garbage collector releases the inactive plugins

	
	def _activate_plugins_from_settings(self):
		"""
		Initializes plugins in the database if the user's settings say so.
		"""

		self._must_activate_plugins = False

		# remove existing plugins

		for basename in self._plugin_database:
			plugins = self._plugin_database[basename]['instances']
			for plugin in plugins:
				if plugin is not None: plugin.__del__()
			self._plugin_database[basename]['instances'] = []

		self._active_plugin_instances  = []
		self._keyword_to_plugin_mapping = {}

		# active plugins listed in self.settings['plugin settings']

		all_plugin_settings = self.settings['plugin settings']

		for basename in self.settings['active plugins']:

			if basename in Constants.BUILTIN_PLUGINS: continue

			basename = str(basename)
			plugin_class = self._load_plugin_class(basename)

			if type(plugin_class) is str:
				logging.error('[%s] %s' % (basename, plugin_class))
				self.settings['active plugins'].remove(basename)
				continue

			logging.info('[%s] Initializing...' % basename)

			error = False

			for category in xrange(plugin_class.category_count):
				try:
					plugin = plugin_class(self.safe_cardapio_proxy, category)

				except Exception, exception:
					logging.error('[%s] Plugin did not load properly: uncaught exception.' % basename)
					logging.error(exception)
					self.settings['active plugins'].remove(basename)
					error = True
					break

				if not plugin.loaded:
					self._plugin_write_to_log(plugin, 'Plugin did not load properly')
					self.settings['active plugins'].remove(basename)
					error = True
					break

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

				plugin.__is_running = False
				plugin.__show_only_with_keyword = show_only_with_keyword

				if plugin_class.category_count > 1:
					try:
						plugin.category_name     = plugin_class.category_name[category]
						plugin.category_icon     = plugin_class.category_icon[category]
						plugin.category_tooltip  = plugin_class.category_tooltip[category]
						plugin.hide_from_sidebar = plugin_class.hide_from_sidebar[category]

					except Exception, exception:
						logging.error('[%s] Error in plugin syntax!' % basename)
						logging.error(exception)
						error = True
						break


				if plugin.search_delay_type is not None:
					plugin.search_delay_type = plugin.search_delay_type.partition(' search update delay')[0]

				if category == 0: 
					self._plugin_database[basename]['instances'] = []
					self._keyword_to_plugin_mapping[keyword]     = []

				self._plugin_database[basename]['instances'].append(plugin)
				self._keyword_to_plugin_mapping[keyword].append(plugin)
				self._active_plugin_instances.append(plugin)

			if error: 
				logging.error('[%s]             ...failed!' % basename)
			else:
				logging.info('[%s]             ...done!' % basename)

		gc.collect()


	def _plugin_write_to_log(self, plugin, text, is_debug = False, is_warning = False, is_error = False):
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
			write = logging.warn

		elif is_debug:
			write = logging.debug

		else:
			write = logging.info

		write('[%s] %s'  % (plugin.name, text))


	def _create_xdg_folders(self):
		"""
		Creates Cardapio's config and cache folders (usually at ~/.config/Cardapio and
		~/.cache/Cardapio)
		"""

		self._config_folder_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio')

		if not os.path.exists(self._config_folder_path):
			os.mkdir(self._config_folder_path)

		elif not os.path.isdir(self._config_folder_path):
			fatal_error('Error creating config folder!', 'Cannot create folder "%s" because a file with that name already exists!' % self._config_folder_path)
			self._quit()

		self._cache_folder_path = os.path.join(DesktopEntry.xdg_cache_home, 'Cardapio')

		if not os.path.exists(self._cache_folder_path):
			os.mkdir(self._cache_folder_path)

		elif not os.path.isdir(self._cache_folder_path):
			fatal_error('Error creating cache folder!', 'Cannot create folder "%s" because a file with that name already exists!' % self._cache_folder_path)
			self._quit()


	def _setup_plugins(self):
		"""
		Reads all plugins from the plugin folders and activates the ones that
		have been specified in the settings file.
		"""

		self.safe_cardapio_proxy = Cardapio.SafeCardapioProxy()
		self.safe_cardapio_proxy.write_to_log              = self._plugin_write_to_log
		self.safe_cardapio_proxy.handle_search_result      = self._plugin_handle_search_result
		self.safe_cardapio_proxy.handle_search_error       = self._plugin_handle_search_error
		self.safe_cardapio_proxy.ask_for_reload_permission = self._plugin_ask_for_reload_permission

		self._build_plugin_database()
		self._activate_plugins_from_settings() # investigate memory usage here


	def set_keybinding(self):
		"""
		Sets Cardapio's keybinding to the value chosen by the user
		"""

		self.unset_keybinding()

		self._keybinding = self.settings['keybinding']
		keybinder.bind(self._keybinding, self.show_hide)


	def unset_keybinding(self):
		"""
		Sets Cardapio's keybinding to nothing 
		"""

		if self._keybinding is not None:
			try: keybinder.unbind(self._keybinding)
			except: pass


	def apply_settings(self):
		"""
		Setup UI elements according to user preferences
		"""

		# set up keybinding
		self.set_keybinding()

		# set up applet
		if self._applet.IS_CONFIGURABLE:
			self._applet.update_from_user_settings(self.settings)

		# set up everything else
		self._view.apply_settings()


	def apply_plugin_settings(self):
		"""
		Setup plugin-related UI elements according to the user preferences
		"""

		self._schedule_rebuild(reactivate_plugins = True)


	def _reset_model(self, reset_all = True):
		"""
		Resets the data structures that contain all data related to Cardapio's
		main operation mode
		"""

		self._app_list         = []  # holds a list of all apps for searching purposes
		self._sys_list         = []  # holds a list of all apps in the system menus
		self._section_list     = {}  # holds a list of all sections to allow us to reference them by their section
		self._current_query    = ''
		self._subfolder_stack  = []
		self._selected_section = None

		self._volumes          = {}  # holds a list of all storage volumes found in the system

		self._builtin_applications_plugin_active = False
		self._builtin_places_plugin_active       = False


	def _reset_members(self):
		"""
		Resets Cardapio's member variables
		"""

		self._visible                       = False
		self._no_results_to_show            = False
		self._opened_last_app_in_background = False
		self._keybinding                    = None
		self._reset_search_timer            = None
		self._must_rebuild                  = False
		self._rebuild_timer                 = None
		self._search_timer_local            = None
		self._search_timer_remote           = None
		self._search_timeout_local          = None
		self._search_timeout_remote         = None
		self._in_system_menu_mode           = False
		self._plugins_still_searching       = 0
		self._bookmark_monitor              = None
		self._volume_monitor                = None
		self._last_visibility_toggle        = 0
		self._default_window_position       = None

		# These may be used by the View or OptionsWindow classes
		self.de                             = DesktopEnvironment(self)
		self.icon_helper                    = None


	def _load_settings(self):
		"""
		Loads the user's settings using a SettingsHelper
		"""

		try:
			# This object may be used by the View or OptionsWindow classes
			self.settings = SettingsHelper(self._config_folder_path)

		except Exception, ex:
			msg = 'Unable to read settings: ' + str(ex)
			logging.error(msg)
			fatal_error('Settings error', msg)
			traceback.print_exc()
			sys.exit(1)


	def _build_ui(self):
		"""
		Read the contents of all menus and plugins and build the UI
		elements that support them.
		"""

		self._view.pre_build_ui()

		self._clear_all_panes()
		self._view.hide_view_mode_button()
		self._view.build_all_sections_sidebar_buttons(_('All'), _('Show all categories'))

		self._build_special_sections()
		self._build_reorderable_sections()

		if self._builtin_places_plugin_active:
			self._fill_places_list()

		if self._builtin_applications_plugin_active:
			self._fill_session_list()
			self._fill_system_list()
			self._fill_uncategorized_list()

			if self._have_control_center:
				self._view.show_view_mode_button()

		self._fill_favorites_list(self._view.FAVORITES_SECTION, 'pinned items')
		self._fill_favorites_list(self._view.SIDEPANE_SECTION, 'side pane items')

		self.apply_settings()
		self._view.post_build_ui()
		self._view.hide_message_window()


	def _rebuild_ui(self, show_message = False):
		"""
		Rebuild the UI after a timer (this is called when the menu data changes,
		for example)
		"""

		# TODO: make rebuild smarter: only rebuild whatever is absolutely necessary

		# TODO: make rebuild even smarter: use a "double buffer" approach, where
		# things are rebuilt into a second copy of the model/ui, which at the end is
		# swapped in. This way, Cardapio should *never* be temporarily inaccessible
		# due to a rebuild.

		if self._rebuild_timer is not None:
			glib.source_remove(self._rebuild_timer)
			self._rebuild_timer = None

		# don't interrupt the user if a rebuild was requested while the window was shown
		# (instead, the rebuild will happen when self._hide() is called)
		if (not show_message) and self._view.is_window_visible(): 
			logging.info('Rebuild postponed: Cardapio is visible!')
			self._must_rebuild = True
			return False # Required! Makes sure this is a one-shot timer

		self._view.hide_rebuild_required_bar()
		self._must_rebuild = False

		logging.info('Rebuilding UI')

		if show_message:
			self._view.show_message_window()

		self._reset_model()
		if self._must_activate_plugins: self._activate_plugins_from_settings()
		self._build_ui()

		gc.collect()

		if not self._must_activate_plugins:
			for plugin in self._active_plugin_instances:

				# trying to be too clever here, ended up causing a memory leak:
				#glib.idle_add(plugin.on_reload_permission_granted)

				# so now I'm back to doing this the regular way:
				plugin.on_reload_permission_granted()
				# (leak solved!)

		#self._reset_search_query()
		self._reset_search()
		self._view.focus_search_entry()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"
		# (actually, in this case this shouldn't be necessary, because we remove
		# the rebuild_timer above. But it's better to be safe then sorry...)


	def _clear_all_panes(self):
		"""
		Clears all the different sections of the UI (panes)
		"""

		self._remove_all_buttons_from_section(self._view.APPLICATION_PANE)
		self._remove_all_buttons_from_section(self._view.SIDE_PANE)
		self._remove_all_buttons_from_section(self._view.LEFT_SESSION_PANE)
		self._remove_all_buttons_from_section(self._view.RIGHT_SESSION_PANE)

		self._view.remove_all_buttons_from_category_panes()


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = None)
	def open_options_dialog(self):
		"""
		Show the Options Dialog and populate its widgets with values from the
		user's settings.
		"""

		self._hide()
		self._options_window.show()


	def get_plugin_class(self, plugin_basename):
		"""
		Given the plugin filename (without the .py) this method returns the
		CardapioPlugin class containing information about the plugin, such as
		its full name, version, author, and so on.
		"""

		return self._plugin_database[plugin_basename]['class']


	def get_inactive_plugins(self):
		"""
		Returns the basenames of all plugins in the plugin_database that are not
		present in settings['active plugins'] (i.e. have not been selected by the user
		to be activated in Cardapio)
		"""

		return [basename for basename in self._plugin_database if basename not in self.settings['active plugins']]


	def _on_menu_data_changed(self, tree):
		"""
		Rebuild the Cardapio UI whenever the menu data changes
		"""

		self._schedule_rebuild()

	
	def _on_icon_theme_changed(self, *dummy):
		"""
		Rebuild the Cardapio UI whenever the icon theme changes
		"""

		self._schedule_rebuild()


	def _schedule_rebuild(self, reactivate_plugins = False):
		"""
		Rebuilds the Cardapio UI after a timer
		"""

		if self._rebuild_timer is not None:
			glib.source_remove(self._rebuild_timer)

		if reactivate_plugins:
			self._must_activate_plugins = True
		#else: don't set to False because we want to avoid race conditions

		if reactivate_plugins:
			rebuild_delay = Cardapio.PLUGIN_REBUILD_DELAY
			# this larger delay makes it a bit nicer to reorganize plugins,
			# since it keeps Cardapio from reloading all the time
		else:
			rebuild_delay = self.settings['keep results duration']

		self._view.show_rebuild_required_bar()
		self._rebuild_timer = glib.timeout_add(rebuild_delay, self._rebuild_ui)


	def _switch_modes(self, show_system_menus, toggle_mode_button = False):
		"""
		Switches between "all menus" and "system menus" mode
		"""

		self._in_system_menu_mode = show_system_menus

		if toggle_mode_button: self._view.set_view_mode_button_toggled(show_system_menus)

		self._untoggle_and_show_all_sections()
		self._process_query(ignore_if_unchanged = False)

		if show_system_menus:
			self._view.hide_pane(self._view.CATEGORY_PANE)
			self._view.show_pane(self._view.SYSTEM_CATEGORY_PANE)

		else:
			self._view.hide_pane(self._view.SYSTEM_CATEGORY_PANE)
			self._view.show_pane(self._view.CATEGORY_PANE)


	def _parse_keyword_query(self, text):
		"""
		Returns the (keyword, text) pair of a keyword search of type 
		"?keyword text1 text2 ...", where text = "text1 text2 ..."
		"""

		keyword, dummy, text = text.partition(' ')
		if len(keyword) == 0: return None

		self._current_query = text
		return keyword[1:], text


	def _process_query(self, ignore_if_unchanged):
		"""
		Processes user query (i.e. the text in the search entry)
		"""

		text = self._view.get_search_entry_text().strip()
		if ignore_if_unchanged and text and text == self._current_query: return

		self._current_query = text

		self._no_results_to_show = True
		self._view.hide_no_results_text()

		in_subfolder_search_mode = (text and text.find('/') != -1)

		if in_subfolder_search_mode:

			# MUST run these lines BEFORE disappering with all sections
			first_app_info = self._view.get_nth_visible_app(1)

			# About the line above, there should be no need for
			# asking the view what is the first visible app (with
			# get_nth_visible_app). Instead, the model should know the top
			# app already! Except this is not exactly that straight-forward,
			# since it depends on the plugin ordering chosen by the user. And to
			# further complicate matters, some plugins respond after a
			# local/remote delay. So this seemed like the simplest solution.

			selected_app_info = self._view.get_selected_app()
			self._view.show_navigation_buttons()

		else:
			self._subfolder_stack = []
			self._view.hide_navigation_buttons()

		self._disappear_with_all_sections_and_category_buttons()
		handled = False

		# if showing the control center menu
		if self._in_system_menu_mode:
			handled = self._search_menus(text, self._sys_list)

		# if doing a subfolder search
		elif in_subfolder_search_mode:
			handled = self._search_subfolders(text, first_app_info, selected_app_info)

		# if doing a keyword search
		elif text and text[0] == '?':
			handled = self._search_with_plugin_keyword(text)

		# if none of these have "handled" the query, then just run a regular
		# search. This includes the regular menus, the system menus, and all
		# active plugins
		if not handled:
			self._view.hide_navigation_buttons()
			self._search_menus(text, self._app_list)
			self._schedule_search_with_all_plugins(text)

		if len(text) == 0: self._disappear_with_all_transitory_sections()
		else: self._view.set_all_sections_sidebar_button_sensitive(True, self._in_system_menu_mode)

		self._consider_showing_no_results_text()


	def _search_menus(self, text, app_list):
		"""
		Start a menu search
		"""

		if not self._builtin_applications_plugin_active: return False

		self._view.hide_pane(self._view.APPLICATION_PANE) # for speed

		text = text.lower()

		for app in app_list:

			if app['name'].find(text) == -1 and app['basename'].find(text) == -1:
				self._view.hide_button(app['button'])
			else:
				self._view.show_button(app['button'])
				self._no_results_to_show = False
				self._mark_section_has_entries_and_show_category_button(app['section'])

		if self._selected_section is None:
			self._untoggle_and_show_all_sections()

		self._view.show_pane(self._view.APPLICATION_PANE) # restore APPLICATION_PANE
		
		return True


	def _search_subfolders(self, text, first_app_info, selected_app_info):
		"""
		Lets you browse your filesystem through Cardapio by typing slash "/" after
		a search query to "push into" a folder. 
		"""

		search_inside = (text[-1] == '/')
		slash_pos     = text.rfind('/')
		base_text     = text[slash_pos+1:]
		path          = None

		self._view.hide_section(self._view.SUBFOLDERS_SECTION) # for added performance
		self._remove_all_buttons_from_section(self._view.SUBFOLDERS_SECTION)

		if not search_inside:
			if not self._subfolder_stack: return False
			slash_count = text.count('/')
			path = self._subfolder_stack[slash_count - 1][1]
			self._subfolder_stack = self._subfolder_stack[:slash_count]

		else:
			text = text[:-1]
			curr_level = text.count('/')

			if self._subfolder_stack:
				prev_level = self._subfolder_stack[-1][0].count('/')
			else: 
				prev_level = -1

			# if typed root folder
			if text == '' and selected_app_info is None: 
				path        = u'/'
				base_text   = ''
				self._subfolder_stack = [(text, path)]

			# if pushing into a folder
			elif prev_level < curr_level:

				if first_app_info is not None:
					if selected_app_info is not None: app_info = selected_app_info
					else: app_info = first_app_info

					if app_info['type'] != 'xdg': return False
					path = app_info['command']
					path = self._unescape_url(path)
					# removed this (was it ever necessary?)
					#path = self.escape_quotes(path)

					path_type, path = urllib2.splittype(path)
					if path_type and path_type != 'file': return False
					if not os.path.isdir(path): return False
					self._subfolder_stack.append((text, path))

			# if popping out of a folder
			else:
				if prev_level > curr_level: self._subfolder_stack.pop()
				path = self._subfolder_stack[-1][1]

		if path is None: return False

		if path == '/': parent_name = _('Filesystem Root')
		else: parent_name = os.path.basename(path)
		self._view.set_subfolder_section_title(parent_name)

		base_text = base_text.lower()
		ignore_hidden = True

		if base_text:
			# show hidden files if user query is something like 'hi/there/.dude'
			if base_text[0] == '.': 
				ignore_hidden = False
				base_text = base_text[1:]

			costs_and_words = [(f.lower().find(base_text), f) for f in os.listdir(path)]
			costs_and_words = sorted(costs_and_words) # sort by cost
			matches = [cw[1] for cw in costs_and_words if cw[0] >= 0]
		else:
			matches = os.listdir(path)
			matches = sorted(matches, key = unicode.lower)

		try: 
			self._file_looper = self._file_looper_generator(matches, path, ignore_hidden)
			count = self._file_looper.next()

		except Exception, e:
			count = 0

		if count > 0:
			self._view.show_section(self._view.SUBFOLDERS_SECTION)
			self._no_results_to_show = False
			self._mark_section_has_entries_and_show_category_button(self._view.SUBFOLDERS_SECTION)

		else:
			self._no_results_to_show = True

		return True


	def _file_looper_generator(self, matches, path, ignore_hidden):
		"""
		Creates a generator object that adds an app button for each file/folder
		found in 'matches', and yields when the maximum number of results has been
		shown. This is useful for paging the results.
		"""

		count    = 0
		page     = 1
		pagesize = self.settings['long search results limit']
		limit    = pagesize
		path     = unicode(path) # just in case we missed it somewhere else

		for filename in matches:
		#for filename in sorted(matches, key = unicode.lower):

			# ignore hidden files
			if filename[0] == '.' and ignore_hidden: continue

			if count > limit: 

				# don't let user click more than 5 times on "load more results"
				if page == 5:
					self._add_app_button(_('Open this folder'), 'system-file-manager', self._view.SUBFOLDERS_SECTION, 'xdg', path, _('Show additional search results in a file browser'), None)
					yield count

				load_more_button = self._add_app_button(_('Load additional results'), 'add', self._view.SUBFOLDERS_SECTION, 'special', self._load_more_subfolder_results, _('Show additional search results'), None)
				yield count

				self._view.hide_button(load_more_button)
				page += 1
				limit = page * (pagesize * 2)

			count += 1

			command = os.path.join(path, filename)
			icon_name = self.icon_helper.get_icon_name_for_path(command)
			if icon_name is None: icon_name = 'folder'

			basename, dummy = os.path.splitext(filename)
			self._add_app_button(filename, icon_name, self._view.SUBFOLDERS_SECTION, 'xdg', command, command, None)

		yield count


	def _load_more_subfolder_results(self):
		"""
		Loads more results in the subfolder view
		"""

		try:
			self._file_looper.next()	
		except:
			pass


	def _cancel_all_plugin_timers(self):
		"""
		Cancels both the "search start"-type timers and the "search timeout"-type ones
		"""

		if self._search_timer_local is not None:
			glib.source_remove(self._search_timer_local)

		if self._search_timer_remote is not None:
			glib.source_remove(self._search_timer_remote)

		if self._search_timeout_local is not None:
			glib.source_remove(self._search_timeout_local)

		if self._search_timeout_remote is not None:
			glib.source_remove(self._search_timeout_remote)


	def _search_with_plugin_keyword(self, text):
		"""
		Search using the plugin that matches the keyword (specified as the first
		word in a query beginning with a question mark). This method always
		returns True, to make sure keyword searches take precedence over other
		types. 
		"""

		keywordtext = self._parse_keyword_query(text)
		if not keywordtext: return True

		keyword, text = keywordtext
		keyword_exists = False

		# search for a registered keyword that has this keyword as a substring
		for plugin_keyword in self._keyword_to_plugin_mapping:
			if plugin_keyword.find(keyword) == 0:
				keyword_exists = True
				keyword = plugin_keyword
				break

		if not keyword_exists: return True

		plugin = self._keyword_to_plugin_mapping[keyword][0]

		self._cancel_all_plugins()
		self._cancel_all_plugin_timers()

		self._schedule_search_with_specific_plugin(text, plugin.search_delay_type, plugin)

		return True


	def _reset_search(self):
		"""
		Sets Cardapio's search to its default empty state
		"""
		self._schedule_search_with_all_plugins('')


	def _schedule_search_with_all_plugins(self, text):
		"""
		Cleans up plugins and timers, and creates new timers to search with all
		plugins
		"""

		self._cancel_all_plugins()
		self._cancel_all_plugin_timers()

		self._schedule_search_with_specific_plugin(text, None)
		self._schedule_search_with_specific_plugin(text, 'local')
		self._schedule_search_with_specific_plugin(text, 'remote')


	def _schedule_search_with_specific_plugin(self, text, delay_type = None, specific_plugin = None):
		"""
		Sets up timers to start searching with the plugins specified by the
		delay_type and possibly by "specific_plugin"
		"""

		if delay_type is None:
			self._search_with_specific_plugin(text, None, specific_plugin)

		elif delay_type == 'local':
			timer_delay = self.settings['local search update delay']
			timeout     = self.settings['local search timeout']
			self._search_timer_local   = glib.timeout_add(timer_delay, self._search_with_specific_plugin, text, delay_type, specific_plugin)
			self._search_timeout_local = glib.timeout_add(timeout, self._show_all_plugin_timeout_text, delay_type)
		
		else:
			timer_delay = self.settings['remote search update delay']
			timeout     = self.settings['remote search timeout']
			self._search_timer_remote   = glib.timeout_add(timer_delay, self._search_with_specific_plugin, text, delay_type, specific_plugin)
			self._search_timeout_remote = glib.timeout_add(timeout, self._show_all_plugin_timeout_text, delay_type)


	def _search_with_specific_plugin(self, text, delay_type, specific_plugin = None):
		"""
		Start a plugin-based search
		"""

		if delay_type == 'local':
			if self._search_timer_local is not None:
				glib.source_remove(self._search_timer_local)
				self._search_timer_local = None

		elif delay_type == 'remote':
			if self._search_timer_remote is not None:
				glib.source_remove(self._search_timer_remote)
				self._search_timer_remote = None

		if specific_plugin is not None:

			plugin = specific_plugin
			plugin.__is_running = True

			try:
				self._show_plugin_loading_text(plugin)
				plugin.search(text, self.settings['long search results limit'])

			except Exception, exception:
				self._plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

			return False # Required!

		query_is_too_short = (len(text) < self.settings['min search string length'])
		number_of_results = self.settings['search results limit']

		for plugin in self._active_plugin_instances:

			if plugin.search_delay_type != delay_type or plugin.__show_only_with_keyword:
				continue

			if plugin.hide_from_sidebar and query_is_too_short:
				continue

			if plugin.hide_from_sidebar == -1:
				continue

			plugin.__is_running = True

			try:
				self._show_plugin_loading_text(plugin)
				plugin.search(text, number_of_results)

			except Exception, exception:
				self._plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def _show_plugin_loading_text(self, plugin):
		"""
		Write "Searching..." under the plugin section title
		"""

		self._view.show_section_status_text(plugin.section, self.plugin_loading_text)

		if self._selected_section is None or plugin.section == self._selected_section:
			self._view.show_section(plugin.section)
			self._view.hide_no_results_text()

		self._plugins_still_searching += 1


	def _show_all_plugin_timeout_text(self, delay_type):
		"""
		Write "Plugin timed out..." under the plugin section title
		"""

		for plugin in self._active_plugin_instances:

			if not plugin.__is_running: continue
			if plugin.search_delay_type != delay_type: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self._plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)

			self._view.show_section_status_text(plugin.section, self.plugin_timeout_text)
			self._view.show_section(plugin.section)

			self._plugins_still_searching -= 1

		self._consider_showing_no_results_text()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def _plugin_handle_search_error(self, plugin, text):
		"""
		Handler for when a plugin returns an error
		"""

		plugin.__is_running = False
		self._plugin_write_to_log(plugin, text, is_error = True)

		# must be outside the lock!
		self._plugin_handle_search_result(plugin, [], '')


	def _plugin_handle_search_result(self, plugin, results, original_query):
		"""
		Handler for when a plugin returns some search results. This handler may be
		running on a different thread from the rest of the Cardapio application, since
		plugins can launch their own threads. For this reason, this code is actually 
		sent to be executed in the UI thread (if any).
		"""

		self._view.run_in_ui_thread(self._plugin_handle_search_result_synchronized, plugin, results, original_query)


	def _plugin_handle_search_result_synchronized(self, plugin, results, original_query):
		"""
		Handler for when a plugin returns some search results. This one is
		actually synchronized with the UI thread.
		"""

		self._view.hide_section(plugin.section) # for added performance
		self._view.remove_all_buttons_from_section(plugin.section)

		plugin.__is_running = False
		self._plugins_still_searching -= 1

		query_is_too_short = (len(self._current_query) < self.settings['min search string length'])

		if plugin.hide_from_sidebar and query_is_too_short:

			# Handle the case where user presses backspace *very* quickly, and the
			# search starts when len(text) > min_search_string_length, but after
			# search_update_delay milliseconds this method is called while the
			# search entry now has len(text) < min_search_string_length

			# Anyways, it's hard to explain, but suffice to say it's a race
			# condition and we handle it here.

			results = []

		elif original_query != self._current_query:
			results = []

		for result in results:

			icon_name = self.icon_helper.get_icon_name_from_app_info(result, plugin.fallback_icon)
			button = self._add_app_button(result['name'], icon_name, plugin.section, result['type'], result['command'], result['tooltip'], None)
			button.app_info['context menu'] = result['context menu']

		if results:

			self._no_results_to_show = False
			self._mark_section_has_entries_and_show_category_button(plugin.section)

			if (self._selected_section is None) or (self._selected_section == plugin.section):
				self._view.show_section(plugin.section)
				self._view.hide_no_results_text()

			else:
				self._consider_showing_no_results_text()

		else: 
			self._mark_section_empty_and_hide_category_button(plugin.section)

			if (self._selected_section is None) or (self._selected_section == plugin.section):
				self._view.hide_section(plugin.section)

			self._consider_showing_no_results_text()


	def _plugin_ask_for_reload_permission(self, plugin):
		"""
		Handler for when a plugin asks Cardapio whether it can reload its
		database
		"""

		# TODO: do this in a smarter way
		self._schedule_rebuild()


	def _cancel_all_plugins(self):
		"""
		Tell all plugins to stop a possibly-time-consuming search
		"""

		self._plugins_still_searching = 0

		for plugin in self._active_plugin_instances:

			if not plugin.__is_running: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self._plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)


	def _choose_coordinates_for_window(self):
		"""
		Returns the appropriate coordinates for the given window. The
		coordinates are determined according to the following algorithm:

		- If there's no Cardapio applet, place the window in the center of the
		  screen

		- Otherwise, position the window near the applet (just below it if the
		  panel is top oriented, just to the left of it if the panel is right
		  oriented, and so on)
		"""

		window_width, window_height = self._view.get_window_size()

		if self._applet.IS_CONTROLLABLE:

			orientation = self._applet.get_orientation()
			x, y = self._applet.get_position()
			w, h = self._applet.get_size()
			if orientation == POS_LEFT: x += w
			if orientation == POS_TOP : y += h

		elif self._default_window_position is not None:

			return self._default_window_position

		else:

			# show cardapio on center of the monitor that contains the mouse cursor

			cursor_x, cursor_y = self._view.get_cursor_coordinates()
			monitor_x, monitor_y, monitor_width, monitor_height = \
					self._view.get_monitor_dimensions(cursor_x, cursor_y)

			x = monitor_x + (monitor_width - window_width)/2
			y = monitor_y + (monitor_height - window_height)/2

		return x, y


	def _get_coordinates_inside_screen(self, x, y, force_anchor_right = False, force_anchor_bottom = False):
		"""
		If the window won't fit on the usable screen, given its size and
		proposed coordinates, the method will rotate it over its x, y, or x=y
		axis. Also, the window won't hide beyond the top and left borders of the
		usable screen.

		Returns the new x, y coordinates and two booleans indicating whether the
		window was rotated around the x and/or y axis.
		"""

		window_width, window_height = self._view.get_window_size()

		screen_x, screen_y, screen_width, screen_height = self._view.get_screen_dimensions()
		monitor_x, monitor_y, monitor_width, monitor_height = self._view.get_monitor_dimensions(x, y)

		# maximal coordinates of window and usable screen
		max_window_x , max_window_y  = x + window_width         , y + window_height
		max_screen_x , max_screen_y  = screen_x + screen_width  , screen_y + screen_height
		max_monitor_x, max_monitor_y = monitor_x + monitor_width, monitor_y + monitor_height

		anchor_right  = False
		anchor_bottom = False

		orientation = self._applet.get_orientation()
		w, h = self._applet.get_size()

		# if the window won't fit horizontally, flip it over its y axis
		if max_window_x > max_screen_x or max_window_x > max_monitor_x: 
			anchor_right = True
			if orientation == POS_TOP or orientation == POS_BOTTOM: x += w 

		# if the window won't fit horizontally, flip it over its x axis
		if max_window_y > max_screen_y or max_window_y > max_monitor_y: 
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


	def _restore_dimensions(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Resize Cardapio according to the user preferences
		"""

		if self.settings['window size'] is not None:
			self._view.resize_main_window(*self.settings['window size'])

		if x is None or y is None:
			x, y = self._choose_coordinates_for_window()

		x, y, anchor_right, anchor_bottom = self._get_coordinates_inside_screen(x, y, force_anchor_right, force_anchor_bottom)
		self._view.move_main_window(x, y, anchor_right, anchor_bottom)

		if self.settings['mini mode']:
			self._view.set_main_splitter_position(0)

		elif self.settings['splitter position'] > 0:
			self._view.set_main_splitter_position(self.settings['splitter position'])

		# decide which search bar to show (top or bottom) depending
		# on the y = 0 axis window invert
		self._view.setup_search_entry(not anchor_bottom, not self.settings['mini mode'])


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = 'iii', out_signature = None)
	def set_default_window_position(self, x, y, screen):
		"""
		Sets Cardapio's position when it was initialized by itself (usually not 
		in applet mode). If not set, Cardapio defaults to appearing in the center
		of the screen.
		"""

		self._default_window_position = (x,y)


	def _save_dimensions(self):
		"""
		Save Cardapio's size into the user preferences
		"""

		self.settings['window size'] = self._view.get_window_size()
		if not self.settings['mini mode']:
			self.settings['splitter position'] = self._view.get_main_splitter_position()


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = None)
	def show_hide(self):
		"""
		Toggles Cardapio's visibility and places the window near the applet or,
		if there is no applet, centered on the screen.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		return self.show_hide_near_point()


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = None, out_signature = None)
	def show_hide_near_mouse(self):
		"""
		Toggles Cardapio's visibility and places the window near the mouse.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		mouse_x, mouse_y = self._view.get_cursor_coordinates()
		return self.show_hide_near_point(mouse_x, mouse_y)


	@dbus.service.method(dbus_interface = Constants.BUS_NAME_STR, in_signature = 'iibb', out_signature = None)
	def show_hide_near_point(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Toggles Cardapio's visibility and places the window at the given (x,y)
		location -- or as close as possible so that the window still fits on the
		screen.

		Requests are ignored if they come more often than
		MIN_VISIBILITY_TOGGLE_INTERVAL.

		This function is dbus-accessible.
		"""

		if time() - self._last_visibility_toggle < Cardapio.MIN_VISIBILITY_TOGGLE_INTERVAL:
			return

		if self._visible: 
			self._hide()
		else: 
			if x is not None: x = int(x)
			if y is not None: y = int(y)
			if x < 0: x = None
			if y < 0: y = None
			self._show(x, y, force_anchor_right, force_anchor_bottom)
		# emit the signal
		self.on_menu_visibility_changed()

		return True
	

	def _show(self, x = None, y = None, force_anchor_right = False, force_anchor_bottom = False):
		"""
		Shows the Cardapio window.

		If arguments x and y are given, the window will be positioned somewhere
		near that point.  Otherwise, the window will be positioned near applet
		or in the center of the screen (if there's no applet).
		"""

		if self._reset_search_timer is not None:
			glib.source_remove(self._reset_search_timer)

		# reset to regular mode if 'keep search results' is off
		elif not self.settings['keep search results']:
			self._switch_modes(show_system_menus = False, toggle_mode_button = True)

		self._applet.draw_toggled_state(True)
		#self._applet.disable_autohide(True)

		self._restore_dimensions(x, y, force_anchor_right = False, force_anchor_bottom = False)

		self._view.focus_search_entry()
		self._show_main_window_on_best_screen()

 		self._view.scroll_to_top()

		self._visible = True
		self._last_visibility_toggle = time()

		self._opened_last_app_in_background = False


	def _show_main_window_on_best_screen(self):
		"""
		Shows the Cardapio window on the best screen: if there is an applet,
		shows Cardapio on the screen where the applet is drawn. Otherwise, show
		wherever the mouse pointer is.
		"""
		if self._applet.IS_CONTROLLABLE:
			self._view.set_screen(self._applet.get_screen_number())
		else:
			self._view.set_screen(self._view.get_screen_with_pointer())

		self._view.show_main_window()


	def _hide(self):
		"""
		Hides the Cardapio window.
		"""

		if not self._visible: return

		self._applet.draw_toggled_state(False)
		#self._applet.disable_autohide(False)

		self._visible = False
		# emit the signal
		self.on_menu_visibility_changed()
		self._last_visibility_toggle = time()

		self._view.hide_main_window()

		if self.settings['keep search results']:
			# remembering current search text in all entries
			self._view.set_search_entry_text(self._current_query)
		else:
			self._reset_search_timer = glib.timeout_add(self.settings['keep results duration'], self._reset_search_timer_fired)

		self._cancel_all_plugins()

		logging.info('(RSS = %s)' % get_memory_usage())

		if self._must_rebuild: self._schedule_rebuild()

		return False # used for when hide() is called from a timer


	def _hide_if_mouse_away(self):
		"""
		Hide the window if the cursor is neither on top of it nor on top of the
		panel applet
		"""

		#mouse_x, mouse_y = self._view.get_cursor_coordinates()

		#window_width, window_height = self._view.get_window_size()
		#window_x, window_y = self._view.get_window_position()

		#cursor_in_window_x = (window_x <= mouse_x <= window_x + window_width)
		#cursor_in_window_y = (window_y <= mouse_y <= window_y + window_height)
		#if cursor_in_window_x and cursor_in_window_y: return

		if self._view.is_cursor_inside_window(): return
		if self._applet.has_mouse_cursor(mouse_x, mouse_y): return

		self._hide()


	def _remove_section_from_app_list(self, section):
		"""
		Remove from the app list all apps that belong in a given section.
		"""

		i = 0
		while i < len(self._app_list):

			app = self._app_list[i]
			if section == app['section']: self._app_list.pop(i)
			else: i += 1


	def _fill_system_list(self):
		"""
		Populate the System section
		"""

		# TODO: add session buttons here

		for entry in self._sys_tree:
			if entry.is_menu():
				self.add_section(entry.get_name(), entry.get_icon(), entry.get_comment(), node = entry, system_menu = True)

		self._view.hide_pane(self._view.SYSTEM_CATEGORY_PANE)

		section, dummy = self.add_section(_('Uncategorized'), 'applications-other', tooltip = _('Other configuration tools'), hidden_when_no_query = False, system_menu = True)
		self._add_tree_to_app_list(self._sys_tree, section, self._sys_list, recursive = False)

		self._add_tree_to_app_list(self._sys_tree, self._view.SYSTEM_SECTION, self._app_list)


	def _fill_uncategorized_list(self):
		"""
		Populate the Uncategorized section
		"""

		self._add_tree_to_app_list(self._app_tree, self._view.UNCATEGORIZED_SECTION, self._app_list, recursive = False)


	def _fill_places_list(self):
		"""
		Populate the places list
		"""

		self._fill_bookmarked_places_list()
		self._fill_system_places_list()


	def _fill_system_places_list(self):
		"""
		Populate the "system places", which include Computer, the list of
		connected drives, and so on.
		"""

		section = self._view.PLACES_SECTION

		if self._volume_monitor is None:
			volume_monitor_already_existed = False
			self._volume_monitor = gio.volume_monitor_get() # keep a reference to avoid getting it garbage-collected
		else:
			volume_monitor_already_existed = True

		for mount in self._volume_monitor.get_mounts():

			volume = mount.get_volume()
			if volume is None: continue

			name = volume.get_name()
			icon_name = self.icon_helper.get_icon_name_from_gio_icon(volume.get_icon())

			try    : command = str(volume.get_mount().get_root().get_uri())
			except : command = ''

			self._add_app_button(name, icon_name, section, 'xdg', command, command, self._app_list)
			self._volumes[command] = volume

		self._add_app_button(_('Network'), 'network', section, 'xdg', 'network://', _('Browse the contents of the network'), self._app_list)

		self.de.connect_to_server
		if self.de.connect_to_server is not None:
			self._add_app_button(_('Connect to Server'), 'network-server', section, 'raw', self.de.connect_to_server, _('Connect to a remote computer or shared disk'), self._app_list)

		self._add_app_button(_('Trash'), 'user-trash', section, 'xdg', 'trash:///', _('Open the trash'), self._app_list)

		if not volume_monitor_already_existed:
			self._volume_monitor.connect('mount-added', self._on_volume_monitor_changed)
			self._volume_monitor.connect('mount-removed', self._on_volume_monitor_changed)


	def _fill_bookmarked_places_list(self):
		"""
		Populate the "bookmarked places", which include Home and your personal bookmarks.
		"""

		section = self._view.PLACES_SECTION

		self._add_app_button(_('Home'), 'user-home', section, 'xdg', self._home_folder_path, _('Open your personal folder'), self._app_list)

		xdg_folders_file_path = os.path.join(DesktopEntry.xdg_config_home, 'user-dirs.dirs')
		xdg_folders_file = file(xdg_folders_file_path, 'r')
		# TODO: xdg_folders_file = codecs.open(xdg_folders_file_path, mode='r', encoding='utf-8')

		# find desktop path and add desktop button
		for line in xdg_folders_file.readlines():

			res = re.match('\s*XDG_DESKTOP_DIR\s*=\s*"(.+)"', line)
			if res is not None:
				path = res.groups()[0]

				# check if the desktop path is the home folder, in which case we
				# do *not* need to add the desktop button.
				if os.path.abspath(path) == self._home_folder_path: break

				self._add_place(_('Desktop'), path, 'user-desktop')
				break

		xdg_folders_file.close()

		bookmark_file_path = os.path.join(self._home_folder_path, '.gtk-bookmarks')
		bookmark_file = file(bookmark_file_path, 'r')
		# TODO: xdg_folders_file = codecs.open(bookmark_file_path, mode='r', encoding='utf-8')

		for line in bookmark_file.readlines():
			if line.strip(' \n\r\t'):

				name, path = self._get_place_name_and_path(line)
				name = urllib2.unquote(name)

				path_type, dummy = urllib2.splittype(path)

				gio_path_obj = gio.File(path)
				if not gio_path_obj.query_exists() and path_type not in Cardapio.REMOTE_PROTOCOLS: continue

				self._add_place(name, path, 'folder')

		bookmark_file.close()

		if self._bookmark_monitor is None:
			self._bookmark_monitor = gio.File(bookmark_file_path).monitor_file() # keep a reference to avoid getting it garbage-collected
			self._bookmark_monitor.connect('changed', self._on_bookmark_monitor_changed)


	def _on_bookmark_monitor_changed(self, monitor, file, other_file, event):
		"""
		Handler for when the user adds/removes a bookmarked folder using
		Nautilus or some other program
		"""

	 	# hoping this helps with bug 662249, in case there is some strange threading problem happening (although there are no explicit threads in this program)	
		self._bookmark_monitor.handler_block_by_func(self._on_bookmark_monitor_changed)

		if event == gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:
			self._remove_all_buttons_from_section(self._view.PLACES_SECTION)
			self._fill_places_list()

		# same here
		self._bookmark_monitor.handler_unblock_by_func(self._on_bookmark_monitor_changed) 


	def _on_volume_monitor_changed(self, monitor, drive):
		"""
		Handler for when volumes are mounted or ejected
		"""

	 	# hoping this helps with bug 662249, in case there is some strange threading problem happening (although there are no explicit threads in this program)	
		self._volume_monitor.handler_block_by_func(self._on_volume_monitor_changed)

		self._remove_all_buttons_from_section(self._view.PLACES_SECTION)
		self._fill_places_list()

		# same here
		self._volume_monitor.handler_unblock_by_func(self._on_volume_monitor_changed) 


	def _get_folder_name_and_path(self, folder_path):
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


	def _get_place_name_and_path(self, folder_path):
		"""
		Return the name and path of a bookmarked folder given a line from the
		gtk-bookmarks file
		"""

		res = folder_path.split(' ')
		if len(res) > 1:
			name = ' '.join(res[1:]).strip(' \n\r\t')
			path = res[0]
			return name, path

		return self._get_folder_name_and_path(folder_path)


	def _add_place(self, folder_name, folder_path, folder_icon):
		"""
		Add a folder to the Places list in Cardapio
		"""

		folder_path = os.path.expanduser(folder_path.replace('$HOME', '~')).strip(' \n\r\t')
		folder_path = self._unescape_url(folder_path)

		icon_name = self.icon_helper.get_icon_name_for_path(folder_path)
		if icon_name is None: icon_name = folder_icon
		self._add_app_button(folder_name, icon_name, self._view.PLACES_SECTION, 'xdg', folder_path, folder_path, self._app_list)


	def _fill_favorites_list(self, section, list_name):
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

			app_button = self._add_app_button(app['name'], app['icon name'], section, app['type'], app['command'], app['tooltip'], self._app_list)

			self._view.show_button(app_button)
			self._no_results_to_show = False
			self._mark_section_has_entries_and_show_category_button(section)
			no_results = False

			if section == self._view.SIDEPANE_SECTION:
				button_str, tooltip = self._sanitize_button_info(app['name'], app['tooltip'])
				sidepane_button = self._view.add_sidepane_button(button_str, app['icon name'], self._view.SIDE_PANE, tooltip)
				sidepane_button.app_info = app_button.app_info

		if no_results or (section is self._view.SIDEPANE_SECTION):
			self._disappear_with_section_and_category_button(section)

		elif (self._selected_section is not None) and (self._selected_section != section):
			self._view.hide_section(section)

		else:
			self._mark_section_has_entries_and_show_category_button(section)
			self._view.show_section(section)


	def _fill_session_list(self):
		"""
		Populate the Session list
		"""

		items = [
			[
				_('Lock Screen'),
				_('Protect your computer from unauthorized use'),
				'system-lock-screen',
				self.de.lock_screen,
				self._view.LEFT_SESSION_PANE,
			],
			[
				_('Log Out...'),
				_('Log out of this session to log in as a different user'),
				'system-log-out',
				self.de.save_session,
				self._view.RIGHT_SESSION_PANE,
			],
			[
				_('Shut Down...'),
				_('Shut down the system'),
				'system-shutdown',
				self.de.shutdown,
				self._view.RIGHT_SESSION_PANE,
			],
		]

		for item in items:

			app_button = self._add_app_button(item[0], item[2], self._view.SESSION_SECTION, 'raw', item[3], item[1], self._app_list)

			button_str, tooltip = self._sanitize_button_info(item[0], item[1])
			session_button = self._view.add_session_button(button_str, item[2], item[4], tooltip)

			session_button.app_info = app_button.app_info


	def _build_applications_list(self):
		"""
		Populate the Applications list by reading the Gnome menus
		"""

		self._load_application_menus()

		for entry in self._app_tree:
			if entry.is_menu():
				self.add_section(entry.get_name(), entry.get_icon(), entry.get_comment(), node = entry, hidden_when_no_query = False)


	# TODO MVC - appears to be done...
	# This method is called from the View API
	def add_section(self, title_str, icon_name = None, tooltip = '', hidden_when_no_query = False, node = None, system_menu = False):
		"""
		Add to the app pane a new section (i.e. a container holding a title
		label and a hbox to be filled with apps). This also adds the section
		name to the left pane, under the View label.
		"""

		if system_menu:
			category_pane = self._view.SYSTEM_CATEGORY_PANE
			app_list = self._sys_list
		else:
			category_pane = self._view.CATEGORY_PANE
			app_list = self._app_list

		# add category to application pane
		section, label = self._view.add_application_section(title_str)

		if node is not None:
			# add all apps in this category to application pane
			self._add_tree_to_app_list(node, section, app_list)
			# TODO: fix small leak in the call above

		# add category to category pane
		title_str, tooltip = self._sanitize_button_info(title_str, tooltip)
		category_button = self._view.add_category_button(title_str, icon_name, category_pane, section, tooltip)

		if hidden_when_no_query:
			self._view.hide_button(category_button)
			self._view.hide_section(section)

		self._section_list[section] = {
			'must show'         : not hidden_when_no_query,
			'category button'   : category_button,
			'name'              : title_str,
			'is system section' : system_menu,
			}

		return section, label


	def _build_special_sections(self):
		"""
		Builds sections that have special functions in the system, such as the
		one that contains the "no results to show" text and the one containing
		subfolder results.
		"""

		self._view.build_no_results_section()
		self._view.build_subfolders_section(_('Folder Contents'), _('Look inside folders'))


	def _build_reorderable_sections(self):
		"""
		Add all the reorderable sections to the app pane
		"""

		self._view.build_sidepane_section(_('Side Pane'), _('Items pinned to the side pane'))

		for basename in self.settings['active plugins']:

			if basename not in self._plugin_database:
				self.settings['active plugins'].remove(basename)
				continue

			plugin_class = self._plugin_database[basename]['class']

			if basename == 'applications':
				self._build_applications_list() 
				self._view.build_uncategorized_section(_('Uncategorized'), _('Items that are not under any menu category'))
				self._view.build_session_section(_('Session'), None)
				self._view.build_system_section(_('System'), None)
				self._builtin_applications_plugin_active = True

			elif basename == 'places':
				self._view.build_places_section(plugin_class.category_name, plugin_class.category_tooltip)
				self._builtin_places_plugin_active = True

			elif basename == 'pinned':
				self._view.build_pinneditems_section(plugin_class.category_name, plugin_class.category_tooltip)

			else:
				for category in xrange(plugin_class.category_count):

					try:
						plugin = self._plugin_database[basename]['instances'][category]
					except Exception, exception:
						logging.error('[%s] No such category in this plugin!' % basename)
						logging.error(exception)
						continue
						
					if plugin is None: continue
					plugin.section, dummy = self.add_section(plugin.category_name, plugin.category_icon, plugin.category_tooltip, hidden_when_no_query = plugin.hide_from_sidebar)


	def _remove_all_buttons_from_section(self, section):
		"""
		Removes all buttons from a given section
		"""

		# this is necessary to avoid a memory leak
		if section is not None: 
			self._app_list = [app for app in self._app_list if app['section'] != section]
			self._sys_list = [app for app in self._sys_list if app['section'] != section]

			self._view.remove_all_buttons_from_section(section)


	def _reset_search_query(self):
		"""
		Clears search entry.
		"""

		self._reset_search_timer = None
		self._view.clear_search_entry()
		self._subfolder_stack = []


	def _reset_search_timer_fired(self):
		"""
		Clears search entry and unselects the selected section button (if any)
		"""

		if not self._view.is_window_visible():
			self._reset_search_query_and_selected_section()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def _reset_search_query_and_selected_section(self):
		"""
		Clears search entry and unselects the selected section button (if any)
		"""

		self._reset_search_query()
		self._untoggle_and_show_all_sections()


	def _add_app_button(self, button_str, icon_name, section, command_type, command, tooltip, app_list):
		"""
		Adds a new button to the app pane
		"""

		if type(button_str) is str:
			button_str = unicode(button_str, 'utf-8')

		button_str, tooltip = self._sanitize_button_info(button_str, tooltip)
		button = self._view.add_app_button(button_str, icon_name, section, tooltip)

		# save some metadata for easy access
		button.app_info = {
			'name'         : button_str,
			'tooltip'      : tooltip,
			'icon name'    : icon_name,
			'command'      : command,
			'type'         : command_type,
			'context menu' : None,
		}

		# NOTE: I'm not too happy about keeping this outside the View, but I can't think
		# of a better solution...
		if command_type == 'app':
			self._view.setup_button_drag_and_drop(button, True)

		elif command_type == 'xdg':
			self._view.setup_button_drag_and_drop(button, False)

		if app_list is not None:

			path, basename = os.path.split(command)
			if basename : basename, dummy = os.path.splitext(basename)
			else        : basename = path

			app_list.append({
				'name'     : button_str.lower(),
				'button'   : button,
				'section'  : self._view.get_section_from_button(button),
				'basename' : basename,
				'command'  : command,
				})

		return button


	def _sanitize_button_info(self, button_str, tooltip):
		"""
		Clean up the strings that have to do with a button: its label and its tooltip
		"""

		button_str = self._unescape_url(button_str)
		if tooltip: tooltip = self._unescape_url(tooltip)
		return button_str, tooltip


	def _add_tree_to_app_list(self, tree, section, app_list, recursive = True):
		"""
		Adds all the apps in a subtree of Gnome's menu as buttons in a given
		parent widget
		"""

		for entry in tree:

			if entry.is_entry():

				self._add_app_button(entry.get_name(), entry.get_icon(), section, 'app', entry.get_path(), entry.get_comment(), app_list)

			elif entry.is_menu() and recursive:

				self._add_tree_to_app_list(entry, section, app_list)


	def _go_to_parent_folder(self):
		"""
		Goes to the parent of the folder specified by the string in the search
		entry.
		"""

		current_path = self._view.get_search_entry_text()
		slash_pos = current_path.rfind('/')

		if current_path[-1] == '/': slash_pos = current_path[:-1].rfind('/')
		current_path = current_path[:slash_pos+1]
		self._view.set_search_entry_text(current_path)
		self._view.place_text_cursor_at_end()


	def _setup_app_context_menu(self, app_info):
		"""
		Show or hide different context menu options depending on the widget
		"""

		self._view.hide_context_menu_option(self._view.OPEN_PARENT_MENUITEM)
		self._view.hide_context_menu_option(self._view.PEEK_INSIDE_MENUITEM)
		self._view.hide_context_menu_option(self._view.EJECT_MENUITEM)

		if app_info['type'] == 'callback' or app_info['type'] == 'special':
			self._view.hide_context_menu_option(self._view.PIN_MENUITEM)
			self._view.hide_context_menu_option(self._view.UNPIN_MENUITEM)
			self._view.hide_context_menu_option(self._view.ADD_SIDE_PANE_MENUITEM)
			self._view.hide_context_menu_option(self._view.REMOVE_SIDE_PANE_MENUITEM)
			self._view.hide_context_menu_option(self._view.SEPARATOR_MENUITEM)
			self.setup_plugin_context_menu(app_info)
			return

		already_pinned = False
		already_on_side_pane = False
		self._view.show_context_menu_option(self._view.SEPARATOR_MENUITEM)

		for command in [app['command'] for app in self.settings['pinned items']]:
			if command == app_info['command']:
				already_pinned = True
				break

		for command in [app['command'] for app in self.settings['side pane items']]:
			if command == app_info['command']:
				already_on_side_pane = True
				break

		if already_pinned:
			self._view.hide_context_menu_option(self._view.PIN_MENUITEM)
			self._view.show_context_menu_option(self._view.UNPIN_MENUITEM)
		else:
			self._view.show_context_menu_option(self._view.PIN_MENUITEM)
			self._view.hide_context_menu_option(self._view.UNPIN_MENUITEM)

		if already_on_side_pane:
			self._view.hide_context_menu_option(self._view.ADD_SIDE_PANE_MENUITEM)
			self._view.show_context_menu_option(self._view.REMOVE_SIDE_PANE_MENUITEM)
		else:
			self._view.show_context_menu_option(self._view.ADD_SIDE_PANE_MENUITEM)
			self._view.hide_context_menu_option(self._view.REMOVE_SIDE_PANE_MENUITEM)

		folder_or_file = self._app_is_valid_folder_or_file(app_info)
		if folder_or_file == 1:
			self._view.show_context_menu_option(self._view.PEEK_INSIDE_MENUITEM)
		if folder_or_file > 0:
			self._view.show_context_menu_option(self._view.OPEN_PARENT_MENUITEM)

		# figure out whether to show the 'eject' menuitem
		if app_info['command'] in self._volumes:
			self._view.show_context_menu_option(self._view.EJECT_MENUITEM)
			# NOTE: 'eject' only appears if the Places plugin is active!
			# (otherwise, self._volumes is empty)

		self.setup_plugin_context_menu(app_info)


	def _app_is_valid_folder_or_file(self, app_info):
		"""
		Returns 1 if the given app_info points to a local folder that exists, 
		2 if a file, and 0 if neither.
		"""

		app_type = app_info['type']
		if app_type != 'xdg': return 0

		path_type, canonical_path = urllib2.splittype(app_info['command'])
		dummy, extension = os.path.splitext(canonical_path)

		# don't show it for network://, trash://, or .desktop files
		# TODO: should we handle http://, etc?
		if path_type not in ('computer', 'network', 'trash') and extension != '.desktop':

			unescaped_path = self._unescape_url(canonical_path)
			if os.path.isdir(unescaped_path)    : return 1
			elif os.path.isfile(unescaped_path) : return 2

		return 0


	# TODO MVC - appears to be done...
	def setup_plugin_context_menu(self, app_info):
		"""
		Sets up context menu items as requested by individual plugins
		"""

		self._view.clear_plugin_context_menu()
		if 'context menu' not in app_info: return
		if app_info['context menu'] is None: return
		self._view.fill_plugin_context_menu(app_info['context menu'])


	def _peek_or_launch_app(self, app_info, hide):
		"""
		Either peek inside a folder (if the app_info describes a local folder)
		or launch the item in the app_info
		"""

		if self._app_is_valid_folder_or_file(app_info) == 1:
			self._peek_inside_folder(app_info)
			self._view.place_text_cursor_at_end()

		elif self._app_is_valid_folder_or_file(app_info) > 0:
			self._open_parent_folder(app_info)

		else:
			self._launch_app(app_info, hide)


	def _launch_app(self, app_info, hide):
		"""
		Execute app_info['command'], for any app_info['type']
		"""

		command = app_info['command']
		command_type = app_info['type']

		self._opened_last_app_in_background = not hide

		if command_type == 'app':
			self._launch_desktop(command, hide)

		elif command_type == 'raw':
			self._launch_raw(command, hide)

		elif command_type == 'raw-in-terminal':
			self._launch_raw_in_terminal(command, hide)

		elif command_type == 'raw-no-notification':
			self._launch_raw(command, hide, skip_startup_notification = True)

		elif command_type == 'xdg':
			self._launch_xdg(command, hide)

		elif command_type == 'callback':
			text = self._current_query
			if hide: self._hide()
			command(text)

		elif command_type == 'special':
			command()


	def _open_parent_folder(self, app_info):
		"""
		Opens the parent folder of a given file/folder
		"""
		parent_folder, dummy = os.path.split(app_info['command'])
		self._launch_xdg(parent_folder)


	def _peek_inside_folder(self, app_info):
		"""
		Shows within Cardapio the folder that given app_info points to
		"""

		dummy, path = urllib2.splittype(app_info['command'])
		if os.path.isfile(path): path, dummy = os.path.split(path)

		path = self._unescape_url(path)
		name = app_info['name']

		if self._subfolder_stack:
			entry_text = self._view.get_search_entry_text() + name
			self._subfolder_stack.append((entry_text, path))
		else:
			self._subfolder_stack = [(name, path)]
			entry_text = name

		self._view.set_search_entry_text(entry_text + '/')


	def _launch_desktop(self, command, hide = True):
		"""
		Launch applications represented by .desktop files
		"""

		if os.path.exists(command):

			path = DesktopEntry.DesktopEntry(command).getExec()
			path = self._unescape_string(path)

			# Strip parts of the path that contain %<a-Z>

			path_parts = path.split()

			for i in xrange(len(path_parts)):
				if path_parts[i][0] == '%':
					path_parts[i] = ''

			path = ' '.join(path_parts)
			
			if DesktopEntry.DesktopEntry(command).getTerminal():
				return self._launch_raw_in_terminal(path, hide)
			else:
				return self._launch_raw(path, hide)

		else:
			logging.warn('Tried launching an app that does not exist: %s' % desktop_path)


	def _launch_xdg(self, path, hide = True):
		"""
		Open a url, file or folder
		"""

		path = self._escape_quotes_for_shell(self._unescape_url(path))
		path_type, dummy = urllib2.splittype(path)

		# if the file is executable, ask what to do
		if os.path.isfile(path) and os.access(path, os.X_OK):

			dummy, extension = os.path.splitext(path)

			# treat '.desktop' files differently
			if extension == '.desktop':
				self._launch_desktop(path, hide)
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
				response = self._view.show_executable_file_dialog(primary_text, secondary_text, hide_terminal_option)

				# if "Run in Terminal"
				if response == 1:
					return self._launch_raw_in_terminal(path, hide)

				# if "Display"
				elif response == 2:
					pass

				# if "Run"
				elif response == 3:
					return self._launch_raw(path, hide)

				# if "Cancel"
				else:
					return

		elif path_type in Cardapio.REMOTE_PROTOCOLS:
			# TODO: move to DesktopEnvironment.py
			special_handler = self.settings['handler for %s paths' % path_type]
			return self._launch_raw(special_handler % path, hide)

		return self._launch_raw(self.de.file_open % path, hide)


	def _launch_raw(self, path, hide = True, skip_startup_notification = False):
		"""
		Run a command as a subprocess
		"""

		notify_id = None

		try:
			if not skip_startup_notification:

				app       = gio.AppInfo(path)
				context   = gtk.gdk.AppLaunchContext()
				notify_id = context.get_startup_notify_id(app, [])

				os.environ['DESKTOP_STARTUP_ID'] = notify_id

			if self._applet.panel_type != PANEL_TYPE_NONE:
				# allow launched apps to use Ubuntu's AppMenu
				os.environ['UBUNTU_MENUPROXY'] = 'libappmenu.so'

			# FIXME
			#
			# This is the preferred GNOME way of doing things:
			#app.launch(None, context)
			# ...but how do we set the working directory?
			#
			# in the meantime, I'll just continue using this:
			subprocess.Popen(path, shell = True, cwd = self._home_folder_path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)

			if notify_id is not None: 
				context.launch_failed(notify_id)

			return False

		if hide: self._hide()

		return True


	def can_launch_in_terminal(self):
		"""
		Returns true if the libraries for launching in a terminal are installed
		"""

		return (self.de.execute_in_terminal is not None)


	def _launch_raw_in_terminal(self, path, hide = True):
		"""
		Run a command inside Gnome's default terminal
		"""

		try:
			if self.can_launch_in_terminal():
				self.de.execute_in_terminal(self._home_folder_path, path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)
			return False

		if hide:
			self._hide()

		return True


	def _escape_quotes_for_shell(self, text):
		"""
		Sanitize a string by escaping quotation marks, but treat single quotes
		differently since they cannot be escaped by the shell when in already
		single-quote mode (i.e. strong quoting).
		"""

		text = text.replace("'", r"'\''")
		text = text.replace('"', r'\"')
		return text


	def _unescape_url(self, text):
		"""
		Clear all sorts of escaping from a URL, like %20 -> [space]
		"""

		# Important: unicode(*) must be the outermost function here, or all
		# sorts of unicode-related problems may appear!!!
		return unicode(urllib2.unquote(text)) 


	def _unescape_string(self, text):
		"""
		Clear all sorts of escaping from a string, like slash slash -> slash
		"""

		return text.decode('string-escape')


	def _untoggle_and_show_all_sections(self):
		"""
		Show all sections that currently have search results, and untoggle all
		category buttons
		"""

		self._no_results_to_show = True

		for sec in self._section_list:
			if self._section_list[sec]['must show'] and self._section_list[sec]['is system section'] == self._in_system_menu_mode:
				self._view.show_section(sec)
				self._no_results_to_show = False
			else:
				self._view.hide_section(sec)

		if not self._no_results_to_show:
			self._view.hide_no_results_text()

		if self._selected_section is not None:
			widget = self._section_list[self._selected_section]['category button']
			self._view.set_sidebar_button_toggled(widget, False)

		self._selected_section = None
		self._view.set_all_sections_sidebar_button_toggled(True, self._in_system_menu_mode)

		if self._view.is_search_entry_empty():
			self._view.set_all_sections_sidebar_button_sensitive(False, self._in_system_menu_mode)


	def _toggle_and_show_section(self, section):
		"""
		Show a given section, make sure its button is toggled, and that
		no other buttons are toggled
		"""

		# hide all sections
		self._view.hide_sections(self._section_list)

		# untoggle the currently-toggled button, if any
		if self._selected_section is not None:
			widget = self._section_list[self._selected_section]['category button']
			self._view.set_sidebar_button_toggled(widget, False)

		# untoggled and make sensitive the "All" buttons
		self._view.set_all_sections_sidebar_button_toggled(False, True)
		self._view.set_all_sections_sidebar_button_toggled(False, False)
		self._view.set_all_sections_sidebar_button_sensitive(True, True)
		self._view.set_all_sections_sidebar_button_sensitive(True, False)

		self._selected_section = section
		self._consider_showing_no_results_text()
 		self._view.scroll_to_top()


	def _consider_showing_no_results_text(self):
		"""
		Decide whether the "No results" text should be shown (and, if so, show it)
		"""

		if self._selected_section is None:

			if self._plugins_still_searching > 0:
				return

			if self._no_results_to_show:
				self._view.show_no_results_text()

			return

		if self._section_list[self._selected_section]['must show']:
			self._view.show_section(self._selected_section)
			self._view.hide_no_results_text()

		else:
			self._view.hide_section(self._selected_section)
			self._view.show_no_results_text(self.no_results_in_category_text % {'category_name': self._section_list[self._selected_section]['name']})


	def _disappear_with_all_transitory_sections(self):
		"""
		Hides all sections that should not appear in the sidebar when
		there is no text in the search entry
		"""

		self._disappear_with_section_and_category_button(self._view.SUBFOLDERS_SECTION)
		self._disappear_with_section_and_category_button(self._view.SIDEPANE_SECTION)

		if self._builtin_applications_plugin_active:
			self._disappear_with_section_and_category_button(self._view.SESSION_SECTION)
			self._disappear_with_section_and_category_button(self._view.SYSTEM_SECTION)
			self._disappear_with_section_and_category_button(self._view.UNCATEGORIZED_SECTION)

		self._disappear_with_all_transitory_plugin_sections()


	def _disappear_with_section_and_category_button(self, section):
		"""
		Mark a section as empty, hide it, and hide its category button
		"""

		self._mark_section_empty_and_hide_category_button(section)
		self._view.hide_section(section)


	def _disappear_with_all_sections_and_category_buttons(self):
		"""
		Hide all sections, including plugins and non-plugins
		"""

		for section in self._section_list:
			self._mark_section_empty_and_hide_category_button(section)
			self._view.hide_section(section)


	def _disappear_with_all_transitory_plugin_sections(self):
		"""
		Hide the section for all plugins that are marked as transitory
		"""

		for plugin in self._active_plugin_instances:
			if plugin.hide_from_sidebar:
				self._disappear_with_section_and_category_button(plugin.section)


	def _mark_section_empty_and_hide_category_button(self, section):
		"""
		Mark a section as empty (no search results) and hide its sidebar button
		"""

		if not self._section_list[section]['must show']: return
		self._section_list[section]['must show'] = False
		self._view.hide_button(self._section_list[section]['category button'])


	def _mark_section_has_entries_and_show_category_button(self, section):
		"""
		Mark a section as having entries and show its sidebar button
		"""

		# check first for speed improvement (since this function usually gets
		# called several times, once for each app in the section)
		if self._section_list[section]['must show']: return

		self._section_list[section]['must show'] = True
		self._view.show_button(self._section_list[section]['category button'])

	# TODO: simplify the spaghetti structure related to hiding-showing sections
	
	# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
	# Callbacks used in the View module	

	def handle_section_all_clicked(self):
		"""
		This method is activated when the user presses the "All" section button.
		It unselects the currently-selected section if any, otherwise it clears
		the search entry.
		"""

		if self._selected_section is None:
			self._view.clear_search_entry()
			self._view.set_all_sections_sidebar_button_sensitive(False, self._in_system_menu_mode)
			return 

		self._untoggle_and_show_all_sections()


	def handle_section_clicked(self, section):
		"""
		This method is activated when the user presses a section button (except
		for the "All" button). It causes that section to be displayed in case
		the it wasn't already visible, or hides it otherwise. Returns a boolean
		indicating whether the section button should be drawn toggled or not.
		"""

		# if already toggled, untoggle
		if self._selected_section == section:
			self._selected_section = None # necessary!
			self._untoggle_and_show_all_sections()
			return False

		# otherwise toggle
		self._toggle_and_show_section(section)
		return True


	def handle_about_menu_item_clicked(self, verb):
		"""
		Opens either the "About Gnome" dialog, or the "About Ubuntu" dialog,
		or the "About Cardapio" dialog
		"""

		if verb == 'AboutGnome':
			self._launch_raw(self.de.about_de)

		elif verb == 'AboutDistro':
			self._launch_raw(self.de.about_distro)

		else: self._view.open_about_dialog()


	def handle_resize_done(self):
		"""
		This function is called when the user releases the mouse after resizing the
		Cardapio window.
		"""

		self._save_dimensions()


	def handle_mainwindow_focus_out(self):
		"""
		Make Cardapio disappear when it loses focus
		"""

		# Fixes a bug where the main window sometimes loses focus right after
		# it is shown -- and for no apparent reason!
		if time() - self._last_visibility_toggle < Cardapio.MIN_VISIBILITY_TOGGLE_INTERVAL:
			return

		self._save_dimensions()

		# Make sure clicking the applet button doesn't cause a focus-out event.
		# Otherwise, the click signal can actually happen *after* the focus-out,
		# which causes the window to be re-shown rather than disappearing.  So
		# by ignoring this focus-out we actually make sure that Cardapio will be
		# hidden after all. Silly.
		mouse_x, mouse_y = self._view.get_cursor_coordinates()
		if self._applet.has_mouse_cursor(mouse_x, mouse_y): return

		# If the last app was opened in the background, make sure Cardapio
		# doesn't hide when the app gets focused

		if self._opened_last_app_in_background:

			self._opened_last_app_in_background = False
			self._show_main_window_on_best_screen()
			return

		self._hide()


	def handle_mainwindow_cursor_leave(self):
		"""
		Handler for when the cursor leaves the Cardapio window.
		If using 'open on hover', this hides the Cardapio window after a delay.
		"""

		if not self._applet.IS_CONTROLLABLE: return

		if self.settings['open on hover']:
			glib.timeout_add(self.settings['autohide delay'], self._hide_if_mouse_away)


	def handle_user_closing_mainwindow(self):
		"""
		What happens when the user presses Alt-F4? If in panel mode,
		nothing. If in launcher mode, this terminates Cardapio.
		"""

		if self._applet.panel_type != PANEL_TYPE_NONE:
			# keep window alive if in panel mode
			return True

		self.save_and_quit()


	def handle_window_destroyed(self):
		"""
		Handler for when the Cardapio window is closed
		"""

		self.save_and_quit()


	def handle_reload_clicked(self):
		"""
		Rebuilds the Cardapio UI immediately. Should *never* be called from a plugin!
		"""
		self._rebuild_ui(show_message = True)


	def handle_view_settings_changed(self):
		"""
		Rebuilds the UI after the View reports its settings has changed (for instance, 
		when the icon theme changes)
		"""

		self._schedule_rebuild()

	
	def handle_search_entry_icon_pressed(self):
		"""
		Handler for when the "clear" icon of the search entry is pressed
		"""

		if self._view.is_search_entry_empty():
			self._untoggle_and_show_all_sections()

		else:
			self._reset_search_query_and_selected_section()


	def handle_special_key_pressed(self, key, alt = False, ctrl = False):
		"""
		Handler for when an Alt/Ctrl combo is pressed and Cardapio is active.
		"""

		if alt:
			if type(key) == int and 1 <= key <= 9:

				app_info = self._view.get_nth_visible_app(key)

				if app_info is not None:
					self._launch_app(app_info, ctrl == False)


	def handle_search_entry_changed(self):
		"""
		Handler for when the user types something in the search entry
		"""

		self._process_query(ignore_if_unchanged = True)

	
	def handle_search_entry_activate(self, ctrl_is_pressed, shift_is_pressed):
		"""
		Handler for when the user presses Enter on the search entry
		"""

		if self._view.is_search_entry_empty():
			# TODO: why is this needed? I don't see its effects...
			self._disappear_with_all_transitory_sections() 
			return

		app_info = self._view.get_nth_visible_app(1)

		# About the line above, there should be no need for
		# asking the view what is the first visible app (with
		# get_nth_visible_app). Instead, the model should know the top
		# app already! Except this is not exactly that straight-forward,
		# since it depends on the plugin ordering chosen by the user. And to
		# further complicate matters, some plugins respond after a
		# local/remote delay. So this seemed like the simplest solution.

		if app_info is not None:
			self.handle_app_clicked(app_info, 1, ctrl_is_pressed, shift_is_pressed)

		if not self.settings['keep search results']:
			self._reset_search_timer = glib.timeout_add(self.settings['keep results duration'], self._reset_search_timer_fired)


	def handle_search_entry_tab_pressed(self):
		"""
		Handler for when the tab is pressed while the search entry is focused.
		This moves the focus into the app pane.
		"""
		self._view.focus_first_visible_app()


	def handle_search_entry_escape_pressed(self):
		"""
		Handle what should happen when Escape is pressed while the search entry
		is focused.
		"""

		self._cancel_all_plugins()

		text = self._view.get_search_entry_text()
		slash_pos = text.rfind('/')

		if self._subfolder_stack and slash_pos != -1:
			self._go_to_parent_folder()

		elif not self._view.is_search_entry_empty():
			self._reset_search_query()

		elif self._selected_section is not None:
			self._untoggle_and_show_all_sections()

		elif self._in_system_menu_mode:
			self._switch_modes(show_system_menus = False, toggle_mode_button = True)

		else:
			self._hide()


	def handle_editor_menu_item_clicked(self):
		"""
		Opens Gnome's menu editor.
		"""

		self._launch_raw(self.de.menu_editor)


	def handle_back_button_clicked(self):
		"""
		Handle the back-button's click action
		"""
		self._go_to_parent_folder()


	def handle_pin_this_app_clicked(self, clicked_app_info):
		"""
		Handle the pinning action
		"""

		self._remove_section_from_app_list(self._view.FAVORITES_SECTION)
		self._remove_all_buttons_from_section(self._view.FAVORITES_SECTION)
		self.settings['pinned items'].append(clicked_app_info)
		self._fill_favorites_list(self._view.FAVORITES_SECTION, 'pinned items')


	def handle_unpin_this_app_clicked(self, clicked_app_info):
		"""
		Handle the unpinning action
		"""

		self._remove_section_from_app_list(self._view.FAVORITES_SECTION)
		self._remove_all_buttons_from_section(self._view.FAVORITES_SECTION)
		self.settings['pinned items'].remove(clicked_app_info)
		self._fill_favorites_list(self._view.FAVORITES_SECTION, 'pinned items')


	def handle_add_to_side_pane_clicked(self, clicked_app_info):
		"""
		Handle the "add to sidepane" action
		"""

		self._remove_section_from_app_list(self._view.SIDEPANE_SECTION)
		self._remove_all_buttons_from_section(self._view.SIDEPANE_SECTION)
 		self._remove_all_buttons_from_section(self._view.SIDE_PANE)
		self.settings['side pane items'].append(clicked_app_info)
		self._fill_favorites_list(self._view.SIDEPANE_SECTION, 'side pane items')
		self._view.SIDE_PANE.queue_resize() # required! or sidepane's allocation will be x,y,width,0 when first item is added
		self._view.get_widget('SideappSubdivider').queue_resize() # required! or sidepane will obscure the mode switcher button


	def handle_remove_from_side_pane_clicked(self, clicked_app_info):
		"""
		Handle the "remove from sidepane" action
		"""

		self._remove_section_from_app_list(self._view.SIDEPANE_SECTION)
		self._remove_all_buttons_from_section(self._view.SIDEPANE_SECTION)
 		self._remove_all_buttons_from_section(self._view.SIDE_PANE)
		self.settings['side pane items'].remove(clicked_app_info)
		self._fill_favorites_list(self._view.SIDEPANE_SECTION, 'side pane items')
		self._view.get_widget('SideappSubdivider').queue_resize() # required! or an extra space will show up where but button used to be


	def handle_launch_app_pressed(self, clicked_app_info):
		"""
		Handle the "launch" context-menu action
		"""

		self._launch_app(clicked_app_info, True)


	def handle__open_parent_folder_pressed(self, clicked_app_info):
		"""
		Handle the "open parent folder" context-menu action
		"""

		self._open_parent_folder(clicked_app_info)


	def handle_launch_in_background_pressed(self, clicked_app_info):
		"""
		Handle the "launch in background" context-menu action
		"""

		self._launch_app(clicked_app_info, hide = False)


	def handle_peek_inside_pressed(self, clicked_app_info):
		"""
		Handle the "peek inside folder" context-menu action
		"""

		self._peek_inside_folder(clicked_app_info)


	def handle_eject_pressed(self, clicked_app_info):
		"""
		Handle the "eject" context-menu action
		"""

		volume = self._volumes[clicked_app_info['command']]
		volume.eject(return_true)


	def handle_app_clicked(self, app_info, button, ctrl_is_pressed, shift_is_pressed):
		"""
		Handles the on-click event for buttons on the app list
		"""

		if button == 1:

			if (shift_is_pressed):
				self._peek_or_launch_app(app_info, hide = not ctrl_is_pressed)

			else:
				self._launch_app(app_info, hide = not ctrl_is_pressed)


		elif button == 2:
			self._launch_app(app_info, hide = False)
			#self._view.block_focus_out_event()

		elif button == 3:
			self._setup_app_context_menu(app_info)
			self._view.block_focus_out_event()
			self._view.popup_app_context_menu(app_info)


	def handle_view_mode_toggled(self, show_system_menus):
		"""
		Handler for when the user toggles between the Control Center and regular views
		"""

		self._switch_modes(show_system_menus)


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


	# This method is called from OptionsWindow
	def toggle_mini_mode_ui(self):
		"""
		Collapses the sidebar into a row of small buttons (i.e. minimode)
		"""
		self._view.toggle_mini_mode_ui()


# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 
# Create some new built-ins for use in the plugins

import __builtin__
__builtin__._ = _
__builtin__.CardapioPluginInterface = CardapioPluginInterface
__builtin__.dbus        = dbus
__builtin__.logging     = logging
__builtin__.subprocess  = subprocess
__builtin__.get_output  = get_output
__builtin__.fatal_error = fatal_error
__builtin__.which       = which


