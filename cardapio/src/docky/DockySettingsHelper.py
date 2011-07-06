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

import gconf
import gtk

class DockySettingsHelper:
	"""
	Helper class for dealing with Docky's GConf settings.
	"""

	# GConf keys of Docky's settings
	docky_gconf_root = '/apps/docky-2/Docky'
	docky_dcontroller_gconf_root = docky_gconf_root + '/DockController/'
	docky_iface_gconf_root = docky_gconf_root + '/Interface/DockPreferences/'

	# name of Cardapio's launcher
	cardapio_desktop = 'cardapioDocky.desktop'

	gconf_client = gconf.client_get_default()


	def __init__(self):
		# sets the names of user's active docks
		self.active_docks = self.gconf_client.get_list(self.docky_dcontroller_gconf_root + 'ActiveDocks', gconf.VALUE_STRING)


	def get_main_dock(self):
		"""
		Returns the name of the main Docky's dock (the one that keeps the
		unknown launchers). If there's none, raises MainDockError and if
		there are more, returns the first one's name.
		"""

		main_docks = filter(lambda dock:
			self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/WindowManager'),
		self.active_docks)

		if len(main_docks) == 0:
			raise MainDockError

		return main_docks[0]


	def get_icon_size(self, dock):
		"""
		Returns the IconSize property for chosen dock.
		"""

		return self.gconf_client.get_int(self.docky_iface_gconf_root + dock + '/IconSize')


	def get_zoom_percentage(self, dock):
		"""
		Returns the ZoomPercent property for chosen dock if zoom is
		enabled (ZoomEnabled). If not, returns neutral scaling
		factor (number 1).
		"""

		if(self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/ZoomEnabled')):
			return self.gconf_client.get_float(self.docky_iface_gconf_root + dock + '/ZoomPercent')
		else:
			return 1


	def get_position(self, dock):
		"""
		Returns the Position property for chosen dock.
		"""

		return self.gconf_client.get_string(self.docky_iface_gconf_root + dock + '/Position')


	def is_in_panel_mode(self, dock):
		"""
		Returns a flag saying whether the given dock is in panel mode.
		"""

		return self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/PanelMode')


	def is_showing_hover(self):
		"""
		Returns a flag saying whether Docky's icon has a hover.
		"""

		return self.gconf_client.get_string(self.docky_gconf_root + '/Items/DockyItem/HoverText') != ''


	def get_horizontal_offset(self, dock):
		"""
		Returns the horizontal offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode.
		"""

		return 5 if self.is_in_panel_mode(dock) else 15


	def get_vertical_offset(self, dock, position):
		"""
		Returns the vertical offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode, whether the icon of Docky has a hover and whether Cardapio is decorated.
		"""

		# initial offset
		#offset = 20 if self.is_in_panel_mode(dock) else 35
		offset = 5 if self.is_in_panel_mode(dock) else 15

		return offset


	def get_best_position(self, dock_num):
		"""
		Determines the best (x, y) position for Cardapio in docky-mode.
		Takes things like Docky's orientation, it's size or zoom mode
		into account. Also, requires a parameter saying whether Cardapio's
		window is decorated.
		"""

		# properties of our dock
		icon_size = self.get_icon_size(dock_num)
		zoom_percent = self.get_zoom_percentage(dock_num)
		position = self.get_position(dock_num)

		display = gtk.gdk.display_get_default()
		screen = display.get_default_screen()

		monitor = self.gconf_client.get_int(self.docky_iface_gconf_root + dock_num + '/MonitorNumber')
		monitor_x, monitor_y, monitor_width, monitor_height =\
				screen.get_monitor_geometry(monitor)

		dummy, mouse_x, mouse_y, dummy = display.get_pointer()

		# offsets from screen's borders
		horizontal_offset = self.get_horizontal_offset(dock_num)
		vertical_offset = self.get_vertical_offset(dock_num, position)

		# place cardapio slightly off so it's easier to interact with it
		half_zoomed_icon_size = icon_size * zoom_percent / 3
		# (ideally, i would like to place it flush with the docky window, so
		# for example it would be flush with the leftmost edge of docky when
		# docky is on the bottom edge of the screen. But there's no way to find
		# out where docky's left edge is...)

		force_anchor_right = False
		force_anchor_bottom = False

		# calculating final position...
		if position == 'Bottom':
			x = mouse_x - half_zoomed_icon_size 
			y = monitor_y + monitor_height - icon_size - vertical_offset
			force_anchor_bottom = True

		elif position == 'Top':
			x = mouse_x - half_zoomed_icon_size 
			y = monitor_y + icon_size + vertical_offset

		elif position == 'Left':
			x = monitor_x + icon_size + horizontal_offset
			y = mouse_y - half_zoomed_icon_size 

		elif position == 'Right':
			x = monitor_x + monitor_width - icon_size - horizontal_offset
			y = mouse_y - half_zoomed_icon_size
			force_anchor_right = True

		return x, y, force_anchor_right, force_anchor_bottom
	

class MainDockError(Exception):
	"""
	Exception raised when the DockySettingsHelper is unable to find the
	main dock of Docky.
	"""

	pass
