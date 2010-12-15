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
	import gtk

except Exception, exception:
	fatal_error('Fatal error loading Cardapio libraries', exception)
	import sys
	sys.exit(1)


def gtk_window_move_with_gravity(window, x, y):
	"""
	For some reason, GTK 2.20.x in Ubuntu 10.04 (Lucid) does not 
	respect the set_gravity command, so here we fix that.
	"""

	gravity = window.get_gravity()
	width, height = window.get_size()

	if gravity == gtk.gdk.GRAVITY_NORTH_WEST:
		pass

	elif gravity == gtk.gdk.GRAVITY_NORTH_EAST:
		x -= width

	elif gravity == gtk.gdk.GRAVITY_SOUTH_WEST:
		y -= height

	elif gravity == gtk.gdk.GRAVITY_SOUTH_EAST:
		x -= width
		y -= height

	# NOTE: There are other gravity constants in GDK, but we do not implement
	# them here because they're not used in Cardapio.

	window.set_gravity(gtk.gdk.GRAVITY_NORTH_WEST)
	window.move(x, y)



