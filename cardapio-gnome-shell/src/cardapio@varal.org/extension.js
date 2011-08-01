//
//  Copyright (c) 2011   Cardapio team
//

const St = imports.gi.St;
const Shell = imports.gi.Shell;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const Util = imports.misc.util;
//const Lang = imports.lang;

const DBus = imports.dbus;

const CardapioInterface = {
	name: 'org.varal.Cardapio',
	methods: [{
		name: 'show_hide_near_point',
		inSignature: 'iibb',
		outSignature: ''
	}, {
		name: 'is_visible',
		inSignature: '',
		outSignature: 'b'
	}, {
		name: 'set_default_window_position',
		inSignature: 'ii',
		outSignature: ''
	}]
};

let Cardapio = DBus.makeProxyClass(CardapioInterface);

function ApplicationsButton() {
	this._init.apply(this, arguments);
}

ApplicationsButton.prototype = {
	__proto__: PanelMenu.Button.prototype,

	_init: function() {
		PanelMenu.Button.prototype._init.call(this, 0.0);

		DBus.session.start_service('org.varal.Cardapio')

		this._icon = new St.Icon({ 
			icon_name: 'start-here',
			icon_type: St.IconType.SYMBOLIC,
			icon_size: Main.panel.button.height 
		});

        this._label = new St.Label({text: 'Menu' });

		this._box = new St.BoxLayout({style_class: 'cardapio-box'});
		this._box.add(this._icon);
		this._box.add(this._label);

		//this.actor.set_child(this._icon);
		this.actor.set_child(this._box);

		// add immediately after hotspot
		Main.panel._leftBox.insert_actor(this.actor, 1);

		x = this.actor.get_x();
		y = this.actor.get_y();

		this._cardapio = new Cardapio(DBus.session, 'org.varal.Cardapio', '/org/varal/Cardapio');
		this._cardapio.set_default_window_positionRemote(x, y);
	},

    _onButtonPress: function(actor, event) {

		visible = this._cardapio.is_visibleRemote();

        if (visible)
            this.actor.add_style_pseudo_class('active');
        else
            this.actor.remove_style_pseudo_class('active');

		x = this.actor.get_x();
		y = this.actor.get_y();
		this._cardapio.show_hide_near_pointRemote(x, y, false, false);
    },
};


function main(extensionMeta) {

	new ApplicationsButton();
}

