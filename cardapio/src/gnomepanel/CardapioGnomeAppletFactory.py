from Cardapio import Cardapio
from CardapioGnomeApplet import CardapioGnomeApplet

def CardapioGnomeAppletFactory(applet, iid):

	panel_applet = CardapioGnomeApplet(applet)
	cardapio = Cardapio(show = Cardapio.DONT_SHOW, panel_applet = panel_applet)

