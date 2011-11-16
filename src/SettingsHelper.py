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

from misc import *

try:
	import Cardapio
	import Constants

	import os
	import gtk
	import json
	import logging

except Exception, exception:
	fatal_error('Fatal error loading Cardapio libraries', exception)
	import sys
	sys.exit(1)


class SettingsHelper:

	def __init__(self, config_folder_path):
		"""
		Reads Cardapio's config file and builds the settings dictionary.
		"""

		self.config_folder_path = config_folder_path
		
		self.settings = {}
		s = {}

		with self.get_config_file('r') as config_file:
			# if the file is empty, we assume it's the first run and
			# we'll fill it while saving the settings for the first time
			if(os.path.getsize(config_file.name) > 0):
				s = json.load(config_file)

		default_side_pane_items = []
		path = which('software-center')
		if path is not None:
			default_side_pane_items.append(
				{
					'name'      : _('Ubuntu Software Center'),
					'icon name' : 'softwarecenter',
					'tooltip'   : _('Lets you choose from thousands of free applications available for Ubuntu'),
					'type'      : 'raw',
					'command'   : 'software-center',
				})

		default_side_pane_items.append(
			{
				'name'      : _('Help and Support'),
				'icon name' : 'help-contents',
				'tooltip'   : _('Get help with %(distro_name)s') % { 'distro_name': Cardapio.Cardapio.distro_name },
				'type'      : 'raw',
				'command'   : 'gnome-help',
			})
			
		self.read_config_option(s, 'window size'                , None                     ) # format: [px, px]
		self.read_config_option(s, 'mini mode'                  , False                    ) # bool
		self.read_config_option(s, 'splitter position'          , 0                        ) # int, position in pixels
		self.read_config_option(s, 'show session buttons'       , False                    ) # bool
		self.read_config_option(s, 'keep results duration'      , 3000                     ) # msec
		self.read_config_option(s, 'keep search results'        , False                    ) # bool
		self.read_config_option(s, 'open on hover'              , False                    ) # bool
		self.read_config_option(s, 'open categories on hover'   , False                    ) # bool
		self.read_config_option(s, 'min search string length'   , 3                        ) # int, number of characters
		#self.read_config_option(s, 'menu rebuild delay'         , 3                        , force_update_from_version = [0,9,96]) # seconds
		self.read_config_option(s, 'search results limit'       , 5                        ) # int, number of results
		self.read_config_option(s, 'long search results limit'  , 15                       ) # int, number of results
		self.read_config_option(s, 'local search update delay'  , 100                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'remote search update delay' , 250                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'local search timeout'       , 3000                     ) # msec
		self.read_config_option(s, 'remote search timeout'      , 5000                     ) # msec
		self.read_config_option(s, 'autohide delay'             , 250                      ) # msec
		self.read_config_option(s, 'keybinding'                 , '<Super>space'           ) # the user should use gtk.accelerator_parse('<Super>space') to see if the string is correct!
		self.read_config_option(s, 'applet label'               , _('Menu')                ) # string
		self.read_config_option(s, 'applet icon'                , 'start-here'             , override_empty_str = False) # string (either a path to the icon, or an icon name)
		self.read_config_option(s, 'pinned items'               , []                       )
		self.read_config_option(s, 'side pane items'            , default_side_pane_items  )
		self.read_config_option(s, 'active plugins'             , ['pinned', 'places', 'applications', 'zeitgeist_simple', 'google', 'command_launcher', 'software_center'])
		self.read_config_option(s, 'plugin settings'            , {}                       )
		self.read_config_option(s, 'show titlebar'              , False                    ) # bool
		self.read_config_option(s, 'allow transparency'         , False                    ) # bool

		# these are a bit of a hack:
		self.read_config_option(s, 'handler for ftp paths'      , r"nautilus '%s'"         ) # a command line using %s
		self.read_config_option(s, 'handler for sftp paths'     , r"nautilus '%s'"         ) # a command line using %s
		self.read_config_option(s, 'handler for smb paths'      , r"nautilus '%s'"         ) # a command line using %s
		# see https://bugs.launchpad.net/bugs/593141

		self.settings['cardapio version'] = Cardapio.Cardapio.version

		# clean up the config file whenever options are changed between versions

		# 'side pane' used to be called 'system pane'
		if 'system pane' in self.settings:
			self.settings['side pane'] = self.settings['system pane']
			self.settings.pop('system pane')

		# 'None' used to be the 'applications' plugin
		if None in self.settings['active plugins']:
			i = self.settings['active plugins'].index(None)
			self.settings['active plugins'][i] = 'applications'

		# 'firefox_bookmarks.py' has been replaced by 'web_bookmarks.py'
		if 'firefox_bookmarks' in self.settings['active plugins']:
			i = self.settings['active plugins'].index('firefox_bookmarks')
			self.settings['active plugins'][i] = 'web_bookmarks'

		# make sure required plugins are in the plugin list
		for required_plugin in Constants.REQUIRED_PLUGINS:
			if required_plugin not in self.settings['active plugins']:
				self.settings['active plugins'] = [required_plugin] + self.settings['active plugins']

		# make sure plugins only appear once in the plugin list
		for plugin_name in self.settings['active plugins']:
			while len([basename for basename in self.settings['active plugins'] if basename == plugin_name]) > 1:
				self.settings['active plugins'].remove(plugin_name)

		# this saves the loaded config file (useful on the first run)
		self.save()


	def assert_config_file_exists(self):
		"""
		If this doesn't throw any exceptions, after the invocation the caller
		might be sure that the config file "config.json" exists at and can be
		used further.

		The method returns a file path to the config file.

		It might raise FatalSettingsError if "config.json" exists but is
		a directory.
		"""

		old_config_file_path = os.path.join(self.config_folder_path, 'config.ini')
		config_file_path = os.path.join(self.config_folder_path, 'config.json')

		if not os.path.exists(config_file_path):

			# maybe it's not there because we're migrating from version
			# that's using the old file extension (".ini")?
			if os.path.exists(old_config_file_path):
				# change the extension
				os.rename(old_config_file_path, config_file_path)
				# also, let's remove the old log file while we're at it...
				os.remove(os.path.join(self.config_folder_path, 'cardapio.log'))
			else:
				# create and close an empty file
				with open(config_file_path, 'w+') as new_file:
					pass

		elif not os.path.isfile(config_file_path):
			raise FatalSettingsError('cannot create file "%s" because a folder with that name already exists!' % config_file_path)

		return config_file_path


	def get_config_file(self, mode):
		"""
		Returns a file handler to Cardapio's config file. The caller is
		responsible for closing the file.
		"""

		return open(self.assert_config_file_exists(), mode)


	def save(self):
		"""
		Saves this settings object to a config file.
		"""

		with self.get_config_file('w') as config_file:
			logging.info('Saving config file...')
			json.dump(self.settings, config_file, sort_keys = True, indent = 4)
			logging.info('...done saving config file!')


	def read_config_option(self, user_settings, key, val, override_empty_str = False, force_update_from_version = None):
		"""
		Sets on itself the config option 'key' from the 'user_settings'
		dictionary using 'val' as a fallback value.

		Will override found but empty settings when the override_empty_str flag
		is set to true.

		Will update the setting 'key' to the 'val' value if user is migrating
		from version force_update_from_version.
		"""

		if key in user_settings:

			if override_empty_str and len(user_settings[key]) == 0:
				self.settings[key] = val
			else:
				self.settings[key] = user_settings[key]

		else:
			
			self.settings[key] = val

		if force_update_from_version is not None:

			if 'cardapio version' in user_settings:
				settings_version = [int(i) for i in user_settings['cardapio version'].split('.')]
			else:
				settings_version = 0

			if settings_version <= force_update_from_version:
				self.settings[key] = val


	def __getitem__(self, name):
		"""
		Returns the value of the setting named 'name'.
		"""

		return self.settings[name];


	def __setitem__(self, name, value):
		"""
		Sets the value of the setting named 'name' to 'value'.
		"""

		self.settings[name] = value;


class FatalSettingsError(Exception):
	"""
	Indicates unrecoverable SettingsHelper error.
	"""

	pass

