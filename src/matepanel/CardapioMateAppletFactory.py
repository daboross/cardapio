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

from Cardapio import Cardapio
from CardapioMateApplet import CardapioMateApplet
import Constants 

def CardapioMateAppletFactory(applet, iid):

	mate_panel_applet = CardapioMateApplet(applet)
	cardapio = Cardapio(show = Constants.DONT_SHOW, panel_applet = mate_panel_applet)

