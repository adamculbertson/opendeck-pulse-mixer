# PulseAudio Mixer OpenDeck Plugin
![Screenshot from OpenDeck of the mixer controlling four different devices, Game, Voice Chat, Media, and Headset](github/opendeck-ui.png)

Control PulseAudio Sink volumes from within OpenDeck on a supported Elgato StreamDeck device.

## Libraries
Uses BarRaider's [EasyPI v2](https://github.com/BarRaider/streamdeck-easypi-v2) to manage the settings, [python-pulse-control](https://github.com/mk-fg/python-pulse-control) to manage the PulseAudio sinks, and [Pillow](https://github.com/python-pillow/Pillow) to create the percentage images.

## Installing
Make sure you have [OpenDeck](https://github.com/nekename/OpenDeck) installed. Go to Plugins, then "Install from file" and select the ZIP file that you created/downloaded from here.

## Building
If you want to build the plugin yourself, you can run the `build.sh` script (outside the plugin directory, though). It basically just packages the Python scripts and resources into a ZIP file in a format that OpenDeck expects. You will also need my [base plugin](https://github.com/adamculbertson/opendeck-base-plugin) in the same directory as this plugin's directory.

## More Information
Information about the default included libraries, fonts, etc. can be found in my [base plugin](https://github.com/adamculbertson/opendeck-base-plugin)
