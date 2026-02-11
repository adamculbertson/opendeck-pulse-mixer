#!/usr/bin/env python
import json
import logging
import io
import os
import base64
from threading import Lock

import pulsectl
from PIL import Image, ImageDraw, ImageFont

import plugin

logging.basicConfig(level=logging.INFO)

# Get the font from the plugin directory
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(os.path.join(PLUGIN_DIR, "fonts"), "DejaVuSans-Bold.ttf")

try:
    # Define specific sizes
    name_font = ImageFont.truetype(FONT_PATH, 12)  # Smaller for device name
    volume_font = ImageFont.truetype(FONT_PATH, 18)  # Larger for the percentage
except OSError:
    # Fallback if the font path is wrong
    logging.warning("Font file not found, falling back to default.")
    name_font = volume_font = ImageFont.load_default()


def show_sink_info(volume_percent: float | int, sink_name: str, width: int = 72, height: int = 72) -> str:
    """
    Display an image with the device name/nickname and volume percentage on the Stream Deck.
    :param volume_percent: Volume level, between 0 and 100
    :param sink_name: The audio device name or nickname
    :param width: Image width (Stream Deck button width)
    :param height: Image height (Stream Deck button height)
    :return: Base64-encoded image to be displayed on the button
    """
    image = Image.new("RGBA", (width, height), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Sink name on the top
    draw.text((width // 2, 5), sink_name[:12], fill="white", font=name_font, anchor="mt")

    # If the volume is 0 (or muted), set the color to red
    # Otherwise, it's cyan
    if volume_percent > 0:
        fill = "cyan"
    else:
        fill = "red"

    # Volume in the center
    draw.text((width // 2, height // 2 + 5), f"{int(volume_percent)}%", fill=fill, font=volume_font, anchor="mm")

    buffered = io.BytesIO()
    image.save(buffered, format="PNG")

    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"

class PulsePlugin(plugin.SDPlugin):
    def __init__(self, port: int, info: str, uuid: str, event: str):
        super().__init__(port, info, uuid, event)
        self.pulse = pulsectl.Pulse("sd-audio-plugin")
        self.pulse_lock = Lock()
        self.sinks = []

        self.last_devices = {}
        self.last_volumes = {}

        self.refresh()

    def get_sink(self, index: int) -> pulsectl.PulseSinkInfo | None:
        """
        Quick way to get the sink from its index, or return None if not found
        :param index: The PulseAudio index of the sink (NOT the index in self.sinks)
        :return: The matching sink or None if not found
        """
        return next((s for s in self.sinks if s.index == index), None)

    def get_sink_from_name(self, name: str) -> pulsectl.PulseSinkInfo | None:
        """
        Quick way to get the sink from its name, or return None if not found
        :param name: The PulseAudio device name of the sink
        :return: The matching sink or None if not found
        """
        return next((s for s in self.sinks if s.description == name), None)

    def get_volume(self, index: int) -> int | None:
        """
        Get the volume of the PulseAudio sink at the given index.
        :param index: Index to retrieve the volume for
        :return: Volume as an int (percentage) or None if the sink wasn't found
        """
        sink = self.get_sink(index)
        if sink:
            return int(sink.volume.value_flat * 100.0)
        return None

    def set_volume(self, index: int, volume: float) -> bool:
        """
        Sets the volume to a specified value/
        :param index: The PulseAudio index of the sink (NOT the index in self.sinks)
        :param volume: Volume level as a float, either from 0.0 to 1.0 OR 0.0 to 100.0
        :return: True if a valid value was provided, False otherwise
        """
        with self.pulse_lock:
            sink = self.get_sink(index)
            if sink:
                if volume > 1.0:
                    volume = volume / 100.0

                value = max(0.0, min(1.0, volume))
                self.pulse.volume_set_all_chans(sink, value)
                self.logger.debug(f"Volume: {value}")
                return True
            return False

    def refresh(self):
        """
        Refreshes the internal list of sinks
        :return: None
        """
        with self.pulse_lock:
            self.sinks = self.pulse.sink_list()

    def on_loop(self, context: str):
        """
        Perform actions on a loop, like updating the image of a button
        :param context: Stream Deck context, provided by the WebSocket API
        :return: None
        """
        settings = self.ctxSettings.get(context)
        info = self.ctxInfo.get(context)

        if not settings or not info: return

        action = info["action"].split(".")[-1]
        if action == "showvol":
            device = settings.get("audioDevice")
            if not device: return

            sink = self.get_sink_from_name(device)
            if not sink:
                self.logger.error(f"Could not find sink from {device}")
                return

            mute = sink.mute  # Get the mute status
            volume = int(sink.volume.value_flat * 100.0)
            nickname = settings.get("deviceNickname")
            nickname = (nickname.strip() if nickname else None) or sink.description

            if mute:
                # Set the volume to 0 if muted
                volume = 0

            if not context in self.last_devices:
                self.last_devices[context] = nickname

            if not context in self.last_volumes:
                self.last_volumes[context] = volume

            if self.last_devices[context] != nickname or self.last_volumes[context] != volume:
                img = show_sink_info(volume, nickname)
                self.SetImage(context, img)

                self.last_devices[context] = nickname
                self.last_volumes[context] = volume


    def toggle_mute(self, index: int):
        """
        Toggles the mute status of the given PulseAudio sink
        :param index: The PulseAudio index of the sink (NOT the index in self.sinks)
        :return: None
        """
        with self.pulse_lock:
            sink = self.get_sink(index)
            if sink:
                if sink.mute:
                    self.pulse.mute(sink, False)
                else:
                    self.pulse.mute(sink, True)

    def get_settings(self, context: str):
        """
        Retrieves the settings associated with the given context
        :param context: Stream Deck context, provided by the WebSocket API
        :return: None
        """
        self.refresh()
        options = [sink.description for sink in self.sinks]

        if context not in self.ctxSettings:
            self.ctxSettings[context] = {}

        if "audioDevice" in self.ctxSettings[context]:
            value = self.ctxSettings[context]["audioDevice"]
        else:
            value = None

        settings = {"event": "getSettingsFields", "settingsFields": [{"type": "dropdown", "name": "audioDevice", "label": "Audio Sinks",
                     "value": value, "options": options}]}

        info = self.ctxInfo.get(context)

        if info:
            action = info["action"].split(".")[-1]
            if action == "showvol":
                settings_ctx = self.ctxSettings.get(context)
                nickname = settings_ctx.get("deviceNickname")

                settings["settingsFields"].append({"type": "text", "name": "deviceNickname", "label": "Device Nickname",
                                                   "value": nickname})

        payload = {"context": context, "event": "sendToPropertyInspector", "payload": settings}
        self.logger.debug(f"Sending payload to PI: {payload}")
        self.sd.socket.send(json.dumps(payload))


    # Plugin overrides
    def onSendToPlugin(self, payload: dict):
        context = payload["context"]

        self.get_settings(context)

    def onPropertyInspectorDidAppear(self, payload: dict):
        context = payload["context"]

        self.get_settings(context)

    def onKeyUp(self, payload: dict):
        action = payload["action"].split(".")[-1]
        context = payload["context"]
        settings = self.ctxSettings.get(context)
        if not settings:
            self.logger.error("Device not set up. Please go to the settings for the button and configure the audio device.")
            self.ShowAlert(context)
            return

        device = settings.get("audioDevice")
        if not device:
            self.logger.error("Audio device not set up. Please go to the settings for the audio device.")
            self.ShowAlert(context)
            return

        sink = self.get_sink_from_name(device)
        if not sink:
            self.logger.error(f"No sink found for device {device}")
            self.ShowAlert(context)
            return

        if action == "volup":
            current = self.get_volume(sink.index)
            if current is not None:
                new_volume = current + 5
                self.set_volume(sink.index, new_volume)

        elif action == "voldown":
            current = self.get_volume(sink.index)
            if current is not None:
                new_volume = current - 5
                self.set_volume(sink.index, new_volume)

        elif action == "mute":
            self.toggle_mute(sink.index)

        elif action == "showvol":
            self.toggle_mute(sink.index)

        self.logger.debug(f"Action: {action}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plugin parameters")
    parser.add_argument("-port", type=int)
    parser.add_argument("-info", type=str)
    parser.add_argument("-pluginUUID", type=str)
    parser.add_argument("-registerEvent", type=str)

    args = parser.parse_args()

    pulse_plugin = PulsePlugin(args.port, args.info, args.pluginUUID, args.registerEvent)
    pulse_plugin.run()