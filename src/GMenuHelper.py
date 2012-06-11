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

import gmenu
import os
from MenuHelperInterface import *

class GMenuHelper(MenuHelperInterface):
	"""
	This class only exists to provide a common API around the XDG Menu module
	and the Gnome GMenu module.

	In this case, the implementation is for the Gmenu version, which adds
	support for monitoring the menu for changes.
	"""

	def __init__(self, filename = None):
		if filename: 
			self._root = gmenu.lookup_tree(filename)
			self._node = self._root.root
		else: 
			self._root = None
			self._node = None

	def is_valid(self):
		return (self._node is not None)

	def _wrap_entry(self, entry):

		menuHelper = GMenuHelper()
		menuHelper._root = self._root
		menuHelper._node = entry 
		return menuHelper

	def __iter__(self):	
		def the_iter(entries):
			for entry in entries:
				yield self._wrap_entry(entry)
			raise StopIteration

		if self._node is None:
			raise StopIteration

		# will possibly have an issue where sometimes we can't have the .root here :-/
		return the_iter(self._node.contents)

	def is_menu(self):
		return isinstance(self._node, gmenu.Directory)

	def is_entry(self):
		return isinstance(self._node, gmenu.Entry)

	def get_name(self):
		return self._node.name

	def get_icon(self):
		return self._node.icon

	def get_comment(self):
		return self._node.get_comment()

	def get_path(self):
		return self._node.desktop_file_path

	def set_on_change_handler(self, handler):
		self._root.add_monitor(handler)


