![BPS Logo](img/icon.png)
# BLE Positioning System (BPS)
A BLE positioning sytem for Homeassistant providing realtime, multi device, floor plan tracking indoors. Dependent on the Bermuda component built by @agattins. 

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Hogster&repository=BPS&category=Integration)

- Precisely track your bluetooth devices (indoors) using [bluetooth_proxy] [ESPHome](https://esphome.io/) (https://esphome.io/components/bluetooth_proxy.html) devices in [HomeAssistant](https://home-assistant.io/).

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

## What it does:

BLE Positioning System (BPS) continues on the great work by [@agittins](https://github.com/agittins) and his [Bermuda](https://github.com/agittins/bermuda).
Based on Bermudas ability to, in near-realtime, estimate distance to ESPHome devices running bluetooth_proxy BPS can leverage this information and by trilaterate give a precise position.

![Tracking](img/screenshots/bps_tracking.gif)

By exactly placing the location of the bluetooth_proxy devices as well as defining specific zones, BPS can show:
- Where exactly a device is located on a floorplan (like a GPS on a map)
- Determine which floor you are currently on. Gives the ability to automate when changing floor.
- Determine which zone (Kitchen, Bedroom etc.) a device is currently in. Gives the ability to automate based on specific devices entering or leaving a zone. 

This is done for all devices you track with Bermuda so you can track different persons or objects and automate based on this.

For my specific purpose I Sonoff NS Panels in all rooms of my house which I run esphome on. This together with other stationary bluetooth proxies I have good coverage to do trilataration.

Bermuda aims to let you track any bluetooth device, and have Homeassistant tell you where in your house that device is. The only extra hardware you need are esp32 devices running esphome that act as bluetooth proxies. Alternatively, Shelly Plus devices can also perform this function.

## What you need:

- Home Assistant up and running (duhh!)
![duhh](https://media.tenor.com/bZzADZu6H1AAAAAM/disappointed-facepalm.gif)
- Bermuda [bermuda] installed and tracking at least one bluetooth device
- At least three devices providing bluetooth proxy information to HA using esphome's `bluetooth_proxy` component. (it needs data from three devices to be able to track so if you only have three devices and you loose one due to distance it is not able to track)

@agittins writes on the Bermuda readme:
"  I like the D1-Mini32 boards because they're cheap and easy to deploy.
  The Shelly Plus bluetooth proxy devices are reported to work well.
  Only natively-supported bluetooth devices are supported, meaning there's no current or planned support for MQTT devices etc.

- USB Bluetooth on your HA host is not ideal, since it does not timestamp the advertisement packets.
  However it can be used for simple "Home/Not Home" tracking, and Area distance support is enabled currently."

  I can from my own experience add NS Panel since I use them all around the house as replacement for wall switches and thus get great coverage.


- Install BPS via HACS: [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Hogster&repository=BPS&category=Integration)

## Documentation and help - the Wiki

See [The Wiki](https://github.com/Hogster/BPS/wiki/) for more info on how it works and how to configure for your home.

## Screenshots

After installing, the integration should be visible in Settings, Devices & Services
![The integration, in Settings, Devices & Services](img/screenshots/integration1.png)
![The integration, in Settings, Devices & Services](img/screenshots/integration2.png)

The integration has now, if you are tracking devices, created 2 sensors for each device you are tracking. One for tracking device floor and another for tracking device zone
![Created entities](img/screenshots/entities.png)

You will now also have a new panel in the side panel named "BPS"

![BPS Panel](img/screenshots/panel.png)

The BPS panel for tracking is used for placing receivers (Bluetooth_Proxy devices) and defining zones. The "real-time" tracking is more to get a sense about what i happening and a form of debugging. You will notice where you have good precision as well as worse. And thus can give you an idea where to add devices for improved tracking.

![Tracking](img/screenshots/bps_tracking.gif)

## TODO / Ideas

- [ ] Improve the GUI (adding circles around the receivers for showing the distance and thus where the intersections are i.e. visualizing the trilataration)
- [ ] Be able to create zones that are not square (not a priority)
- [ ] Improve speed and performance in general
- [ ] Create a lovalace card with a map showing tracked devices
- [ ] And more...

## Feed back

To set the stage. I'm not a programmer and not even close to have this as a profession. I'm just a hobyist who love home automation and built this out of the urge to be able track people in realtime.
Do you think there is room to improve or in any other way add to the experience. GREAT! Please contribute or let me know.

Again, this work is only possible due to the great work by [@agittins](https://github.com/agittins) and his [Bermuda](https://github.com/agittins/bermuda). This is a teamwork, if we can improve Bermuda's abilties (precision & stability) BPS will also greatly benefit.


## Prior Art

There are other like [Bermuda](https://github.com/agittins/bermuda), `bluetooth_tracker`, `ble_tracker` and ESPresense. 
The `bluetooth_tracker` and `ble_tracker` integrations are only built to give a "home/not home"
determination, and don't do "Area" based location. (nb: "Zones" are places outside the
home, while "Areas" are rooms/areas inside the home). I wanted to be free to experiment with
this in ways that might not suit core, but hopefully at least some of this could find
a home in the core codebase one day.

The "monitor" script uses standalone Pi's to gather bluetooth data and then pumps it into
MQTT. It doesn't use the `bluetooth_proxy` capabilities which I feel are the future of
home bluetooth networking (well, it is for my home, anyway!).

ESPresense looks cool, but I don't want to dedicate my nodes to non-esphome use, and again
it doesn't leverage the bluetooth proxy features now in HA. I am probably reinventing
a fair amount of ESPresense's wheel.

## Installation

Definitely use the HACS interface! Once you have HACS installed, go to `Integrations`, click the
meatballs menu in the top right, and choose `Custom Repositories`. Paste `Hogster/BPS` into
the `Repository` field, and choose `Integration` for the `Category`. Click `Add`.

You should now be able to add the `BLE Positioning Sytem` integration. Once you have done that,
you need to restart Homeassistant, then in `Settings`, `Devices & Services` choose `Add Integration`
and search for `BLE Positioning Sytem` or 'BPS'. 

Once the integration is added, you need to set up your devices by clicking `Configure` in `Devices and Services`,
`Bermuda BLE Trilateration`.

In the `Configuration` dialog, you can choose which bluetooth devices you would like the integration to track.

The instructions below are the generic notes from the template:

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `BPS`.
4. Download _all_ the files from the `custom_components/BPS/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant
7. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for `BLE Positioning Sytem` or 'BPS'

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

The idea for this project was initiated by the work of agattins and his [Bermuda](https://github.com/agittins/bermuda). With an idea and great help from chatGPT this project came to life.

## Say thanks

If you found this helpful and you'd like to say thanks you can do so via buy me a coffee or a beer.
I've put a bunch of time into this integration and it always puts a smile on my face when people say thanks!

<a href="https://www.buymeacoffee.com/hogster" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" height="60" width="217"></a>
---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[buymecoffee]: https://buymeacoffee.com/hogster
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/Hogster/ble_pos_sys.svg?style=for-the-badge
[commits]: https://github.com/Hogster/BPS/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/Hogster/BPS.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40Hogster-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Hogster/BPS.svg?style=for-the-badge
[releases]: https://github.com/Hogster/BPS/releases
[user_profile]: https://github.com/Hogster
[bermuda]: https://github.com/agittins/bermuda
