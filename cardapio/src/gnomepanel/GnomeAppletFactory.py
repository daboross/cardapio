from Cardapio import Cardapio
from GnomePanelApplet import GnomePanelApplet

def GnomeAppletFactory(applet, iid):

	panel_applet = GnomePanelApplet(applet)
	cardapio = Cardapio(show = Cardapio.DONT_SHOW, panel_applet = panel_applet)

