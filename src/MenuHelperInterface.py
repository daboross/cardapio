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


class MenuHelperInterface(object):
	"""
	Common API for XDG and Gnome menus.
	"""

	def is_valid(self):
		return False

	def __iter__(self):	
		return iter([])

	def is_menu(self):
		return False

	def is_entry(self):
		return False

	def get_name(self):
		return None

	def get_icon(self):
		return None

	def get_comment(self):
		return None

	def get_path(self):
		return None

	def set_on_change_handler(self, handler):
		pass


