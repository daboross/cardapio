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

from awn.extras import awnlib, __version__

from CardapioAwnApplet import CardapioAwnApplet
from Cardapio import Cardapio

class CardapioAwnWrapper:
	def __init__(self, applet):
		cardapio_awn_applet = CardapioAwnApplet(applet)
		cardapio = Cardapio(panel_applet = cardapio_awn_applet)


if __name__ == '__main__':
	awnlib.init_start(CardapioAwnWrapper, {
		'name'           : "Cardapio's applet",
		'short'          : 'cardapio',
		'version'        : __version__,
		'description'    : 'Replace your menu with Cardapio',
		'theme'          : CardapioAwnApplet.ICON,
		'author'         : 'Cardapio Team',
		'copyright-year' : '2010',
		'authors'        : [ 'Pawel Bara, Thiago Teixeira' ],
	}, 
	['no-tooltip'])

