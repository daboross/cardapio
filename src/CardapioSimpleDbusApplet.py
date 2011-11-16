#  
#  Copyright (C) 2011 Cardapio Team (tvst@hotmail.com)
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

try:
	from CardapioAppletInterface import *

except Exception, exception:
	fatal_error('Fatal error loading Cardapio', exception)
	sys.exit(1)


class CardapioSimpleDbusApplet(CardapioAppletInterface):

	panel_type = PANEL_TYPE_SIMPLEDBUS

	IS_CONFIGURABLE = True
	IS_CONTROLLABLE = False


	def __init__(self, bus):

		self._applet = bus.get_object('org.varal.CardapioSimpleDbusApplet', '/org/varal/CardapioSimpleDbusApplet')


	def update_from_user_settings(self, settings):

		label = settings['applet label']
		icon  = settings['applet icon']
		self._applet.configure_applet_button(label, icon)


