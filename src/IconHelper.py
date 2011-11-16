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
	import re
	import os
	import gtk
	import gio
	import json
	import logging
	from xdg import BaseDirectory

except Exception, exception:
	fatal_error('Fatal error loading Cardapio libraries', exception)
	import sys
	sys.exit(1)


class IconHelper:

	def __init__(self):

		self.icon_extension_types = re.compile('.*\.(png|xpm|svg)$')
		self.icon_theme = gtk.icon_theme_get_default()

		self.icon_size_app = gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]
		self.icon_size_category = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]
		self.icon_size_menu = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]

		uninstalled_icon_path = '/usr/share/app-install/icons/'
		if os.path.exists(uninstalled_icon_path):
			self.icon_theme.append_search_path(uninstalled_icon_path)

		self._listener = return_true
		self.icon_theme.connect('changed', self._on_icon_theme_changed)


	def get_icon_pixbuf(self, icon_name_or_path, icon_size, fallback_icon = 'application-x-executable'):
		"""
		Returns a GTK Image from a given icon name and size. The icon name can be
		either a path or a named icon from the GTK theme.
		"""

		# TODO: speed this up as much as possible!

		if not icon_name_or_path:
			icon_name_or_path = fallback_icon

		icon_name = icon_name_or_path

		# if icon_name_or_path is something like /dir/myfile.png, and if it
		# points to a valid file, try reading the file into a pixbuf and return it
		if os.path.isabs(icon_name_or_path):
			if os.path.isfile(icon_name_or_path):
				try: return gtk.gdk.pixbuf_new_from_file_at_size(icon_name_or_path, icon_size, icon_size)
				except: pass

		icon_name = self._get_icon_name_from_icon_path(icon_name_or_path)

		# try loading the icon from the theme 
		cleaned_icon_name = self.get_icon_name_from_theme(icon_name)
		if cleaned_icon_name is not None:
			try: return self.icon_theme.load_icon(cleaned_icon_name, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)
			except: pass

		# otherwise, try loading the icon from /usr/share/pixmaps 
		# or /usr/share/icons (non-recursive, of course!)
		for dir_ in BaseDirectory.xdg_data_dirs:
			for subdir in ('pixmaps', 'icons'):
				path = os.path.join(dir_, subdir, icon_name_or_path)
				if os.path.isfile(path):
					try: return gtk.gdk.pixbuf_new_from_file_at_size(path, icon_size, icon_size)
					except: pass

		# otherwise, return fallback icon
		return self.icon_theme.load_icon(fallback_icon, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)


	def get_icon_name_from_theme(self, icon_name):
		"""
		Find out if this icon exists in the theme (such as 'gtk-open'), or if
		it's a mimetype (such as audio/mpeg, which has an icon audio-mpeg), or
		if it has a generic mime icon (such as audio-x-generic).
		"""

		# replace slashed with dashes for mimetype icons
		cleaned_icon_name = icon_name.replace('/', '-')

		if self.icon_theme.has_icon(cleaned_icon_name):
			return cleaned_icon_name

		# try generic mimetype
		gen_type = cleaned_icon_name.split('-')[0]
		cleaned_icon_name = gen_type + '-x-generic'
		if self.icon_theme.has_icon(cleaned_icon_name):
			return cleaned_icon_name

		return None


	def get_icon_name_for_path(self, path):
		"""
		Gets the icon name for a given path using GIO
		"""

		info = None

		try:
			file_ = gio.File(path)
			info = file_.query_info('standard::icon')

		except Exception, exception:
			logging.warn('Could not get icon for %s' % path)
			logging.warn(exception)
			return None

		if info is not None:
			icon_names = info.get_icon().get_names()

			# if there are several icons available, as the theme for the name of the best one
			# (except there's no good way of doing that, so we need to ask for the best
			# *filename* and then get the icon name from the filename. Argh.
			if type(icon_names) == list:
				info = self.icon_theme.choose_icon(icon_names, self.icon_size_app, 0)
				if info is not None: 
					return self._get_icon_name_from_icon_path(info.get_filename())
				
			else:
				if self.icon_theme.has_icon(icon_names[0]): return icon_names[0]

		return None


	def get_icon_name_from_gio_icon(self, gio_icon, icon_size = None):
		"""
		Gets the icon name from a GIO icon object
		"""

		if icon_size == None: icon_size = self.icon_size_app

		try:
			names = self.icon_theme.lookup_by_gicon(gio_icon, icon_size, 0)
			if names: return names.get_filename()

		except: pass

		try:
			for name in gio_icon.get_names():
				if self.icon_theme.has_icon(name): return name

		except: pass

		return None


	def get_icon_name_from_app_info(self, app_info, fallback_icon):
		"""
		Returns the icon name given an app_info dictionary. This is useful for 
		plugins mostly, since they may request icons for non-traditional documents
		which cannot be handled by GIO.
		"""

		icon_name = app_info['icon name']
		fallback_icon = fallback_icon or 'text-x-generic'

		# TODO: remove lines below by November 2011
		#if icon_name == 'inode/symlink':
		#	icon_name = None

		if icon_name is not None:
			icon_name = self.get_icon_name_from_theme(icon_name)

		elif app_info['type'] == 'xdg':
			icon_name = self.get_icon_name_for_path(app_info['command'])

		if icon_name is None:
			icon_name = fallback_icon

		return icon_name


	def register_icon_theme_listener(self, listener):
		"""
		Registed a function to be called when we detect that the icon theme has
		changed
		"""
		self._listener = listener


	def _get_icon_name_from_icon_path(self, filepath):

		# get the last part of the file (i.e. myfile.png)
		icon_name = os.path.basename(filepath)

		# remove the file extension, if it exists (becomes myfile)
		dot_pos = icon_name.find('.')
		if dot_pos >= 0: icon_name = icon_name[:dot_pos]

		return icon_name


	def _on_icon_theme_changed(self, icon_theme):
		"""
		Rebuild the Cardapio UI whenever the icon theme changes
		"""

		self._listener()


