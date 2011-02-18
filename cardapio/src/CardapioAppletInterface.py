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

#PANEL_TYPE_NONE  = None (Just use None instead of PANEL_TYPE_NONE)
PANEL_TYPE_GNOME2 = 1
PANEL_TYPE_AWN    = 2
PANEL_TYPE_DOCKY  = None # The Docky applet is actually a "fake" applet, that just opens Cardapio at a given location.

POS_TOP    = 0
POS_BOTTOM = 1
POS_LEFT   = 2
POS_RIGHT  = 3

class CardapioAppletInterface:

	panel_type = None

	def setup(self, cardapio):
		"""
		This methods is called right after Cardapio loads its main variables, but
		before it actually loads plugins and builds its GUI.

		IMPORTANT: Do not modify anything inside the "cardapio" variable! It is
		only passed here directly (instead of using a proxy like in the case of
		plugins) because applets are written by "trusted" coders (since there
		will only be 3 or 4 applets total)
		"""
		pass


	def update_from_user_settings(self, settings):
		"""
		This method updates the applet according to the settings in
		settings['applet label'], settings['applet icon'], and settings['open on
		hover']
		"""
		pass


	def get_size(self):
		"""
		Returns the width and height of the applet
		"""
		return 0,0


	def get_position(self):
		"""
		Returns the position of the applet with respect to the screen (same as
		get_origin in GTK)
		"""
		return 0,0


	def get_orientation(self):
		"""
		Returns the edge of the screen at which the panel is placed, using one
		of POS_TOP, POS_BOTTOM, ORIENT_LEFT, ORIENT_RIGHT.
		"""
		return POS_TOP


	def draw_toggled_state(self, state):
		"""
		Draws the panel applet in the toggled/untoggled state depending
		on whether state is True/False. Note that this method should *only
		draw*, but not handle toggling in any way.
		"""
		pass


	def get_screen_number(self):
		"""
		Returns the number of the screen where the applet is placed
		"""
		pass


	def has_mouse_cursor(self, mouse_x, mouse_y):
		"""
		Returns true if the given coordinates is on top of the applet, and False
		otherwise.
		"""
		x, y = self.get_position()
		w, h = self.get_size()
		return ((x <= mouse_x <= x + w) and (y <= mouse_y <= y + h))


