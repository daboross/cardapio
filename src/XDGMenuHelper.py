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

from xdg import DesktopEntry, Menu
import os
from MenuHelperInterface import *

class XDGMenuHelper(MenuHelperInterface):
	"""
	This class only exists to provide a common API around the XDG Menu module
	and the Gnome GMenu module.

	In this case, the implementation is for the XDG version.
	"""

	def __init__(self, filename = None):
		if filename: self._node = Menu.parse(filename)
		else: self._node = None

	def is_valid(self):
		return bool(self._node)

	def _wrap_entry(self, entry):

		menuHelper = XDGMenuHelper()
		menuHelper._node = entry 
		return menuHelper

	def __iter__(self):	
		def the_iter(entries):
			for entry in entries:
				yield self._wrap_entry(entry)
			raise StopIteration
		return the_iter(self._node.Entries)

	def is_menu(self):
		return self._node.__class__ is Menu.Menu

	def is_entry(self):
		return self._node.__class__ is Menu.MenuEntry

	def get_name(self):
		if self.is_menu(): return self._node.getName()
		return self._node.DesktopEntry.getName()

	def get_icon(self):
		if self.is_menu(): return self._node.getIcon()
		return self._node.DesktopEntry.getIcon()

	def get_comment(self):
		if self.is_menu(): return self._node.getComment()
		return self._node.DesktopEntry.getComment()

	def get_path(self):
		if self.is_menu(): return self._node.getPath()
		return os.path.join(self._node.getDir(), self._node.Filename)

	def set_on_change_handler(self, handler):
		pass

